"""Decision-makers for qualified accounts.

Sources (Settings → Contacts, per workspace):
  site     (default, free) people named on the company's OWN website (team / leadership / about / contact pages) with a
           job title next to the name; e-mails and phone numbers only when the site itself publishes them. Status VERIFIED
           (source page on the company's domain). E-mails are never guessed or constructed.
  hunter   Hunter.io domain search with the workspace's API key (needs approval + monthly cap); status PROVIDER with the
           provider's own confidence score.
  apollo   Apollo.io people search by domain and the profile's buying-committee titles (same approval + cap rules).
Each person is matched against the profile's buying committee (titles / departments)."""
import json
import re
import urllib.parse
import urllib.request

from ..util import host, now, same_site

TEAM_PATHS = ["/about", "/about-us", "/team", "/our-team", "/leadership", "/management", "/people", "/staff", "/contact", "/contact-us"]
GENERIC_TITLES = ["chief executive officer", "ceo", "chief operating officer", "coo", "chief financial officer", "cfo", "chief technology officer", "cto",
                  "chief information officer", "cio", "chief marketing officer", "cmo", "chief revenue officer", "cro", "president", "founder",
                  "co-founder", "owner", "managing director", "general manager", "vice president", "vp", "svp", "evp", "director", "head of",
                  "manager", "principal", "partner", "administrator", "superintendent", "chair"]
NAME = r"(?:Dr\.?\s+)?[A-Z][a-z'’\-]+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z'’\-]+){1,2}"
STOPNAME = re.compile(r"^(Contact|About|Our|The|Read|Learn|Meet|View|Privacy|Terms|Home|Find|Book|Request|Get|Join|New|All|More|Board|Team|Leadership|Executive|Senior|Customer|Client)\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")
GENERIC_LOCAL = re.compile(r"^(info|contact|hello|sales|support|admin|office|help|team|marketing|press|media|hr|jobs|careers|billing|noreply|no-reply|webmaster)$", re.I)


def settings(app, wid=None):
    from ..db import get_setting
    s = json.loads(get_setting(app, f"contacts:w{int(wid)}" if wid else "contacts", "{}") or "{}")
    s.setdefault("provider", "site")
    s.setdefault("approved", False)
    s.setdefault("monthly_cap_usd", 0)
    s.setdefault("usd_per_lookup", 0.05)
    s.setdefault("per_company", 5)
    return s


def committee_match(title, cfg):
    t = (title or "").lower()
    for x in cfg["committee"]["titles"] + cfg["committee"]["departments"]:
        words = [w for w in re.findall(r"[a-z]+", x.lower()) if len(w) > 2]
        if words and all(w in t for w in words):
            return x
    return ""


def title_rx(cfg):
    titles = sorted({*(t.lower() for t in cfg["committee"]["titles"]), *GENERIC_TITLES}, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in titles) + r")\b[\w ,&/\-]{0,60}", re.I)


def from_site(cfg, pages, acct):
    """People named with a title on the company's own pages, plus e-mails/phones the site publishes."""
    trx = title_rx(cfg)
    people, emails = {}, []
    for p in pages:
        url = p.get("final_url") or p["url"]
        if not same_site(url, acct.get("domain") or ""):
            continue
        text = p.get("text") or ""
        html = p.get("html") or ""
        for e in set(EMAIL.findall(text) + re.findall(r"mailto:([^\"'?>\s]+)", html)):
            e = urllib.parse.unquote(e).strip().lower()
            if same_site("http://" + e.split("@")[-1], acct.get("domain") or "") and not e.endswith((".png", ".jpg")):
                emails.append((e, url))
        flat = re.sub(r"\s*\n\s*", " | ", text)
        for m in re.finditer(NAME, flat):
            name = m.group(0).strip()
            if STOPNAME.match(name) or len(name) > 40 or trx.fullmatch(name):
                continue
            after, before = flat[m.end():m.end() + 90], flat[max(0, m.start() - 70):m.start()]
            t = trx.search(after)
            if not (t and t.start() <= 25):
                t = trx.search(before)
                if not (t and len(before) - t.end() <= 12):
                    continue
            title = re.sub(r"\s+", " ", t.group(0)).strip(" ,-–|")
            if not title or name.lower() in title.lower() or title.lower() in name.lower():
                continue
            k = name.lower()
            if k not in people:
                people[k] = {"name": name, "title": title[:80], "email": "", "phone": "", "source_url": url, "status": "VERIFIED",
                             "source": "company website", "confidence": "named with title on the company's own page"}
                ph = PHONE.search(after)
                if ph:
                    people[k]["phone"] = ph.group(0)
    out = list(people.values())
    for e, url in emails:
        local = e.split("@")[0]
        hit = None
        for pp in out:
            parts = [w.lower() for w in re.findall(r"[A-Za-z]+", pp["name"]) if w.lower() not in ("dr",)]
            if len(parts) >= 2 and (local in (parts[0], parts[-1], parts[0] + "." + parts[-1], parts[0][0] + parts[-1], parts[0] + parts[-1], parts[0] + "_" + parts[-1])):
                hit = pp
                break
        if hit and not hit["email"]:
            hit["email"] = e
        elif not hit and GENERIC_LOCAL.match(local) and not any(c["email"] == e for c in out):
            out.append({"name": "", "title": "General inbox", "email": e, "phone": "", "source_url": url, "status": "VERIFIED", "source": "company website",
                        "confidence": "published on the company's own page"})
    for c in out:
        c["committee"] = committee_match(c["title"], cfg)
    out.sort(key=lambda c: (not c["committee"], not c["name"], not c["email"]))
    return out


