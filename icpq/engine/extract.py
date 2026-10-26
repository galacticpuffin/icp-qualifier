"""Evidence extraction: profile signals -> quoted passages from fetched pages, each with a status.

  VERIFIED   the passage is on the company's own domain (or an allowed independent page that names it), is not a
             rejected page type, and meets the profile's confidence standard
  INFERRED   a real passage that falls short of the standard (lower confidence, independent page, hedged wording)
  REJECTED   kept for transparency with the reason (negative context, content/marketing page, vendor copy, template, ...)
Only VERIFIED evidence can satisfy a mandatory signal. Nothing is ever written that isn't on the page."""
import re
import urllib.parse

from ..util import host, ident_words, same_site

WINDOW = 180
PER_SIGNAL = 6
USAGE = re.compile(r"powered by|built (?:on|with)|we use|we're using|using|runs on|integrat\w+ with|login|log in|sign in|portal|"
                   r"partner(?:ed)? with|implemented|migrat\w+ to|switched to|via|through", re.IGNORECASE)
HEDGE = re.compile(r"\be\.g\.|\bfor example\b|\bsuch as\b|\bmay (?:also )?(?:use|send|contact)\b|\bif applicable\b|\bwhen permissible\b", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}|\[company name\]|lorem ipsum", re.IGNORECASE)
CONTENT_HOST = re.compile(r"^(community|forums?|blog|news|learn|developers?|docs|academy|insights|support\.[a-z]+\.)", re.IGNORECASE)


def _window(text, m):
    a, b = max(0, m.start() - WINDOW), min(len(text), m.end() + WINDOW)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def use_cases(icp, s, window):
    tags = [s["use_case"]] if s.get("use_case") else []
    for tag, rx in icp.use_cases:
        if rx.search(window) and tag not in tags:
            tags.append(tag)
    return tags


def org_tokens(acct):
    toks = set(ident_words(acct.get("name"))) | {t for t in re.split(r"[.\-]", acct.get("domain") or "") if len(t) >= 4}
    toks.discard("www")
    return toks


def find(icp, text, url, acct):
    """All signal passages on one page (positive, negative and info signals)."""
    out, seen = [], set()
    toks = org_tokens(acct)
    for s in icp.signals:
        rx = s["_rx"]
        if rx is None:
            continue
        n = 0
        for m in rx.finditer(text or ""):
            w = _window(text, m)
            key = (s["id"], w[:90])
            if key in seen:
                continue
            seen.add(key)
            mk = bool(s["_mk"] and s["_mk"].search(w))
            ev = {"signal_id": s["id"], "label": s["label"], "kind": s["requirement"], "category": s["category"], "url": url, "snippet": w,
                  "match": m.group(0)[:120], "confidence": "high" if (mk or s["confidence"] == "high") else "medium", "marker": mk,
                  "use_cases": use_cases(icp, s, w), "mentions_org": bool(toks) and any(t in w.lower() for t in toks)}
            if s["requirement"] != "negative" and icp.negative and icp.negative.search(w):
                ev["status"], ev["reason"] = "REJECTED", f"ignored passage (near “{icp.negative.search(w).group(0)}”)"
            out.append(ev)
            n += 1
            if n >= PER_SIGNAL:
                break
    return out


def problem(icp, ev, acct):
    """Why this passage can't be VERIFIED evidence for the account (None if it can). Port of the original gate checks,
    with every vocabulary coming from the profile."""
    E = icp.cfg["evidence"]
    u = urllib.parse.urlparse(ev["url"] if ev["url"].startswith("http") else "")
    dom = acct.get("domain") or ""
    offsite = bool(dom and u.netloc and not same_site(ev["url"], dom))
    if offsite:
        scope = icp.by_id.get(ev["signal_id"], {}).get("scope")
        if E["own_domain_required"] and scope != "any_site":
            return "evidence is on another site (" + host(ev["url"]) + "), not the company's own (" + dom + ")", True
        if not ev.get("mentions_org"):
            return "independent page does not name the company", True
    if dom and u.netloc and not offsite:
        h, d = host(ev["url"]), host(dom)
        if re.search(r"^[a-z0-9-]+\.(?:gov|edu|us|mil)$", d) and h != d and not h.endswith("." + d):
            return f"evidence is on another organisation's site ({h}) under the shared {d} domain", True
    if E["exclude_content_pages"] and (CONTENT_HOST.search(u.netloc.lower()) or (icp.content_path and icp.content_path.search(u.path))):
        return "evidence page is content/news/marketing, not the company's own statement", False
    if PLACEHOLDER.search(ev["snippet"]):
        return "evidence is an unfilled website template", False
    if icp.vendor_copy and icp.vendor_copy.search(ev["snippet"]) and ev["kind"] in ("mandatory", "preferred"):
        return "reads as vendor copy aimed at its own customers, not the company's own use", False
    if HEDGE.search(ev["snippet"]) and not ev["marker"]:
        return "hedged wording (e.g. / such as / may), no explicit proof", False
    if E["min_confidence"] == "high" and ev["confidence"] != "high":
        return "below the profile's confidence standard (no explicit proof marker)", False
    return None, False


def grade(icp, evs, acct):
    """Assign VERIFIED / INFERRED / REJECTED to each passage (in place) and return them, best first."""
    for ev in evs:
        if ev.get("status") == "REJECTED":
            continue
        p, hard = problem(icp, ev, acct)
        if p is None:
            ev["status"], ev["reason"] = "VERIFIED", "own-site passage" + (" with explicit proof marker" if ev["marker"] else "")
        elif hard and not ev.get("mentions_org"):
            ev["status"], ev["reason"] = "REJECTED", p
        else:       # a real passage that misses the standard (or an independent page that names the company)
            ev["status"], ev["reason"] = "INFERRED", p
    rank = {"VERIFIED": 0, "INFERRED": 1, "REJECTED": 2}
    evs.sort(key=lambda e: (rank[e["status"]], not e["marker"], e["confidence"] != "high", not e["mentions_org"], not e["use_cases"]))
    return evs


def stack(icp, pages, acct):
    """Technologies / competitors / target technology / channel signals from the company's own pages.
    -> dict of {kind: {name: (status, snippet, url)}} where status is VERIFIED (usage context or page markup) or INFERRED (mention)."""
    out = {"tech": {}, "competitor": {}, "target": {}, "channel": []}
    groups = (("tech", icp.technologies), ("competitor", icp.competitors), ("target", icp.target_tech))
    for p in pages:
        url, text, html = p.get("final_url") or p["url"], p.get("text") or "", p.get("html") or ""
        if not same_site(url, acct.get("domain") or ""):
            continue
        for kind, d in groups:
            for name, rx in d.items():
                if name in out[kind] and out[kind][name][0] == "VERIFIED":
                    continue
                m = rx.search(text)
                markup = bool(re.search(r"(?:src|href)=[\"'][^\"']*" + re.escape(re.sub(r"\W+", "", name.lower())) + r"[^\"']*[\"']", html.lower())) if len(name) >= 4 else False
                if not m and not markup:
                    continue
                w = _window(text, m) if m else f"page markup loads {name}"
                st = "VERIFIED" if markup or (m and USAGE.search(w) and not HEDGE.search(w)) else "INFERRED"
                if icp.vendor_copy and m and icp.vendor_copy.search(w):
                    st = "INFERRED"
                if name not in out[kind] or st == "VERIFIED":
                    out[kind][name] = (st, w, url)
        if icp.channel:
            m = icp.channel.search(text)
            if m and len(out["channel"]) < 3:
                out["channel"].append((_window(text, m), url))
    return out
