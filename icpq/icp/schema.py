"""The ICP profile: a saved, editable JSON document that DIRECTLY drives research and qualification.

normalize(cfg)  -> cfg with every key present (defaults filled in), safe to store
validate(cfg)   -> [error strings]; a profile with errors can't be used for a run
compile_icp(cfg)-> ICP object: compiled matchers, gate expression, scoring and priority rules, research plan
describe(cfg)   -> plain-English rule summary shown on the "Review rules" page

Signal patterns are phrases ("text JOIN to", "free trial") or regular expressions prefixed with "re:". A phrase matches
case-insensitively on word boundaries, with flexible whitespace; "*" inside a phrase stands for up to three words.

Nothing in here is specific to any company or industry: every vocabulary comes from the profile."""
import copy
import re

SCHEMA_VERSION = 1
REQUIREMENTS = ("mandatory", "preferred", "negative", "info")
CATEGORIES = ("product", "technology", "competitor", "problem", "buying", "behavioral", "operational", "financial",
              "organizational", "compliance", "other")
STAGE_TIERS = ("A", "B", "C")

DEFAULT = {
    "schema": SCHEMA_VERSION,
    "name": "Untitled ICP",
    "company": {"name": "", "sells": "", "website": ""},
    "market": "",
    "ideal_customer": "",
    "labels": {"core": "Fit verified", "use_case": "Signal / use case", "stack": "Tech / competitor", "target_tech": "Target technology",
               "hold": "Enterprise Hold", "tagline": ""},
    "targeting": {"industries": [], "exclude_industries": [], "employees_min": None, "employees_max": None, "revenue_min": None,
                  "revenue_max": None, "locations": [], "location_required": False, "out_of_range": "DQ"},
    "segments": [],
    "signals": [],
    "use_cases": [],
    "gate": {"mode": "all_mandatory", "expression": "", "require_use_case": False, "min_mandatory_hits": 1},
    "negative_context": ["scam", "phishing", "fraudulent", "we will never", "never ask you", "do not respond to"],
    "disqualifiers": [],
    "competitors": [],
    "technologies": [],
    "target_technology": [],
    "hold": {"enabled": False, "revenue_min": None, "employees_min": None},
    "scale": {"large": {"revenue_min": 5e8, "employees_min": 1001}, "meaningful": {"revenue_min": 5e7, "employees_min": 201}},
    "priority": {"rules": [{"tier": "A", "scale": "large", "min_score": 0, "require_any": []},
                           {"tier": "B", "scale": "meaningful", "min_score": 0, "require_any": []},
                           {"tier": "C", "scale": "any", "min_score": 0, "require_any": []}],
                 "describe": {"A": "Verified fit + strong scale", "B": "Verified fit + meaningful scale", "C": "Verified fit; scale not established"}},
    "scoring": {"tech_points": 20, "tech_mention_points": 8, "competitor_points": 10, "trigger_points": 15, "scale_large": 20,
                "scale_meaningful": 10, "confidence_points": 5, "core_points": 30},
    "evidence": {"own_domain_required": True, "exclude_content_pages": True, "require_marker_for_ready": True,
                 "min_confidence": "medium", "audit": True,
                 "content_paths": ["blog", "blogs", "news", "newsroom", "press", "articles", "learn", "resources", "insights", "guides",
                                   "community", "forum", "forums", "podcast", "webinars", "stories", "magazine", "case-studies",
                                   "case-study", "careers", "jobs"],
                 "vendor_copy": ["your customers", "your clients", "for businesses", "for agencies"]},
    "research": {"max_pages": 18, "link_budget": 8, "link_hints": ["about", "products", "services", "solutions", "pricing", "contact",
                                                                   "privacy", "terms", "support", "faq", "locations", "careers"],
                 "sitemap_hints": [], "common_paths": ["/about", "/contact", "/privacy", "/terms"], "search_queries": [],
                 "search_when": "no_strong_evidence", "discover_websites": True, "politeness_s": 0.6},
    "channel": {"patterns": ["reseller", "partner program", "white label", "white-label", "managed service provider", "msp",
                             "value added reseller", "systems integrator"], "label": "Channel / partner"},
    "committee": {"titles": [], "departments": [], "persona_default": "Operations leader"},
    "angles": {"default": "Lead with the verified need", "with_tech": "Integrate with {tech}", "with_competitor": "Displace or complement {competitor}",
               "channel": "Partner programme"},
    "export": {"columns": []},
    "ai": {"use": "off", "notes": ""},
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:40] or "signal"


