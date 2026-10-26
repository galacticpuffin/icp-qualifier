"""Uploaded list -> companies. Port of the original's provisional, verified website-level merge.

* Rows are grouped by website host (rows without a website: by normalised name).
* A row is LINKED to its website when its name visibly belongs to that organisation (a domain token appears in the name,
  or the name's words / initials abbreviate into it: "University of Wyoming" -> uwyo).
* Same company name on several rows -> one company; the other rows stay visible as MERGED duplicates (reconciliation).
* Several linked names on one website -> the shortest linked name is the parent; the others are UNITS routed to it
  (never qualified on the parent's evidence), unless they look like franchisees/agents/dealers or separate government
  agencies (independent buying entities that need their own evidence).
* A name with no visible link to its website -> SPLIT_OUT (its own account, sent to an entity check).
* The same name with different websites -> NAME_CONFLICT (entity check).
* An optional "parent company" column links subsidiaries to parents found in the same list.
Every original row is kept in `members` with its spreadsheet row number. Nothing here reads the web."""
import csv
import io
import re
from collections import OrderedDict

from .util import domain_from, jdump, norm_name, now, parse_number

SYNONYMS = {
    "name": ["company", "company name", "account", "account name", "organization", "organisation", "name", "business", "business name"],
    "website": ["website", "domain", "url", "web site", "company website", "site", "homepage", "web"],
    "email": ["email", "e-mail", "email address", "contact email"],
    "industry": ["industry", "sector", "vertical", "category", "naics description", "sic description"],
    "employees": ["employees", "employee count", "headcount", "# employees", "number of employees", "company size", "size", "staff"],
    "revenue": ["revenue", "annual revenue", "sales", "revenue (usd)", "annual sales", "turnover"],
    "location": ["location", "hq", "headquarters", "country", "state", "city", "hq location", "region"],
    "parent": ["parent", "parent company", "parent account", "ultimate parent", "parent organization"],
}
STOP = {"of", "the", "and", "at", "for", "in", "a", "an", "&", "inc", "llc", "ltd", "co", "corp", "corporation", "company", "pllc", "pc", "lp", "llp", "plc"}
GENERIC_TOK = {"www", "com", "org", "net", "edu", "gov", "us", "co", "io", "inc", "llc", "corp", "info", "biz", "the", "and", "group", "online",
               "site", "web", "home", "app", "global", "usa", "america", "american", "services"}
INDEPENDENT = re.compile(r"\b(franchisee?|agent|agency|agencies|realty|realtors?|brokerage|dealer(?:ship)?|owner[- ]operated|independently owned)\b", re.IGNORECASE)
GOV = re.compile(r"(\.gov$|\.mil$|\.state\.[a-z]{2}\.us$|^[a-z]{2}\.us$)")


def read_table(text):
    """CSV text -> (header, rows). Sniffs the delimiter; finds the header row (first row with >= 2 non-empty cells
    that looks like labels) so title rows above the table are skipped."""
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect)]
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("The file has no rows.")
    hi = 0
    for i, r in enumerate(rows[:15]):
        cells = [c.strip().lower() for c in r if c.strip()]
        if len(cells) >= 2 and any(any(c == s or c.startswith(s) for s in SYNONYMS["name"] + SYNONYMS["website"]) for c in cells):
            hi = i
            break
    header = [c.strip() or f"Column {j + 1}" for j, c in enumerate(rows[hi])]
    width = len(header)
    body = [(hi + 2 + k, (r + [""] * width)[:width]) for k, r in enumerate(rows[hi + 1:])]
    return header, body


def suggest_mapping(header):
    low = [h.strip().lower() for h in header]
    out = {}
    for field, syn in SYNONYMS.items():
        for s in syn:
            hit = next((header[i] for i, h in enumerate(low) if h == s), None) or next((header[i] for i, h in enumerate(low) if s in h and len(h) < 40), None)
            if hit and hit not in out.values():
                out[field] = hit
                break
    return out


