"""The ICP wizard: short conversational questions, one at a time, with conditional follow-ups and one-click suggestions.

QUESTIONS is served to the browser (web/static/wizard.js renders it). `when` makes a question conditional on earlier
answers. build_config(answers) turns the answers into a profile (icpq.icp.schema) that directly controls the engine; the
user reviews the generated rules, edits anything, and saves."""
import re

from . import packs
from .schema import normalize, slug

EXPORT_COLUMNS = [
    ("list", "List"), ("name", "Company"), ("domain", "Website"), ("row", "Source_Rows"), ("stage", "Stage"), ("rs", "Research_Status"),
    ("pr", "Priority"), ("sms", "Fit_Verified"), ("uc", "Use_Case"), ("vert", "Segment"), ("ind", "Industry"), ("buyer", "Buying_Committee"),
    ("ev", "Evidence"), ("url", "Evidence_URL"), ("conf", "Evidence_Confidence"), ("status", "Status"), ("hold", "Outreach_Hold_Reason"),
    ("note", "Research_Note"), ("missing", "Missing_Evidence"), ("sigv", "Signals_Verified"), ("sigi", "Signals_Inferred"),
    ("scale", "Scale_Signal"), ("just", "Priority_Rationale"), ("tw", "Target_Technology_Status"), ("also", "Also_On_Lists"),
    ("at", "Researched_At"), ("eas", "Evidence_Audit"), ("ear", "Evidence_Audit_Findings"), ("eaq", "Evidence_Exact_Quote"),
    ("opp", "Fit_Score"), ("oppx", "Fit_Score_Explanation"), ("cc", "Technologies_Verified"), ("cci", "Technologies_Mentioned"),
    ("vend", "Competitors_Verified"), ("chan", "Channel_vs_Direct"), ("trig", "Buying_Triggers"), ("angle", "Recommended_Angle"),
    ("persona", "Buyer_Persona"), ("emp", "Employees"), ("rev", "Revenue"), ("loc", "Location"), ("relation", "Entity_Relation"),
    ("dm", "Decision_Makers"), ("npl", "Decision_Maker_Count"), ("aics", "AI_Candidate_Strength"), ("aicq", "AI_Candidate_Quote_UNVERIFIED"), ("aicu", "AI_Candidate_URL"),
]
DEFAULT_EXPORT = ["list", "name", "domain", "stage", "pr", "sms", "uc", "vert", "ev", "url", "conf", "status", "hold", "missing", "sigv",
                  "scale", "just", "eas", "eaq", "opp", "oppx", "cc", "vend", "trig", "angle", "persona", "buyer", "dm", "at"]

