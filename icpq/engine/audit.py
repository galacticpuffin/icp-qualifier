"""Evidence audit of every qualified (A/B/C) and held account, as the original dashboards show it (EVIDENCE PASS /
NEEDS REVIEW / FAIL). It re-opens the cited page (from the page cache, or live when asked) and checks:

  FAIL          a hard requirement is missing: fit not verified, no evidence/URL, a search-result URL, the evidence is
                on another organisation's domain (when the profile requires its own domain), or the quote is not on the
                page it cites
  NEEDS REVIEW  the evidence is on the page but can't be proven mechanically: no explicit proof marker (when the signal
                defines markers), or the page can't be read now
  PASS          everything above holds
Audits only report; they never change a verdict (READY requires PASS)."""
import re

from ..util import host, norm_text, registrable

SEARCH_URL = re.compile(r"google\.[a-z.]+/search|bing\.com/search|duckduckgo|search\.yahoo|/search\?q=", re.IGNORECASE)


def audit(icp, ws, acct, v, fetcher=None):
    out = {"s": "PASS", "r": "", "q": (v.get("evidence") or "")[:500], "u": v.get("url") or "", "w": ""}
    fails, reviews = [], []
    if v.get("core") != "Yes":
        fails.append("fit not verified")
    if not (v.get("evidence") or "").strip() or not (v.get("url") or "").startswith("http"):
        fails.append("evidence or source URL missing")
    url = v.get("url") or ""
    if SEARCH_URL.search(url):
        fails.append("cites a search-results page")
    dom = acct.get("domain") or ""
    if icp.cfg["evidence"]["own_domain_required"] and dom and url.startswith("http") and registrable(host(url)) != registrable(host(dom)):
        fails.append(f"evidence on another domain ({host(url)})")
    if url.startswith("http") and not fails:
        r = ws.execute("SELECT text, fetched_at, status FROM pages WHERE url=? OR final_url=? ORDER BY status=200 DESC LIMIT 1", (url, url)).fetchone()
        if (not r or r["status"] != 200) and fetcher is not None:
            rec = fetcher.get(url)
            r = {"text": rec.get("text"), "fetched_at": rec.get("fetched_at"), "status": rec.get("status")}
        if not r or r["status"] != 200 or not r["text"]:
            reviews.append("cited page can't be read now")
        else:
            page, q = norm_text(r["text"]), norm_text(v.get("evidence"))
            core = q[30:-30] if len(q) > 90 else q          # the window edges may be cut mid-word
            if core and core in page:
                out["w"] = f"cited page (fetched {str(r['fetched_at'])[:10]})"
            else:
                fails.append("quote not found on the cited page")
    sig = next((icp.by_id[k] for k, x in (v.get("signals") or {}).items() if x.get("status") == "VERIFIED" and icp.by_id.get(k, {}).get("requirement") == "mandatory"), None)
    mk = (sig and sig["_mk"]) or icp.audit_marker
    if icp.cfg["evidence"]["require_marker_for_ready"] and mk is not None and not fails and not mk.search(v.get("evidence") or ""):
        reviews.append("no explicit proof marker in the quote")
    if fails:
        out["s"], out["r"] = "FAIL", "; ".join(fails + reviews)
    elif reviews:
        out["s"], out["r"] = "NEEDS REVIEW", "; ".join(reviews)
    return out
