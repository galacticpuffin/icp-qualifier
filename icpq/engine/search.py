"""Web search providers. OFF by default; nothing paid ever runs without an explicit approval and a monthly cap.

Provider settings live in app.db (Settings page):
  none        no searches (research = company website only)
  duckduckgo  free HTML results; one request per `gap_s` seconds across the whole install, paused 30 min after a block
  serper | brave | tavily
              licensed APIs: need an API key, `approved: true` and `monthly_cap_usd`; every call is written to the usage
              ledger first and refused once the cap would be exceeded. Prices are editable (`usd_per_1k`).
  mock        offline test results from ICPQ_SEARCH_FIXTURES (JSON {query substring: [urls]})
A search result page is never evidence: results are only candidate URLs, which are fetched and must contain the
evidence themselves. Searches that couldn't run leave the account in RETRY (never counted as research complete)."""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from ..util import now

PRICES = {"serper": 1.0, "brave": 5.0, "tavily": 8.0}   # USD per 1,000 queries; editable in Settings (check your plan)
_gov_lock = threading.Lock()


class SearchUnavailable(Exception):
    pass


def settings(app):
    from ..db import get_setting
    s = json.loads(get_setting(app, "search", "{}") or "{}")
    s.setdefault("provider", "none")
    s.setdefault("approved", False)
    s.setdefault("monthly_cap_usd", 0)
    s.setdefault("gap_s", 20)
    s.setdefault("usd_per_1k", PRICES.get(s["provider"], 0))
    return s


def month_spend(app, provider):
    m = now()[:7]
    r = app.execute("SELECT COALESCE(sum(usd),0) FROM usage WHERE provider=? AND kind='search' AND substr(at,1,7)=?", (provider, m)).fetchone()
    return round(r[0] or 0, 4)


def status(app):
    s = settings(app)
    out = {"provider": s["provider"], "approved": bool(s["approved"]), "cap": s["monthly_cap_usd"], "usd_per_1k": s["usd_per_1k"]}
    out["this_month_usd"] = month_spend(app, s["provider"])
    ok_fail = app.execute("SELECT sum(ok), sum(1-ok) FROM usage WHERE kind='search' AND at>=?",
                          (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3600)),)).fetchone()
    out["last_60_min"] = [ok_fail[0] or 0, ok_fail[1] or 0]
    eng = app.execute("SELECT * FROM search_engines").fetchall()
    out["engines"] = {e["engine"]: {"paused_for_min": max(0, round(((e["paused_until"] or 0) - time.time()) / 60, 1)), "gap_s": s["gap_s"]} for e in eng}
    return out


