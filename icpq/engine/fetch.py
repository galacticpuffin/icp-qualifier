"""Fetch a company's own web pages. Standard library only.

* Every page is cached in the workspace database (table pages): the same URL is never fetched twice, and requalifying
  with a changed ICP re-reads the cache instead of the web.
* robots.txt is honoured; one request per host at a time with a politeness gap; bounded size and timeout.
* ICPQ_FIXTURE_SITES=<dir> serves pages from <dir>/<host>/<path>.html instead of the network (offline tests/demos)."""
import html as htmlmod
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path

from ..util import host, now, same_site

UA = os.environ.get("ICPQ_USER_AGENT", "Mozilla/5.0 (compatible; ICPQualifier/1.0; account research)")
TIMEOUT = float(os.environ.get("ICPQ_FETCH_TIMEOUT", "15"))
MAX_HTML = 800_000
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|docx?|xlsx?|pptx?|mp4|mp3|gz|ico|css|js)(\?|$)", re.IGNORECASE)

_host_lock = threading.Lock()
_host_next = {}


class _Text(HTMLParser):
    BLOCK = ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article", "footer", "header", "label", "td", "form")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.links, self.skip, self._a, self.title, self._t = [], [], 0, None, "", False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.skip += 1
        elif tag == "a":
            self._a = [dict(attrs).get("href") or "", ""]
            self.out.append(" ")
        elif tag == "title":
            self._t = True
        elif tag == "input":
            a = dict(attrs)
            if a.get("placeholder"):
                self.out.append(" " + a["placeholder"] + " ")
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self.skip:
            self.skip -= 1
        elif tag == "a" and self._a is not None:
            self.links.append(tuple(self._a))
            self._a = None
        elif tag == "title":
            self._t = False

    def handle_data(self, d):
        if self.skip:
            return
        if self._t:
            self.title += d
            return
        self.out.append(d)
        if self._a is not None:
            self._a[1] += d


def parse(html):
    p = _Text()
    try:
        p.feed(html or "")
    except Exception:
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text, p.links, re.sub(r"\s+", " ", p.title).strip()


class Fetcher:
    def __init__(self, ws, delay=0.6, fixtures=None):
        self.ws, self.delay = ws, delay
        self.fixtures = Path(fixtures or os.environ.get("ICPQ_FIXTURE_SITES") or "") if (fixtures or os.environ.get("ICPQ_FIXTURE_SITES")) else None
        self.fetched = self.cached = 0
        self._robots = {}

    def _polite(self, h):
        while True:
            with _host_lock:
                t = _host_next.get(h, 0)
                if time.time() >= t:
                    _host_next[h] = time.time() + self.delay
                    return
            time.sleep(min(0.25, max(0.01, t - time.time())))

    def _raw(self, url):
        """-> (status, final_url, body text, content-type, error)"""
        if self.fixtures:
            u = urllib.parse.urlparse(url)
            path = u.path.strip("/") or "index"
            f = self.fixtures / host(url) / (path + ("" if path.endswith((".html", ".txt", ".xml")) else ".html"))
            if path == "robots.txt":
                f = self.fixtures / host(url) / "robots.txt"
            if f.is_file():
                return 200, url, f.read_text(encoding="utf-8", errors="replace"), "text/html", ""
            return (404, url, "", "", "") if (self.fixtures / host(url)).is_dir() else (0, url, "", "", "URLError: fixture host unknown")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,text/plain,*/*;q=0.5",
                                                   "Accept-Language": "en-US,en;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:     # nosec B310: http(s) only, checked in get()
                ctype = r.headers.get("content-type", "")
                raw = r.read(MAX_HTML)
                cs = r.headers.get_content_charset() or "utf-8"
                return r.status, r.geturl(), raw.decode(cs, errors="replace"), ctype, ""
        except urllib.error.HTTPError as e:
            return e.code, url, "", "", f"HTTP {e.code}"
        except Exception as e:
            return 0, url, "", "", f"{type(e).__name__}: {str(e)[:160]}"

    def get(self, url, raw=False):
        if not re.match(r"^https?://", url or ""):
            return {"url": url, "final_url": url, "status": 0, "html": "", "text": "", "title": "", "error": "not an http(s) URL"}
        r = self.ws.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()
        if r:
            self.cached += 1
            return dict(r)
        if not raw and not self.robots_ok(url):
            return {"url": url, "final_url": url, "status": 0, "fetched_at": now(), "html": "", "text": "", "title": "", "error": "robots.txt disallows"}
        self._polite(host(url))
        status, final, body, ctype, err = self._raw(url)
        rec = {"url": url, "final_url": final, "status": status, "fetched_at": now(), "html": "", "text": "", "title": "", "error": err}
        if status == 200 and body:
            if raw or "html" in ctype or "text" in ctype or "xml" in ctype or not ctype:
                rec["html"] = body[:MAX_HTML]
                if not raw:
                    rec["text"], _, rec["title"] = parse(rec["html"])
            else:
                rec["error"] = "non-html: " + ctype[:60]
        self.fetched += 1
        with self.ws:
            self.ws.execute("INSERT OR REPLACE INTO pages(url,final_url,status,fetched_at,html,text,title,error) VALUES(?,?,?,?,?,?,?,?)",
                            (rec["url"], rec["final_url"], rec["status"], rec["fetched_at"], rec["html"], rec["text"], rec["title"], rec["error"]))
        return rec

    def robots_ok(self, url):
        u = urllib.parse.urlparse(url)
        if u.path == "/robots.txt":
            return True
        root = f"{u.scheme}://{u.netloc}"
        rp = self._robots.get(root)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rb = self.get(root + "/robots.txt", raw=True)
            rp.parse(rb["html"].splitlines() if rb["status"] == 200 else [])
            self._robots[root] = rp
        return rp.can_fetch("*", url) and rp.can_fetch(UA, url)

    def sitemap_urls(self, root, domain, hint, limit=4):
        if hint is None:
            return []
        rb = self.get(root + "/robots.txt", raw=True)
        maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rb["html"])[:3] if rb["status"] == 200 else []
        maps = maps or [root + "/sitemap.xml"]
        found, seen = [], set()
        for sm in maps[:3]:
            rec = self.get(sm, raw=True)
            if rec["status"] != 200:
                continue
            locs = re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)", rec["html"])
            for k in [x for x in locs if x.lower().endswith(".xml")][:3]:
                kr = self.get(k, raw=True)
                if kr["status"] == 200:
                    locs += re.findall(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)", kr["html"])
            for loc in locs:
                loc = htmlmod.unescape(loc)
                if loc not in seen and hint.search(urllib.parse.urlparse(loc).path) and same_site(loc, domain) and not SKIP_EXT.search(loc):
                    seen.add(loc)
                    found.append(loc)
            if len(found) >= limit:
                break
        return found[:limit]