def _list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[\n;,]", v) if x.strip()]
    return [str(x).strip() for x in v if str(x).strip()]


def normalize(cfg):
    c = _merge(DEFAULT, cfg or {})
    c["schema"] = SCHEMA_VERSION
    seen = set()
    sigs = []
    for s in c.get("signals") or []:
        s = dict(s)
        s["id"] = slug(s.get("id") or s.get("label"))
        while s["id"] in seen:
            s["id"] += "_2"
        seen.add(s["id"])
        s["label"] = str(s.get("label") or s["id"])
        s["requirement"] = s.get("requirement") if s.get("requirement") in REQUIREMENTS else "preferred"
        s["category"] = s.get("category") if s.get("category") in CATEGORIES else "other"
        s["patterns"] = _list(s.get("patterns"))
        s["markers"] = _list(s.get("markers"))
        s["weight"] = max(0, min(100, int(s.get("weight") or 0)))
        s["confidence"] = "high" if s.get("confidence") == "high" else "medium"
        s["use_case"] = str(s.get("use_case") or "")
        s["scope"] = "any_site" if s.get("scope") == "any_site" else "own_site"
        s["action"] = s.get("action") if s.get("action") in ("DQ", "REVIEW", "SCORE") else ("REVIEW" if s["requirement"] == "negative" else "SCORE")
        s["description"] = str(s.get("description") or "")
        sigs.append(s)
    c["signals"] = sigs
    for k in ("negative_context", "competitors", "technologies", "target_technology"):
        c[k] = _list(c.get(k))
    c["use_cases"] = [{"tag": str(u.get("tag") or "").strip(), "patterns": _list(u.get("patterns"))} for u in c.get("use_cases") or [] if u.get("tag")]
    c["segments"] = [{"key": slug(s.get("key") or s.get("label")).upper(), "label": str(s.get("label") or s.get("key")),
                      "patterns": _list(s.get("patterns"))} for s in (c.get("segments") or [])[:8] if (s.get("label") or s.get("key"))]
    dqs = []
    for d in c.get("disqualifiers") or []:
        dqs.append({"id": slug(d.get("id") or d.get("label")), "label": str(d.get("label") or d.get("id") or "Disqualifier"),
                    "field": d.get("field") if d.get("field") in ("name", "domain", "industry", "page") else "industry",
                    "patterns": _list(d.get("patterns")), "action": "REVIEW" if d.get("action") == "REVIEW" else "DQ"})
    c["disqualifiers"] = dqs
    t = c["targeting"]
    t["industries"], t["exclude_industries"], t["locations"] = _list(t.get("industries")), _list(t.get("exclude_industries")), _list(t.get("locations"))
    for k in ("employees_min", "employees_max", "revenue_min", "revenue_max"):
        t[k] = _num(t.get(k))
    t["out_of_range"] = "REVIEW" if t.get("out_of_range") == "REVIEW" else "DQ"
    for lvl in ("large", "meaningful"):
        for k in ("revenue_min", "employees_min"):
            c["scale"][lvl][k] = _num(c["scale"][lvl].get(k))
    for k in ("revenue_min", "employees_min"):
        c["hold"][k] = _num(c["hold"].get(k))
    rules = []
    for r in c["priority"].get("rules") or []:
        if r.get("tier") in STAGE_TIERS:
            rules.append({"tier": r["tier"], "scale": r.get("scale") if r.get("scale") in ("large", "meaningful", "any") else "any",
                          "min_score": int(r.get("min_score") or 0), "require_any": _list(r.get("require_any"))})
    if not any(r["tier"] == "C" for r in rules):
        rules.append({"tier": "C", "scale": "any", "min_score": 0, "require_any": []})
    c["priority"]["rules"] = rules
    for k in ("link_hints", "sitemap_hints", "common_paths", "search_queries"):
        c["research"][k] = _list(c["research"].get(k))
    c["research"]["max_pages"] = max(1, min(60, int(c["research"].get("max_pages") or 18)))
    c["research"]["link_budget"] = max(0, min(30, int(c["research"].get("link_budget") or 8)))
    c["research"]["search_when"] = c["research"].get("search_when") if c["research"].get("search_when") in ("never", "always", "no_strong_evidence") else "no_strong_evidence"
    c["committee"]["titles"], c["committee"]["departments"] = _list(c["committee"].get("titles")), _list(c["committee"].get("departments"))
    c["channel"]["patterns"] = _list(c["channel"].get("patterns"))
    c["evidence"]["content_paths"] = _list(c["evidence"].get("content_paths"))
    c["evidence"]["vendor_copy"] = _list(c["evidence"].get("vendor_copy"))
    c["export"]["columns"] = _list(c["export"].get("columns"))
    c["ai"]["use"] = c["ai"].get("use") if c["ai"].get("use") in ("off", "shadow") else "off"
    return c


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        from ..util import parse_number
        return parse_number(v)