def _charge(app, wid, s, prov, note):
    cost = float(s.get("usd_per_lookup") or 0)
    m = app.execute("SELECT COALESCE(sum(usd),0) FROM usage WHERE kind='contacts' AND provider=? AND substr(at,1,7)=? AND workspace_id IS ?", (prov, now()[:7], wid)).fetchone()[0]
    if m + cost > float(s.get("monthly_cap_usd") or 0):
        raise RuntimeError(f"{prov} monthly cap ${s.get('monthly_cap_usd')} reached")
    with app:
        cur = app.execute("INSERT INTO usage(at,provider,kind,workspace_id,units,usd,ok,note) VALUES(?,?,?,?,?,?,?,?)", (now(), prov, "contacts", wid, 1, cost, 0, note[:200]))
    return cur.lastrowid


def from_provider(app, wid, cfg, acct):
    """-> (contacts, note). Never runs unless the workspace approved the provider with a cap and saved a key."""
    from ..secrets import get_secret
    s = settings(app, wid)
    prov = s["provider"]
    if prov == "site":
        return [], ""
    if not s["approved"] or float(s["monthly_cap_usd"] or 0) <= 0:
        return [], f"{prov} not approved in Settings"
    key = get_secret(f"contacts_{prov}_w{int(wid)}" if wid else f"contacts_{prov}")
    if not key:
        return [], f"no {prov} API key saved"
    dom = acct.get("domain") or ""
    try:
        uid = _charge(app, wid, s, prov, dom)
    except RuntimeError as e:
        return [], str(e)
    out = []
    try:
        if prov == "hunter":
            d = json.loads(urllib.request.urlopen("https://api.hunter.io/v2/domain-search?" + urllib.parse.urlencode(
                {"domain": dom, "api_key": key, "limit": int(s.get("per_company") or 5), "type": "personal"}), timeout=25).read())   # nosec B310
            for e in (d.get("data") or {}).get("emails", []):
                out.append({"name": " ".join(filter(None, [e.get("first_name"), e.get("last_name")])), "title": e.get("position") or "",
                            "email": e.get("value") or "", "phone": e.get("phone_number") or "", "source": "Hunter.io",
                            "source_url": next((x.get("uri") for x in e.get("sources") or [] if x.get("uri")), ""), "status": "PROVIDER",
                            "confidence": f"Hunter confidence {e.get('confidence')}%" + (" · verified" if (e.get("verification") or {}).get("status") == "valid" else "")})
        elif prov == "apollo":
            body = {"q_organization_domains_list": [dom], "person_titles": cfg["committee"]["titles"][:10], "per_page": int(s.get("per_company") or 5)}
            req = urllib.request.Request("https://api.apollo.io/api/v1/mixed_people/search", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Api-Key": key, "Cache-Control": "no-cache"})
            d = json.loads(urllib.request.urlopen(req, timeout=25).read())     # nosec B310
            for p in d.get("people") or []:
                em = p.get("email") or ""
                out.append({"name": p.get("name") or "", "title": p.get("title") or "", "email": "" if "not_unlocked" in em else em, "phone": "",
                            "source": "Apollo.io", "source_url": p.get("linkedin_url") or "", "status": "PROVIDER",
                            "confidence": f"Apollo email status {p.get('email_status') or 'unknown'}"})
        with app:
            app.execute("UPDATE usage SET ok=1 WHERE id=?", (uid,))
    except Exception as e:
        with app:
            app.execute("UPDATE usage SET note=? WHERE id=?", (f"{type(e).__name__}: {e}"[:200], uid))
        return [], f"{prov} lookup failed: {type(e).__name__}"
    for c in out:
        c["committee"] = committee_match(c["title"], cfg)
    return out, f"{len(out)} from {prov}"


def gather(app, wid, cfg, fetcher, pages, acct, use_provider=True):
    """Own-site people (fetching the usual team/contact pages if they weren't crawled yet), then the provider if configured."""
    have = {p.get("final_url") or p["url"] for p in pages}
    pages = list(pages)
    dom = acct.get("domain") or ""
    for path in TEAM_PATHS:
        if len(pages) > 40:
            break
        u = f"https://{dom}{path}"
        if u in have:
            continue
        rec = fetcher.get(u)
        if rec.get("status") == 200 and rec.get("text") and same_site(rec.get("final_url") or u, dom):
            pages.append(rec)
    site = from_site(cfg, pages, acct)
    note = f"{len(site)} on the company's own site"
    prov, pnote = (from_provider(app, wid, cfg, acct) if use_provider else ([], ""))
    seen = {(c["name"].lower(), c["email"]) for c in site}
    merged = site + [c for c in prov if (c["name"].lower(), c["email"]) not in seen]
    per = int(settings(app, wid).get("per_company") or 5)
    return merged[: max(per, len([c for c in site if c["committee"]]))], "; ".join(filter(None, [note, pnote])), host(dom)