QUESTIONS = [
    {"id": "company", "n": 1, "title": "Your company", "prompt": "What company do you work for, and what does it sell?",
     "help": "Plain English is perfect. If AI is connected (Settings), “Draft my ICP” fills in the next questions for you to check and edit.",
     "kind": "fields", "fields": [{"k": "company_name", "label": "Company"},
                                  {"k": "sells", "label": "What you sell", "long": True},
                                  {"k": "describe", "label": "Describe your business and your best customers (optional)", "long": True},
                                  {"k": "website", "label": "Your website (optional)"}]},
    {"id": "market", "n": 2, "title": "Your market", "prompt": "What industry or market do you operate in?",
     "help": "Optional. Pick the closest one for suggestion chips, or skip and type your own.", "kind": "pack"},
    {"id": "ideal", "n": 3, "title": "Ideal customer", "prompt": "Who is your ideal customer? Describe them in a sentence.",
     "help": "Think of your three best customers. What do they have in common?", "kind": "longtext", "k": "ideal", "suggest": "ideal"},
    {"id": "industries", "n": 4, "title": "Target industries", "prompt": "Which industries are you targeting?",
     "help": "Matched against the Industry column of your list. Leave empty to accept any industry.", "kind": "tags", "k": "industries", "suggest": "industries"},
    {"id": "exclude_industries", "n": 4, "title": "Industries to skip", "prompt": "Any industries you never sell to?", "help": "Optional.",
     "kind": "tags", "k": "exclude_industries"},
    {"id": "size", "n": 4, "title": "Company size", "prompt": "What company sizes fit? (employees and revenue)",
     "help": "Leave a box empty for no limit. Unknown sizes are never counted as a match or a mismatch.", "kind": "ranges",
     "fields": [{"k": "employees_min", "label": "Employees from"}, {"k": "employees_max", "label": "Employees to"},
                {"k": "revenue_min", "label": "Revenue from ($)"}, {"k": "revenue_max", "label": "Revenue to ($)"}]},
    {"id": "locations", "n": 4, "title": "Locations", "prompt": "Which locations are you targeting?", "help": "Countries, states or cities. Optional.",
     "kind": "tags", "k": "locations"},
    {"id": "location_required", "n": 4, "title": "Location rule", "prompt": "Only those locations, or just preferred?", "kind": "choice", "k": "location_required",
     "choices": [["yes", "Only these locations"], ["no", "Preferred, not required"]], "when": {"nonempty": "locations"}},
    {"id": "tech", "n": 5, "title": "Technology", "prompt": "Which products, technologies or platforms indicate a good prospect?",
     "help": "If a company's own site shows it uses one of these, it scores higher.", "kind": "tags", "k": "technologies", "suggest": "technologies"},
    {"id": "competitors", "n": 5, "title": "Competitors", "prompt": "Who are your competitors?", "help": "Optional. Their names are also used to spot vendors in your list.",
     "kind": "tags", "k": "competitors"},
    {"id": "competitor_stance", "n": 5, "title": "Competitor customers", "prompt": "A company that already uses a competitor is…", "kind": "choice",
     "k": "competitor_stance", "when": {"nonempty": "competitors"},
     "choices": [["prospect", "A good prospect (displacement)"], ["neutral", "Neutral"], ["negative", "A weaker prospect"]]},
    {"id": "problems", "n": 6, "title": "Problems you solve", "prompt": "What specific problems does your solution solve?",
     "help": "For each problem, add a few words a prospect's website would show if they have it.", "kind": "signals", "category": "problem", "suggest": "signals:problem"},
    {"id": "buying", "n": 7, "title": "Buying signals", "prompt": "What buying signals show a company needs you now?", "kind": "signals",
     "category": "buying", "suggest": "buying"},
    {"id": "research_signals", "n": 8, "title": "What to research", "prompt": "Which other signals should the engine look for on each company's website?",
     "help": "Behavioral, operational, financial, technology and organizational signals. Pick suggestions or add your own.", "kind": "signals",
     "category": "any", "suggest": "signals:other"},
    {"id": "committee", "n": 9, "title": "Buying committee", "prompt": "Which job titles and departments make up your buying committee?", "kind": "tags2",
     "fields": [{"k": "titles", "label": "Job titles", "suggest": "titles"}, {"k": "departments", "label": "Departments", "suggest": "departments"}]},
    {"id": "disqualifiers", "n": 10, "title": "Disqualifiers", "prompt": "What automatically disqualifies an account?", "kind": "disq"},
    {"id": "roles", "n": 11, "title": "Must-have vs nice-to-have", "prompt": "Which signals are mandatory, and which only raise the score?",
     "help": "Mandatory = an account can't qualify without verified evidence of it.", "kind": "roles"},
    {"id": "gate_mode", "n": 11, "title": "Mandatory rule", "prompt": "With several mandatory signals, must the engine verify all of them, or is one enough?",
     "kind": "choice", "k": "gate_mode", "when": {"min_mandatory": 2},
     "choices": [["all_mandatory", "All of them"], ["any_mandatory", "Any one is enough"], ["expression", "Custom rule (AND / OR)"]]},
    {"id": "gate_expression", "n": 11, "title": "Custom rule", "prompt": "Write the rule with signal names, AND, OR, NOT and brackets.",
     "kind": "expression", "k": "gate_expression", "when": {"eq": ["gate_mode", "expression"]}},
    {"id": "priority", "n": 12, "title": "A / B / C priority", "prompt": "How should A, B and C priorities be decided for qualified accounts?", "kind": "priority"},
    {"id": "evidence", "n": 13, "title": "Evidence standard", "prompt": "How strict should the evidence be before an account counts as qualified?", "kind": "choice",
     "k": "evidence_level", "choices": [["strict", "Strict: their own website, explicit proof, audited"], ["standard", "Standard: their own website"],
                                        ["lenient", "Lenient: independent pages that name them also count"]]},
    {"id": "hold", "n": 13, "title": "Very large companies", "prompt": "Should very large enterprises be held back from outreach (kept, but parked)?",
     "kind": "hold"},
    {"id": "sources", "n": 14, "title": "Research sources", "prompt": "Which research sources should the engine use?", "kind": "sources"},
    {"id": "export", "n": 15, "title": "Export", "prompt": "Which fields should appear in your final export?", "kind": "columns"},
]