class Searcher:
    def __init__(self, app_factory, ws, workspace_id):
        self.app_factory, self.ws, self.wid = app_factory, ws, workspace_id
        self.used = 0

    def enabled(self):
        app = self.app_factory()
        try:
            s = settings(app)
        finally:
            app.close()
        if s["provider"] == "none":
            return False
        if s["provider"] in PRICES and not (s["approved"] and float(s["monthly_cap_usd"] or 0) > 0):
            return False
        return True

    def search(self, q):
        """-> list of URLs. Raises SearchUnavailable when the provider is off, capped, paused or failing."""
        app = self.app_factory()
        try:
            s = settings(app)
            prov = s["provider"]
            r = self.ws.execute("SELECT urls, error FROM searches WHERE q=? AND provider=?", (q, prov)).fetchone()
            if r and not r["error"]:
                return [u for u in (r["urls"] or "").split("\n") if u]
            if prov == "none":
                raise SearchUnavailable("no search provider configured")
            if prov in PRICES:
                if not s["approved"]:
                    raise SearchUnavailable(f"{prov} is not approved in Settings")
                cost = float(s["usd_per_1k"] or PRICES[prov]) / 1000
                with _gov_lock:
                    if month_spend(app, prov) + cost > float(s["monthly_cap_usd"] or 0):
                        raise SearchUnavailable(f"{prov} monthly cap ${s['monthly_cap_usd']} reached")
                    with app:
                        app.execute("INSERT INTO usage(at,provider,kind,workspace_id,units,usd,ok,note) VALUES(?,?,?,?,?,?,?,?)",
                                    (now(), prov, "search", self.wid, 1, cost, 1, q[:200]))
                urls, err = self._licensed(prov, q, app)
            elif prov == "mock":
                urls, err = _mock(q)
                with app:
                    app.execute("INSERT INTO usage(at,provider,kind,workspace_id,units,usd,ok,note) VALUES(?,?,?,?,?,?,?,?)",
                                (now(), prov, "search", self.wid, 1, 0, 0 if err else 1, q[:200]))
            elif prov == "duckduckgo":
                urls, err = self._governed("duckduckgo", float(s["gap_s"] or 20), lambda: _ddg(q), app)
            else:
                raise SearchUnavailable(f"unknown provider {prov}")
            self.used += 1
            with self.ws:
                self.ws.execute("INSERT OR REPLACE INTO searches(q,provider,fetched_at,urls,error) VALUES(?,?,?,?,?)",
                                (q, prov, now(), "\n".join(urls), err))
            if err:
                raise SearchUnavailable(f"{prov}: {err}")
            return urls
        finally:
            app.close()

    def _governed(self, engine, gap, fn, app):
        while True:
            with _gov_lock:
                e = app.execute("SELECT * FROM search_engines WHERE engine=?", (engine,)).fetchone()
                t = time.time()
                if e and (e["paused_until"] or 0) > t:
                    raise SearchUnavailable(f"{engine} paused after a block ({round(((e['paused_until']) - t) / 60)} min left)")
                nxt = (e["last_at"] or 0) + gap if e else 0
                if t >= nxt:
                    with app:
                        app.execute("INSERT INTO search_engines(engine,last_at) VALUES(?,?) ON CONFLICT(engine) DO UPDATE SET last_at=excluded.last_at", (engine, t))
                    break
            time.sleep(min(5, nxt - t))
        urls, err = fn()
        with app:
            if err:
                app.execute("UPDATE search_engines SET paused_until=?, fail=fail+1 WHERE engine=?", (time.time() + 1800, engine))
            else:
                app.execute("UPDATE search_engines SET ok=ok+1 WHERE engine=?", (engine,))
            app.execute("INSERT INTO usage(at,provider,kind,workspace_id,units,usd,ok,note) VALUES(?,?,?,?,?,?,?,?)",
                        (now(), engine, "search", self.wid, 1, 0, 0 if err else 1, err[:200] if err else ""))
        return urls, err

    def _licensed(self, prov, q, app):
        from ..secrets import get_secret
        key = get_secret(f"search_{prov}")
        if not key:
            return [], "no API key saved"
        try:
            if prov == "serper":
                req = urllib.request.Request("https://google.serper.dev/search", data=json.dumps({"q": q, "num": 10}).encode(),
                                             headers={"X-API-KEY": key, "Content-Type": "application/json"})
                d = json.loads(urllib.request.urlopen(req, timeout=20).read())       # nosec B310 fixed https URL
                return [x.get("link") for x in d.get("organic", []) if x.get("link")], ""
            if prov == "brave":
                req = urllib.request.Request("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "count": 10}),
                                             headers={"X-Subscription-Token": key, "Accept": "application/json"})
                d = json.loads(urllib.request.urlopen(req, timeout=20).read())       # nosec B310
                return [x.get("url") for x in (d.get("web") or {}).get("results", []) if x.get("url")], ""
            if prov == "tavily":
                req = urllib.request.Request("https://api.tavily.com/search", data=json.dumps({"api_key": key, "query": q, "max_results": 10}).encode(),
                                             headers={"Content-Type": "application/json"})
                d = json.loads(urllib.request.urlopen(req, timeout=20).read())       # nosec B310
                return [x.get("url") for x in d.get("results", []) if x.get("url")], ""
        except Exception as e:
            with app:
                app.execute("UPDATE usage SET ok=0, note=? WHERE id=(SELECT max(id) FROM usage WHERE provider=?)", (f"{type(e).__name__}"[:200], prov))
            return [], f"{type(e).__name__}: {str(e)[:120]}"
        return [], "unsupported"


def _ddg(q):
    try:
        req = urllib.request.Request("https://html.duckduckgo.com/html/", data=urllib.parse.urlencode({"q": q}).encode(),
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; ICPQualifier/1.0)"})
        body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")      # nosec B310 fixed https URL
    except Exception as e:
        return [], f"{type(e).__name__}"
    if "result__a" not in body and "No results" not in body:
        return [], "blocked or empty result page"
    import html as h
    return [urllib.parse.parse_qs(urllib.parse.urlparse(h.unescape(x)).query).get("uddg", [h.unescape(x)])[0]
            for x in re.findall(r'class="result__a" href="([^"]+)"', body)], ""


def _mock(q):
    path = os.environ.get("ICPQ_SEARCH_FIXTURES")
    if not path:
        return [], "no fixtures"
    data = json.load(open(path))
    if data.get("__block__"):
        return [], "mock block"
    for k, v in data.items():
        if k in q:
            return v, ""
    return [], ""