def nn(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def domain_tokens(domain):
    parts = re.split(r"[.\-]", (domain or "").lower())
    parts = parts[:-1] if len(parts) > 1 else parts          # drop the TLD
    return [p for p in parts if len(p) >= 2 and p not in GENERIC_TOK]


def linked(name, tokens):
    n = nn(name)
    if not n:
        return False
    words = [w for w in re.findall(r"[a-z0-9]+", str(name).lower()) if w not in STOP]
    initials = "".join(w[0] for w in words)
    for t in tokens:
        if len(t) == 2:
            if len(initials) >= 2 and initials.startswith(t):
                return True
            continue
        if t in n or (len(n) >= 4 and n in t):
            return True
        if any(len(w) >= 3 and t.startswith(w) for w in words):
            return True
        if sum(1 for w in words if len(w) >= 3 and w[:3] in t) >= 2:
            return True
        if len(initials) >= 3 and initials in t:
            return True
        if any(len(w) >= 5 and w[:5] in t for w in words):
            return True
        if len(initials) >= 2 and t.startswith(initials[:2]) and any(len(w) >= 3 and w[:3] in t for w in words):
            return True
    return False


def records(header, body, mapping):
    col = {f: header.index(c) for f, c in mapping.items() if c in header}
    if "name" not in col and "website" not in col:
        raise ValueError("Map at least the Company name or the Website column.")
    get = lambda r, f: (r[col[f]] if f in col else "").strip()
    out, blank = [], 0
    for rown, r in body:
        name = get(r, "name")
        dom = domain_from(get(r, "website")) or domain_from(get(r, "email"))
        if not name and not dom:
            blank += 1
            continue
        extra = {h: r[i] for i, h in enumerate(header) if i not in col.values() and str(r[i]).strip()}
        out.append({"row": rown, "name": name or dom, "domain": dom, "industry": get(r, "industry"), "employees": parse_number(get(r, "employees")),
                    "revenue": parse_number(get(r, "revenue")), "location": get(r, "location"), "parent": get(r, "parent"), "extra": extra})
    return out, blank


def group(recs):
    """-> list of company dicts: primary record + members + relation."""
    groups = OrderedDict()
    for r in recs:
        groups.setdefault(r["domain"] or "n:" + norm_name(r["name"]), []).append(r)
    companies = []
    for key, ms in groups.items():
        if key.startswith("n:"):
            companies.append({"primary": ms[0], "members": ms, "relation": "", "notes": "no website in the list"})
            continue
        toks = domain_tokens(key)
        by_name = OrderedDict()
        for m in ms:
            by_name.setdefault(norm_name(m["name"]), []).append(m)
        names = list(by_name.values())
        links = [linked(g[0]["name"], toks) for g in names]
        lk = [i for i, ok in enumerate(links) if ok]
        if len(names) == 1:
            ok = links[0]
            companies.append({"primary": names[0][0], "members": names[0], "relation": "" if ok else "SINGLE_MISMATCH",
                              "notes": "" if ok else f"name has no visible link to {key}: the site must name the company"})
            continue
        pi = min(lk, key=lambda i: (len(names[i][0]["name"]), i)) if lk else 0
        parent = {"primary": names[pi][0], "members": names[pi], "relation": "", "notes": f"parent of {len(names) - 1} other name(s) on {key}"}
        companies.append(parent)
        for i, g in enumerate(names):
            if i == pi:
                continue
            nm = g[0]["name"]
            if INDEPENDENT.search(nm):
                rel = "FRANCHISEE"
            elif GOV.search(key) and "k12" not in key:
                rel = "AGENCY"
            elif links[i]:
                rel = "UNIT"
            elif lk:
                rel = "SPLIT_OUT"
            else:
                rel = "SUBSIDIARY"
            companies.append({"primary": g[0], "members": g, "relation": rel, "parent": parent, "notes": f"shares {key} with {parent['primary']['name']}"})
    # same name, different websites
    seen = {}
    for c in companies:
        if c["primary"]["domain"]:
            seen.setdefault(norm_name(c["primary"]["name"]), set()).add(c["primary"]["domain"])
    for c in companies:
        n = norm_name(c["primary"]["name"])
        if c["primary"]["domain"] and len(seen.get(n, ())) > 1 and not c["relation"]:
            c["relation"], c["notes"] = "NAME_CONFLICT", f"same name listed with websites {', '.join(sorted(seen[n]))}"
    return companies


def ingest(ws, list_id, header, body, mapping):
    recs, blank = records(header, body, mapping)
    comps = group(recs)
    by_norm = {norm_name(c["primary"]["name"]): c for c in comps}
    stats = {"rows_in_file": len(body), "blank_rows": blank, "companies": len(comps), "merged_rows": 0, "routed_units": 0,
             "entity_checks": 0, "no_website": 0, "at": now()}
    with ws:
        ws.execute("DELETE FROM research WHERE account_id IN (SELECT id FROM accounts WHERE list_id=?)", (list_id,))
        ws.execute("DELETE FROM verdicts WHERE account_id IN (SELECT id FROM accounts WHERE list_id=?)", (list_id,))
        ws.execute("DELETE FROM evidence WHERE account_id IN (SELECT id FROM accounts WHERE list_id=?)", (list_id,))
        ws.execute("DELETE FROM accounts WHERE list_id=?", (list_id,))
        ids = {}
        for order, c in enumerate(comps, start=1):
            p = c["primary"]
            rel, parent_id, notes = c["relation"], None, c["notes"]
            if p.get("parent"):
                pc = by_norm.get(norm_name(p["parent"]))
                if pc is not None and pc is not c:
                    notes = (notes + "; " if notes else "") + f"parent company in list: {pc['primary']['name']}"
                    if pc["primary"]["domain"] == p["domain"] and p["domain"]:
                        rel = rel or "UNIT"
            mem = [{"row": m["row"], "name": m["name"]} for m in c["members"]]
            cur = ws.execute("""INSERT INTO accounts(list_id,key,name,domain,industry,employees,revenue,location,extra,members,is_primary,
                                company_order,merge_notes,flags,relation,website_source) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)""",
                             (list_id, f"L{list_id}R{p['row']}", p["name"], p["domain"], p["industry"], p["employees"], p["revenue"], p["location"],
                              jdump(p["extra"]), jdump(mem), order, notes, jdump([]), rel, "list" if p["domain"] else ""))
            aid = cur.lastrowid
            ids[id(c)] = aid
            ws.execute("UPDATE accounts SET company_id=? WHERE id=?", (aid, aid))
            ws.execute("INSERT INTO research(account_id,state) VALUES(?, 'pending')", (aid,))
            for m in c["members"][1:]:       # duplicate rows of the same company: visible for reconciliation
                d = ws.execute("""INSERT INTO accounts(list_id,key,name,domain,industry,members,is_primary,company_id,company_order,merge_notes)
                                  VALUES(?,?,?,?,?,?,0,?,?,?)""", (list_id, f"L{list_id}R{m['row']}", m["name"], m["domain"], m["industry"],
                                                                     jdump([{"row": m["row"], "name": m["name"]}]), aid, order,
                                                                     f"duplicate row, counted under {p['name']}"))
                stats["merged_rows"] += 1
                del d
            if not p["domain"]:
                stats["no_website"] += 1
        for c in comps:
            if c.get("parent") is not None and c["relation"]:
                ws.execute("UPDATE accounts SET parent_id=? WHERE id=?", (ids[id(c["parent"])], ids[id(c)]))
                if c["relation"] == "UNIT":
                    stats["routed_units"] += 1
                else:
                    stats["entity_checks"] += 1
            elif c["relation"]:
                stats["entity_checks"] += 1
        ws.execute("UPDATE lists SET rows_in_file=?, ingest=?, mapping=?, status='ready' WHERE id=?", (len(body), jdump(stats), jdump(mapping), list_id))
    return stats