def _phr(text):
    """A free-text label -> a phrase pattern list (the label itself; users can add more)."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return [t] if t else []


def _signal(s, default_req="preferred"):
    pats = s.get("patterns") or _phr(s.get("label"))
    return {"id": s.get("id") or slug(s.get("label")), "label": s.get("label") or s.get("id"), "category": s.get("category") or "other",
            "patterns": pats, "markers": s.get("markers") or [], "requirement": s.get("requirement") or default_req,
            "weight": int(s.get("weight") if s.get("weight") is not None else 10), "use_case": s.get("use_case") or s.get("label") or "",
            "confidence": s.get("confidence") or "medium", "description": s.get("description") or ""}


def build_config(a):
    a = a or {}
    pack = packs.find(a.get("pack") or "generic")
    sells = (a.get("sells") or "").strip()
    name = (a.get("profile_name") or "").strip() or (f"{a.get('company_name')} ICP" if a.get("company_name") else f"{pack['label']} ICP")
    sigs = [_signal(s) for s in (a.get("signals") or [])]
    ids = {s["id"] for s in sigs}
    stance = a.get("competitor_stance") or "prospect"
    comps = [c for c in (a.get("competitors") or []) if c]
    if comps and stance != "neutral" and "uses_competitor" not in ids:
        sigs.append({"id": "uses_competitor", "label": "Uses a competitor", "category": "competitor", "patterns": comps, "markers": [],
                     "requirement": "preferred" if stance == "prospect" else "negative", "weight": 10, "use_case": "Competitive displacement"})
    techs = [t for t in (a.get("technologies") or []) if t]
    if techs and "uses_target_tech" not in ids:
        sigs.append({"id": "uses_target_tech", "label": "Uses a technology that fits", "category": "technology", "patterns": techs, "markers": [],
                     "requirement": "preferred", "weight": 10, "use_case": "Technology fit"})
    lvl = a.get("evidence_level") or "standard"
    src = a.get("sources") or {}
    queries = [q for q in (a.get("search_queries") or []) if q]
    if src.get("search") and not queries:
        top = [p for s in sigs if s["requirement"] in ("mandatory", "preferred") for p in s["patterns"] if not p.lower().startswith("re:")][:4]
        queries = ["site:{domain} " + " OR ".join(f'"{p}"' for p in top)] if top else []
        queries += [q for q in pack.get("search", []) if "{signal}" not in q][:1]
    dq = []
    for d in packs.DISQUALIFIER_CHOICES:
        if d["id"] in (a.get("disqualifiers") or []):
            d = dict(d)
            if d["id"] == "competitor":
                if not comps:
                    continue
                d["patterns"] = comps
            dq.append(d)
    for p in a.get("custom_disqualifiers") or []:
        if str(p).strip():
            dq.append({"id": slug("dq " + p), "label": f"Site says “{p}”", "field": "page", "patterns": [p], "action": "DQ"})
    pm = a.get("priority_mode") or "size"
    ids_all = [s["id"] for s in sigs]
    if pm == "score":
        rules = [{"tier": "A", "scale": "any", "min_score": int(a.get("a_min_score") or 70), "require_any": []},
                 {"tier": "B", "scale": "any", "min_score": int(a.get("b_min_score") or 45), "require_any": []},
                 {"tier": "C", "scale": "any", "min_score": 0, "require_any": []}]
        desc = {"A": f"Verified fit + fit score ≥ {int(a.get('a_min_score') or 70)}", "B": f"Verified fit + fit score ≥ {int(a.get('b_min_score') or 45)}", "C": "Verified fit"}
    elif pm == "signals":
        need = [x for x in (a.get("a_signals") or []) if x in ids_all]
        rules = [{"tier": "A", "scale": "meaningful", "min_score": 0, "require_any": need},
                 {"tier": "B", "scale": "any", "min_score": 0, "require_any": need},
                 {"tier": "C", "scale": "any", "min_score": 0, "require_any": []}]
        desc = {"A": "Verified fit + key signal + meaningful scale", "B": "Verified fit + key signal", "C": "Verified fit"}
    else:
        need = [x for x in (a.get("a_signals") or []) if x in ids_all]
        rules = [{"tier": "A", "scale": "large", "min_score": 0, "require_any": need},
                 {"tier": "B", "scale": "meaningful", "min_score": 0, "require_any": []},
                 {"tier": "C", "scale": "any", "min_score": 0, "require_any": []}]
        desc = {"A": "Verified fit + strong scale" + (" + key signal" if need else ""), "B": "Verified fit + meaningful scale", "C": "Verified fit; scale not established"}
    scale = {"large": {"revenue_min": a.get("large_revenue") or 5e8, "employees_min": a.get("large_employees") or 1001},
             "meaningful": {"revenue_min": a.get("meaningful_revenue") or 5e7, "employees_min": a.get("meaningful_employees") or 201}}
    segs = a.get("segments")
    if segs is None:
        segs = [{"key": k, "label": lbl, "patterns": p} for k, lbl, p in pack.get("segments", [])]
    uc = a.get("use_cases")
    if uc is None:
        uc = [{"tag": t, "patterns": p} for t, p in pack.get("use_cases", [])]
    cols = [c for c in (a.get("export_columns") or DEFAULT_EXPORT) if c in dict(EXPORT_COLUMNS)]
    core_label = (a.get("core_label") or "").strip() or ("Fit verified" if not sigs else
                                                         (next((s["label"] for s in sigs if s["requirement"] == "mandatory"), "Fit") + " verified"))
    cfg = {
        "name": name, "company": {"name": a.get("company_name") or "", "sells": sells, "website": a.get("website") or ""},
        "market": a.get("market_text") or pack["label"], "ideal_customer": a.get("ideal") or "",
        "labels": {"core": core_label[:40], "use_case": "Signal / use case", "stack": "Tech / competitor", "target_tech": "Target technology",
                   "hold": "Enterprise Hold", "tagline": (f"{a.get('company_name')} · " if a.get("company_name") else "") + (sells or pack["label"])},
        "targeting": {"industries": a.get("industries") or [], "exclude_industries": a.get("exclude_industries") or [],
                      "employees_min": a.get("employees_min"), "employees_max": a.get("employees_max"), "revenue_min": a.get("revenue_min"),
                      "revenue_max": a.get("revenue_max"), "locations": a.get("locations") or [], "location_required": a.get("location_required") == "yes"},
        "segments": segs, "signals": sigs, "use_cases": uc,
        "gate": {"mode": a.get("gate_mode") or "all_mandatory", "expression": a.get("gate_expression") or "", "require_use_case": bool(a.get("require_use_case"))},
        "negative_context": list(dict.fromkeys(["scam", "phishing", "fraudulent", "we will never", "never ask you", "do not respond to"] + pack.get("negative_context", []))),
        "disqualifiers": dq, "competitors": comps, "technologies": techs, "target_technology": a.get("target_technology") or [],
        "hold": {"enabled": bool(a.get("hold_enabled")), "revenue_min": a.get("hold_revenue") or 6e9, "employees_min": a.get("hold_employees") or 10001},
        "scale": scale, "priority": {"rules": rules, "describe": desc},
        "evidence": {"own_domain_required": lvl != "lenient", "exclude_content_pages": lvl != "lenient", "require_marker_for_ready": lvl == "strict",
                     "audit": True, "min_confidence": "high" if lvl == "strict" else "medium"},
        "research": {"link_hints": list(dict.fromkeys(pack.get("link_hints", []) + ["about", "contact", "privacy", "terms"])),
                     "sitemap_hints": pack.get("sitemap_hints", []) if src.get("sitemap", True) else [],
                     "common_paths": pack.get("common_paths") or ["/about", "/contact", "/privacy", "/terms"],
                     "search_queries": queries if src.get("search") else [], "search_when": "no_strong_evidence" if src.get("search") else "never",
                     "discover_websites": bool(src.get("discover", True))},
        "committee": {"titles": a.get("titles") or [], "departments": a.get("departments") or [],
                      "persona_default": (a.get("titles") or a.get("departments") or ["Operations leader"])[0]},
        "export": {"columns": cols}, "ai": {"use": "shadow" if src.get("ai") else "off"},
    }
    return normalize(cfg)


def suggestions(pack_id):
    p = packs.find(pack_id)
    return next((x for x in packs.public()["packs"] if x["id"] == p["id"]), None)