# ------------------------------------------------------------------ patterns
def phrase_regex(p):
    p = str(p).strip()
    if p.lower().startswith("re:"):
        return p[3:].strip()
    parts = [re.escape(x) for x in re.split(r"\s+", p) if x]
    body = r"\s+".join(parts).replace(r"\*", r"(?:\S+\s+){0,3}?\S*")
    left = r"\b" if re.match(r"\w", p) else ""
    right = r"\b" if re.search(r"\w$", p) else ""
    return left + body + right


def any_regex(patterns):
    pats = [phrase_regex(p) for p in patterns if str(p).strip()]
    return re.compile("|".join(f"(?:{x})" for x in pats), re.IGNORECASE | re.DOTALL) if pats else None


# ------------------------------------------------------------------ gate expression
TOKEN = re.compile(r"\s*(\(|\)|\bAND\b|\bOR\b|\bNOT\b|[A-Za-z0-9_]+)", re.IGNORECASE)


def parse_expr(expr, known):
    """Boolean expression over signal ids -> nested tuples. Raises ValueError with a readable message."""
    toks = []
    pos = 0
    expr = expr or ""
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m:
            if expr[pos:].strip():
                raise ValueError(f"can't read the rule near '{expr[pos:pos + 15]}'")
            break
        toks.append(m.group(1))
        pos = m.end()
    i = [0]

    def peek():
        return toks[i[0]].upper() if i[0] < len(toks) else None

    def take():
        i[0] += 1
        return toks[i[0] - 1]

    def p_or():
        n = p_and()
        while peek() == "OR":
            take()
            n = ("or", n, p_and())
        return n

    def p_and():
        n = p_not()
        while peek() == "AND":
            take()
            n = ("and", n, p_not())
        return n

    def p_not():
        if peek() == "NOT":
            take()
            return ("not", p_not())
        if peek() == "(":
            take()
            n = p_or()
            if peek() != ")":
                raise ValueError("missing ')'")
            take()
            return n
        t = take() if peek() else None
        if t is None or t.upper() in ("AND", "OR", ")"):
            raise ValueError("a signal name is missing in the rule")
        if t not in known:
            raise ValueError(f"unknown signal '{t}' in the rule (known: {', '.join(sorted(known)) or 'none'})")
        return ("sig", t)

    if not toks:
        return None
    tree = p_or()
    if i[0] != len(toks):
        raise ValueError(f"unexpected '{toks[i[0]]}' in the rule")
    return tree


