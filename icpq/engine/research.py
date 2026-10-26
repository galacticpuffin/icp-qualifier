"""Research one account, driven entirely by the profile's research plan.

1. Fetch the company's own home page (cached; a cached page is never refetched).
2. Follow same-site links whose URL or anchor text matches the profile's link hints / signal phrases (strong hints first).
3. Sitemap pages whose path matches the profile's sitemap hints; then the profile's common paths.
4. Only when the qualification rule isn't yet met on verified evidence (or always, if the profile says so): the profile's
   search queries through the configured provider. Results are candidate URLs on the company's own site only; each is
   fetched and must contain the evidence itself. If a needed search can't run, the account stays RETRY (not complete).
Accounts without a website: website discovery (search + identity check on the candidate home page) when enabled."""
import re
import urllib.parse

from ..util import host, ident_words, same_site
from . import extract
from .fetch import SKIP_EXT, parse
from .search import SearchUnavailable

SKIP_DISCOVERY = re.compile(r"(linkedin|facebook|twitter|x\.com|instagram|youtube|wikipedia|yelp|bbb\.org|crunchbase|zoominfo|bloomberg|"
                            r"glassdoor|indeed|mapquest|yellowpages|manta|dnb\.com|opencorporates|google\.|bing\.|duckduckgo)", re.IGNORECASE)


def identity_ok(name, pages):
    words = ident_words(name)
    if not words:
        return None
    blob = " ".join(((p.get("text") or "")[:200000] + " " + (p.get("title") or "")).lower() for p in pages)
    hits = [w for w in words if w in blob]
    return len(hits) >= max(1, (len(words) + 1) // 2)


def discover(acct, fetcher, searcher):
    """-> (domain or '', note). Never guesses: the candidate site must name the company."""
    q = f"\"{acct['name']}\" official website" + (f" {acct['location']}" if acct.get("location") else "")
    try:
        urls = searcher.search(q)
    except SearchUnavailable as e:
        return "", f"website discovery not run: {e}", q
    for u in urls[:6]:
        h = host(u)
        if not h or SKIP_DISCOVERY.search(h):
            continue
        rec = fetcher.get(f"https://{h}/")
        if rec["status"] == 200 and identity_ok(acct["name"], [rec]):
            return h, f"found by search; home page names {acct['name']}", q
    return "", "no candidate website named the company", q


def collect(icp, acct, fetcher, searcher, cache_only=False):
    R = icp.cfg["research"]
    domain = acct["domain"]
    log = {"pages": [], "sitemap": [], "search": [], "errors": []}
    evs, pages = [], []

    def take(url, via):
        if url in {p["url"] for p in pages} or len(log["pages"]) >= R["max_pages"]:
            return None
        rec = fetcher.get(url)
        log["pages"].append({"url": url, "status": rec["status"], "error": (rec.get("error") or "")[:80], "via": via})
        fu = rec.get("final_url") or url
        if rec["status"] == 200 and rec.get("text") and (same_site(fu, domain) or via == "search-any"):
            pages.append(rec)
            evs.extend(extract.find(icp, rec["text"], fu, acct))
            return rec
        return None

    def gate_met():
        g = extract.grade(icp, [dict(e) for e in evs], acct)
        return icp.gate({e["signal_id"] for e in g if e["status"] == "VERIFIED"})[0]

    home = None
    for u in (f"https://{domain}/", f"https://www.{domain}/", f"http://{domain}/"):
        home = take(u, "home")
        if home:
            break
    if home:
        base = home.get("final_url") or f"https://{domain}/"
        pu = urllib.parse.urlparse(base)
        root = f"{pu.scheme}://{pu.netloc}"
        cands = []
        for href, label in parse(home.get("html") or "")[1]:
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            u = urllib.parse.urljoin(base, href).split("#")[0]
            if SKIP_EXT.search(u) or not same_site(u, domain):
                continue
            hint = f"{urllib.parse.unquote(u)} {label}".replace("-", " ").replace("_", " ")
            if icp.link_hint and icp.link_hint.search(hint):
                cands.append((0 if icp.link_strong and icp.link_strong.search(hint) else 1, u))
        seen, n = set(), 0
        for _, u in sorted(cands):
            if u in seen or n >= R["link_budget"]:
                continue
            seen.add(u)
            take(u, "link")
            n += 1
        if not gate_met():
            log["sitemap"] = fetcher.sitemap_urls(root, domain, icp.sitemap_hint)
            for u in log["sitemap"]:
                take(u, "sitemap")
        if not gate_met():
            for p in R["common_paths"]:
                take(root + (p if p.startswith("/") else "/" + p), "common-path")
    else:
        log["errors"].append("home page unreachable")
    # search: only for what the crawl couldn't verify (or always, per profile)
    search_state = "off"
    queries = [q for q in R["search_queries"] if q] if R["search_when"] != "never" else []
    if queries and (R["search_when"] == "always" or not gate_met()):
        search_state = "done"
        for q in queries[:4]:
            qq = q.replace("{domain}", domain).replace("{name}", acct.get("name") or "")
            try:
                raw = searcher.search(qq)
            except SearchUnavailable as e:
                search_state = "pending"
                log["search"].append({"q": qq, "error": str(e)[:160]})
                break
            urls = [u for u in raw if same_site(u, domain) and not SKIP_EXT.search(u)]
            log["search"].append({"q": qq, "results": len(raw), "candidates": urls[:6]})
            for u in urls[:4]:
                take(u, "search")
            if R["search_when"] != "always" and gate_met():
                break
    elif queries:
        search_state = "not_needed"
    stk = extract.stack(icp, pages, acct)
    graded = extract.grade(icp, evs, acct)
    return {"evidence": graded, "pages": pages, "log": log, "crawl_ok": bool(home), "search_state": search_state, "stack": stk}