def eval_expr(tree, hits):
    if tree is None:
        return True
    op = tree[0]
    if op == "sig":
        return tree[1] in hits
    if op == "not":
        return not eval_expr(tree[1], hits)
    if op == "and":
        return eval_expr(tree[1], hits) and eval_expr(tree[2], hits)
    return eval_expr(tree[1], hits) or eval_expr(tree[2], hits)


def validate(cfg):
    c = normalize(cfg)
    errs = []
    if not c["signals"]:
        errs.append("Add at least one signal: the engine needs something to look for.")
    pos = [s for s in c["signals"] if s["requirement"] in ("mandatory", "preferred")]
    if not pos:
        errs.append("Add at least one mandatory or preferred signal.")
    for s in c["signals"]:
        if not s["patterns"]:
            errs.append(f"Signal '{s['label']}' has no phrases to look for.")
        for p in s["patterns"] + s["markers"]:
            try:
                re.compile(phrase_regex(p))
            except re.error as e:
                errs.append(f"Signal '{s['label']}': pattern '{p}' is not valid ({e}).")
    if c["gate"]["mode"] == "expression":
        try:
            parse_expr(c["gate"]["expression"], {s["id"] for s in c["signals"]})
        except ValueError as e:
            errs.append(f"Qualification rule: {e}.")
    elif c["gate"]["mode"] in ("all_mandatory", "any_mandatory") and not any(s["requirement"] == "mandatory" for s in c["signals"]):
        errs.append("The qualification rule needs at least one mandatory signal (or switch to a custom rule).")
    for d in c["disqualifiers"]:
        if not d["patterns"]:
            errs.append(f"Disqualifier '{d['label']}' has no phrases.")
    for k in ("negative_context", "competitors", "technologies", "target_technology"):
        for p in c[k]:
            try:
                re.compile(phrase_regex(p))
            except re.error as e:
                errs.append(f"{k}: '{p}' is not valid ({e}).")
    return errs


# ------------------------------------------------------------------ compiled form
class ICP:
    def __init__(self, cfg):
        self.cfg = c = normalize(cfg)
        self.signals = c["signals"]
        self.by_id = {s["id"]: s for s in self.signals}
        for s in self.signals:
            s["_rx"] = any_regex(s["patterns"])
            s["_mk"] = any_regex(s["markers"])
        self.mandatory = [s for s in self.signals if s["requirement"] == "mandatory"]
        self.negative = any_regex(c["negative_context"])
        self.vendor_copy = any_regex(c["evidence"]["vendor_copy"])
        self.content_path = re.compile(r"/(" + "|".join(re.escape(p) for p in c["evidence"]["content_paths"]) + r")(/|$|\.)", re.IGNORECASE) \
            if c["evidence"]["content_paths"] else None
        self.use_cases = [(u["tag"], any_regex(u["patterns"])) for u in c["use_cases"] if u["patterns"]]
        self.segments = [(s["key"], s["label"], any_regex(s["patterns"])) for s in c["segments"]]
        self.competitors = {p: re.compile(phrase_regex(p), re.IGNORECASE) for p in c["competitors"]}
        self.technologies = {p: re.compile(phrase_regex(p), re.IGNORECASE) for p in c["technologies"]}
        self.target_tech = {p: re.compile(phrase_regex(p), re.IGNORECASE) for p in c["target_technology"]}
        self.channel = any_regex(c["channel"]["patterns"])
        self.dq = [(d, any_regex(d["patterns"])) for d in c["disqualifiers"]]
        self.incl_ind = any_regex(c["targeting"]["industries"])
        self.excl_ind = any_regex(c["targeting"]["exclude_industries"])
        self.locations = any_regex(c["targeting"]["locations"])
        self.gate_tree = parse_expr(c["gate"]["expression"], set(self.by_id)) if c["gate"]["mode"] == "expression" else None
        r = c["research"]
        hints = r["link_hints"] + [p for s in self.signals for p in s["patterns"][:3] if not p.lower().startswith("re:")]
        self.link_hint = any_regex([h for h in hints if len(h) <= 40]) if hints else None
        strong_hints = [p for s in self.signals if s["requirement"] == "mandatory" for p in s["patterns"][:3] if not p.lower().startswith("re:")]
        self.link_strong = any_regex([h for h in strong_hints if len(h) <= 40]) if strong_hints else None
        self.sitemap_hint = any_regex(r["sitemap_hints"]) if r["sitemap_hints"] else None
        # proof markers used by the evidence audit: every signal's markers, else its patterns
        mk = [m for s in self.signals if s["requirement"] in ("mandatory", "preferred") for m in (s["markers"] or [])]
        self.audit_marker = any_regex(mk) if mk else None

    @property
    def name(self):
        return self.cfg["name"]

    def gate(self, hits):
        """hits: set of signal ids with qualifying evidence -> (passed, explanation)."""
        g = self.cfg["gate"]
        if g["mode"] == "expression":
            ok = eval_expr(self.gate_tree, hits)
            return ok, ("rule satisfied: " if ok else "rule not satisfied: ") + g["expression"]
        man = [s["id"] for s in self.mandatory]
        got = [m for m in man if m in hits]
        if g["mode"] == "any_mandatory":
            ok = len(got) >= max(1, int(g.get("min_mandatory_hits") or 1))
            return ok, f"{len(got)} of {len(man)} mandatory signals verified (need {max(1, int(g.get('min_mandatory_hits') or 1))})"
        ok = bool(man) and len(got) == len(man)
        return ok, f"{len(got)} of {len(man)} mandatory signals verified (all required)"


def compile_icp(cfg):
    return ICP(cfg)


def _money(v):
    if v is None:
        return "—"
    return f"${v / 1e9:,.1f}B" if v >= 1e9 else f"${v / 1e6:,.0f}M" if v >= 1e6 else f"${v:,.0f}"


def describe(cfg):
    """Plain-English summary of exactly what the engine will do with this profile."""
    c = normalize(cfg)
    out = []
    t = c["targeting"]
    tgt = []
    if t["industries"]:
        tgt.append("industries matching " + ", ".join(t["industries"]))
    if t["exclude_industries"]:
        tgt.append("excluding " + ", ".join(t["exclude_industries"]))
    if t["employees_min"] or t["employees_max"]:
        tgt.append(f"{int(t['employees_min'] or 0):,}–{int(t['employees_max']):,} employees" if t["employees_max"] else f"{int(t['employees_min']):,}+ employees")
    if t["revenue_min"] or t["revenue_max"]:
        tgt.append(f"revenue {_money(t['revenue_min'])}–{_money(t['revenue_max'])}")
    if t["locations"]:
        tgt.append(("only in " if t["location_required"] else "preferably in ") + ", ".join(t["locations"]))
    out.append(("Who is in scope", ("; ".join(tgt) or "Any company in the uploaded list") +
                f". Accounts clearly outside these ranges are {'disqualified' if t['out_of_range'] == 'DQ' else 'sent to review'}; "
                "unknown size, revenue or location is never treated as a match or a mismatch."))
    for req, title in (("mandatory", "Must be verified (mandatory)"), ("preferred", "Raises the score (preferred)"),
                       ("negative", "Counts against the account (negative)"), ("info", "Recorded for information")):
        ss = [s for s in c["signals"] if s["requirement"] == req]
        if ss:
            out.append((title, "; ".join(f"{s['label']} [{s['category']}{', weight ' + str(s['weight']) if s['weight'] else ''}]: looks for "
                                         + ", ".join(f"“{p}”" for p in s["patterns"][:6])
                                         + (" — proof markers " + ", ".join(f"“{m}”" for m in s["markers"][:4]) if s["markers"] else "")
                                         for s in ss)))
    g = c["gate"]
    rule = {"all_mandatory": "every mandatory signal must be verified", "any_mandatory": f"at least {g.get('min_mandatory_hits') or 1} mandatory signal(s) must be verified",
            "expression": f"the rule “{g['expression']}” must be true"}[g["mode"]]
    out.append(("Qualification rule", f"An account qualifies (A/B/C) only when {rule}, with evidence quoted from "
                + ("the company's own website" if c["evidence"]["own_domain_required"] else "a cited web page")
                + (" and a use case identified" if g["require_use_case"] else "") + ". Missing evidence is never counted as verified."))
    pr = c["priority"]
    out.append(("Priority A/B/C", "; ".join(f"{r['tier']}: scale {r['scale']}" + (f", score ≥ {r['min_score']}" if r["min_score"] else "")
                                            + (f", needs one of {', '.join(r['require_any'])}" if r["require_any"] else "") + f" — {pr['describe'].get(r['tier'], '')}"
                                            for r in pr["rules"])))
    sc = c["scale"]
    out.append(("Scale levels", f"Large = revenue ≥ {_money(sc['large']['revenue_min'])} or > {int((sc['large']['employees_min'] or 1) - 1):,} employees; "
                f"meaningful = revenue ≥ {_money(sc['meaningful']['revenue_min'])} or > {int((sc['meaningful']['employees_min'] or 1) - 1):,} employees."))
    if c["hold"]["enabled"]:
        out.append((c["labels"]["hold"], f"Qualified accounts with revenue ≥ {_money(c['hold']['revenue_min'])} or ≥ {int(c['hold']['employees_min'] or 0):,} employees are held, with research kept."))
    dq = [f"{d['label']} ({d['field']}: {', '.join(d['patterns'][:5])}) → {d['action']}" for d in c["disqualifiers"]]
    if c["competitors"]:
        dq.append("Competitors / vendors named " + ", ".join(c["competitors"][:8]) + " → DQ")
    if dq:
        out.append(("Disqualifiers", "; ".join(dq)))
    if c["negative_context"]:
        out.append(("Ignored passages", "Text near " + ", ".join(f"“{x}”" for x in c["negative_context"][:8]) + " is never used as evidence."))
    ev = c["evidence"]
    out.append(("Evidence standard", "; ".join(filter(None, [
        "evidence must be on the company's own domain" if ev["own_domain_required"] else "third-party pages may be cited when they name the company",
        "blog/news/marketing pages are rejected" if ev["exclude_content_pages"] else "",
        "vendor copy aimed at 'your customers' is rejected" if ev["vendor_copy"] else "",
        "outreach-ready needs an explicit proof marker and an evidence audit PASS" if ev["require_marker_for_ready"] else "outreach-ready needs an evidence audit PASS"]))))
    r = c["research"]
    out.append(("Research plan", f"Crawl up to {r['max_pages']} pages per company (home page, {r['link_budget']} linked pages whose link mentions "
                + ", ".join(r["link_hints"][:8]) + (", sitemap pages matching " + ", ".join(r["sitemap_hints"][:5]) if r["sitemap_hints"] else "")
                + ", then " + ", ".join(r["common_paths"][:6]) + "). "
                + (("Web searches: " + " | ".join(r["search_queries"][:4]) + f" (run {'always' if r['search_when'] == 'always' else 'only when no strong evidence was found'}; "
                    "needs a search provider in Settings)") if r["search_queries"] and r["search_when"] != "never" else "No web searches.")))
    if c["committee"]["titles"] or c["committee"]["departments"]:
        out.append(("Buying committee", ", ".join(c["committee"]["titles"] + c["committee"]["departments"])))
    out.append(("AI", "AI reviews accounts in REVIEW and proposes quotes; code checks every quote word for word, and AI never changes a verdict."
                if c["ai"]["use"] == "shadow" else "Off: decisions are made by the rules above only."))
    return out
