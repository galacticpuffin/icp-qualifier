"""Deterministic verdicts from graded evidence. The profile supplies every rule; code supplies every status.

decide(icp, acct, evs, stk, crawl) -> verdict dict:
  priority  A | B | C | HOLD | REVIEW | DQ
  core      Yes (gate passed on VERIFIED evidence) | Signal (some mandatory evidence, gate not passed) | No | — (DQ)
  missing   mandatory signals without VERIFIED evidence (missing evidence is never treated as verified)
  plus the explainable fit score, technology / competitor / channel / trigger fields, angle and persona.
The fit score never qualifies an account on its own (only the gate does); it can only rank and set A/B/C when the
profile's priority rules say so."""
import re

from ..util import registrable

STAGE_OF_RELATION = {
    "FRANCHISEE": "independent franchisee / agent / dealer on a brand site: brand evidence is not theirs, needs its own evidence",
    "AGENCY": "separate government agency on a shared domain: independent buying entity, needs its own evidence",
    "SUBSIDIARY": "shares a website with another company in the list but its name doesn't show it is a unit: possible subsidiary with independent buying",
    "NAME_CONFLICT": "entity ambiguous: the same company name appears with different websites in the list",
    "SPLIT_OUT": "name has no visible link to the website it was listed with: entity check needed",
    "UNIT_NO_PARENT": "department / location of the organisation on this website, whose parent is not in the list: route to the parent once verified",
}


def scale_level(icp, acct):
    rev, emp = acct.get("revenue") or 0, acct.get("employees") or 0
    sc = icp.cfg["scale"]

    def hit(lvl):
        r, e = sc[lvl]["revenue_min"], sc[lvl]["employees_min"]
        return bool((r and rev >= r) or (e and emp >= e))
    if hit("large"):
        return "large"
    if hit("meaningful"):
        return "meaningful"
    return "unknown" if not (rev or emp) else "small"


def scale_text(acct):
    bits = []
    if acct.get("revenue"):
        r = acct["revenue"]
        bits.append(f"revenue ${r / 1e9:,.1f}B" if r >= 1e9 else f"revenue ${r / 1e6:,.0f}M")
    if acct.get("employees"):
        bits.append(f"{int(acct['employees']):,} employees")
    return ", ".join(bits) or "scale not established"


def segment(icp, acct):
    blob = f"{acct.get('industry') or ''} | {acct.get('name') or ''}"
    for key, _label, rx in icp.segments:
        if rx and rx.search(blob):
            return key
    return "GENERAL"


def _targeting(icp, acct):
    """-> (action, reason) when the account is clearly outside the targeting; unknown values never trigger."""
    t, c = icp.cfg["targeting"], icp
    ind = (acct.get("industry") or "").strip()
    if ind and c.excl_ind and c.excl_ind.search(ind):
        return "DQ", f"excluded industry ({ind})"
    act = t["out_of_range"]
    if ind and c.incl_ind and not c.incl_ind.search(ind):
        return act, f"industry outside the target list ({ind})"
    emp, rev = acct.get("employees"), acct.get("revenue")
    if emp and t["employees_min"] and emp < t["employees_min"]:
        return act, f"{int(emp):,} employees, below the {int(t['employees_min']):,} minimum"
    if emp and t["employees_max"] and emp > t["employees_max"]:
        return act, f"{int(emp):,} employees, above the {int(t['employees_max']):,} maximum"
    if rev and t["revenue_min"] and rev < t["revenue_min"]:
        return act, f"revenue ${rev:,.0f}, below the minimum"
    if rev and t["revenue_max"] and rev > t["revenue_max"]:
        return act, f"revenue ${rev:,.0f}, above the maximum"
    loc = (acct.get("location") or "").strip()
    if t["location_required"] and loc and c.locations and not c.locations.search(loc):
        return act, f"location outside the target ({loc})"
    return None, ""


def _dq(icp, acct, page_texts):
    name, dom = acct.get("name") or "", acct.get("domain") or ""
    for comp, rx in icp.competitors.items():
        if rx.search(name) or rx.search(dom.split(".")[0] if dom else ""):
            return "DQ", f"competitor / vendor ({comp})"
    for d, rx in icp.dq:
        if rx is None:
            continue
        if d["field"] == "page":
            for url, txt in page_texts:
                m = rx.search(txt or "")
                if m:
                    return d["action"], f"{d['label']}: “{m.group(0)}” on {url}"
            continue
        val = {"name": name, "domain": dom, "industry": acct.get("industry") or ""}[d["field"]]
        if val and rx.search(val):
            return d["action"], f"{d['label']} ({d['field']}: {val})"
    return None, ""


def score(icp, acct, evs, stk, core, tier_hint=None):
    S = icp.cfg["scoring"]
    parts = []
    if core == "Yes":
        parts.append(("Verified fit", S["core_points"], "qualification rule passed on verified evidence"))
    ver = {e["signal_id"] for e in evs if e["status"] == "VERIFIED"}
    inf = {e["signal_id"] for e in evs if e["status"] == "INFERRED"} - ver
    for s in icp.signals:
        if not s["weight"] or s["requirement"] == "info":
            continue
        if s["requirement"] == "negative":
            if s["id"] in ver:
                parts.append((s["label"], -s["weight"], "negative signal verified"))
            continue
        if s["id"] in ver:
            parts.append((s["label"], s["weight"], "verified"))
        elif s["id"] in inf:
            parts.append((s["label"], s["weight"] // 2, "inferred (not verified): half weight"))
    tv = [n for n, v in stk["tech"].items() if v[0] == "VERIFIED"]
    tm = [n for n, v in stk["tech"].items() if v[0] != "VERIFIED"]
    if tv:
        parts.append(("Technology fit", S["tech_points"], "uses " + ", ".join(tv[:3])))
    elif tm:
        parts.append(("Technology fit", S["tech_mention_points"], "mentions " + ", ".join(tm[:3]) + " (not proof of use)"))
    cv = [n for n, v in stk["competitor"].items() if v[0] == "VERIFIED"]
    if cv:
        parts.append(("Competitor in place", S["competitor_points"], "uses " + ", ".join(cv[:3]) + " (displacement angle)"))
    trig = [e for e in evs if e["status"] == "VERIFIED" and e["category"] in ("buying",)]
    if trig:
        parts.append(("Buying triggers", S["trigger_points"], "; ".join(sorted({e["label"] for e in trig}))[:160]))
    lvl = scale_level(icp, acct)
    if lvl == "large":
        parts.append(("Scale", S["scale_large"], scale_text(acct)))
    elif lvl == "meaningful":
        parts.append(("Scale", S["scale_meaningful"], scale_text(acct)))
    if len(ver) >= 2:
        parts.append(("Evidence confidence", S["confidence_points"], f"{len(ver)} verified signals"))
    return max(0, min(100, sum(p[1] for p in parts))), parts


def decide(icp, acct, evs, stk, crawl, page_texts=()):
    c = icp.cfg
    v = {"priority": "REVIEW", "status": "", "core": "No", "use_case": "", "evidence": "", "url": "", "confidence": "", "scale": scale_text(acct),
         "scale_level": scale_level(icp, acct), "segment": segment(icp, acct), "qual_reason": "", "review_reason": "", "missing": [],
         "signals": {}, "tech": [], "tech_mentions": [], "competitors": [], "triggers": [], "channel": "DIRECT", "channel_score": 0,
         "target_tech": "", "buyer": ", ".join((c["committee"]["titles"] + c["committee"]["departments"])[:4])}
    ver = {}
    for e in evs:
        v["signals"].setdefault(e["signal_id"], {"label": e["label"], "status": "MISSING"})
        cur = v["signals"][e["signal_id"]]["status"]
        if e["status"] == "VERIFIED" or (e["status"] == "INFERRED" and cur not in ("VERIFIED",)):
            v["signals"][e["signal_id"]]["status"] = e["status"] if cur != "VERIFIED" else cur
        if e["status"] == "VERIFIED":
            ver.setdefault(e["signal_id"], e)
    for s in icp.signals:
        v["signals"].setdefault(s["id"], {"label": s["label"], "status": "MISSING"})
        v["signals"][s["id"]]["req"] = s["requirement"]
    v["tech"] = [n for n, x in stk["tech"].items() if x[0] == "VERIFIED"]
    v["tech_mentions"] = [n for n, x in stk["tech"].items() if x[0] != "VERIFIED"]
    v["competitors"] = [n for n, x in stk["competitor"].items() if x[0] == "VERIFIED"]
    v["triggers"] = sorted({e["label"] for e in evs if e["status"] == "VERIFIED" and e["category"] == "buying"})
    if stk["channel"]:
        v["channel"], v["channel_score"] = "CHANNEL / PARTNER", min(100, 40 + 20 * len(stk["channel"]))
    v["missing"] = [s["label"] for s in icp.mandatory if s["id"] not in ver]

    def finish(pr, status, **kw):
        v.update(priority=pr, status=status, **kw)
        v["fit_score"], v["score_parts"] = score(icp, acct, evs, stk, v["core"])
        tv = [n for n, x in stk["target"].items() if x[0] == "VERIFIED"]
        v["target_tech"] = ("TARGET TECH VERIFIED" if tv else ("FIT VERIFIED ONLY" if v["core"] == "Yes" else "NEEDS VERIFICATION")) if icp.target_tech else ""
        v["persona"] = "Partner / alliances manager" if v["channel"] != "DIRECT" else \
            (c["committee"]["titles"][0] if c["committee"]["titles"] else c["committee"]["persona_default"])
        a = c["angles"]
        v["angle"] = (a["channel"] if v["channel"] != "DIRECT" else a["with_tech"].format(tech=v["tech"][0]) if v["tech"] else
                      a["with_competitor"].format(competitor=v["competitors"][0]) if v["competitors"] else a["default"] if v["core"] == "Yes" else
                      "Verify fit first: " + (", ".join(v["missing"][:2]) or "evidence missing"))
        return v

    # 1 disqualifiers and targeting (vendor / competitor / excluded industry / out of range)
    act, why = _dq(icp, acct, page_texts)
    if act == "DQ":
        return finish("DQ", "Disqualified – " + why, core="—", qual_reason="", review_reason="")
    if act == "REVIEW":
        return finish("REVIEW", "Review – " + why, review_reason=why)
    act, why = _targeting(icp, acct)
    if act == "DQ":
        return finish("DQ", "Disqualified – outside ICP: " + why, core="—")
    tgt_review = why if act == "REVIEW" else ""
    # 2 entity relation from the list (units are routed at ingest; these need their own evidence)
    rel = acct.get("relation") or ""
    if rel == "UNIT":
        return finish("DQ", f"Disqualified – duplicate: routed to parent {acct.get('parent_name') or ''}".strip(), core="—", routed=True)
    # 3 negative signals
    for s in icp.signals:
        if s["requirement"] == "negative" and s["id"] in ver:
            if s["action"] == "DQ":
                e = ver[s["id"]]
                return finish("DQ", f"Disqualified – {s['label']}: “{e['match']}”", core="—")
            if s["action"] == "REVIEW":
                tgt_review = (tgt_review + "; " if tgt_review else "") + f"negative signal verified: {s['label']}"
    # 4 the gate
    passed, gate_why = icp.gate(set(ver))
    best = None
    for s in icp.mandatory or [s for s in icp.signals if s["requirement"] == "preferred"]:
        if s["id"] in ver:
            best = ver[s["id"]]
            break
    if best is None and ver:
        best = next((e for e in evs if e["status"] == "VERIFIED" and e["kind"] in ("mandatory", "preferred")), None)
    tags = []
    for e in evs:
        if e["status"] == "VERIFIED" and e["kind"] in ("mandatory", "preferred"):
            tags += [t for t in e["use_cases"] if t not in tags]
    v["use_case"] = ", ".join(tags[:4])
    if best:
        v.update(evidence=best["snippet"][:500], url=best["url"], confidence=best["confidence"])
    if not passed:
        partial = [e for e in evs if e["kind"] == "mandatory" and e["status"] in ("VERIFIED", "INFERRED")]
        if partial:
            e = partial[0]
            v.update(evidence=v["evidence"] or e["snippet"][:500], url=v["url"] or e["url"], confidence=v["confidence"] or e["confidence"])
            why = f"partial evidence ({gate_why}); missing: {', '.join(v['missing']) or 'rule not met'}" + \
                  ("" if e["status"] == "VERIFIED" else f"; best passage is {e['status'].lower()}: {e['reason']}")
            return finish("REVIEW", "Review – " + why, core="Signal", review_reason=why)
        reason = (f"no verified evidence of {', '.join(v['missing'][:3]) or 'the mandatory signals'}" if crawl else "website unreachable; nothing verified")
        return finish("REVIEW", "Review – " + reason, core="No", review_reason=reason)
    if c["gate"]["require_use_case"] and not tags:
        why = "fit verified but no use case established"
        return finish("REVIEW", "Review – " + why, core="Signal", review_reason=why)
    if rel in STAGE_OF_RELATION:
        why = STAGE_OF_RELATION[rel]
        return finish("REVIEW", "Review – " + why, core="Signal", review_reason=why)
    if tgt_review:
        return finish("REVIEW", "Review – " + tgt_review, core="Yes", review_reason=tgt_review)
    # 5 priority
    v["core"] = "Yes"
    fit, _ = score(icp, acct, evs, stk, "Yes")
    lvl = v["scale_level"]
    tier, rule_txt = "C", "default"
    for r in c["priority"]["rules"]:
        ok_scale = r["scale"] == "any" or (r["scale"] == "large" and lvl == "large") or (r["scale"] == "meaningful" and lvl in ("large", "meaningful"))
        ok_sig = not r["require_any"] or any(x in ver for x in r["require_any"])
        if ok_scale and fit >= r["min_score"] and ok_sig:
            tier = r["tier"]
            rule_txt = f"scale {r['scale']}" + (f", fit ≥ {r['min_score']}" if r["min_score"] else "") + (f", has {', '.join(x for x in r['require_any'] if x in ver)}" if r["require_any"] else "")
            break
    just = f"{tier}: {rule_txt} ({v['scale']}; fit score {fit})"
    reason = f"Verified {', '.join(s['label'] for s in icp.signals if s['id'] in ver and s['requirement'] in ('mandatory', 'preferred'))[:200]}" + \
             (f" with use case {v['use_case']}" if v["use_case"] else "") + f" — {gate_why}"
    h = c["hold"]
    if h["enabled"] and ((h["revenue_min"] and (acct.get("revenue") or 0) >= h["revenue_min"]) or (h["employees_min"] and (acct.get("employees") or 0) >= h["employees_min"])):
        return finish("HOLD", f"{c['labels']['hold'].upper()} – researched as {tier}", qual_reason=reason + f"; held: {v['scale']}", just=just, held_tier=tier)
    return finish(tier, f"Qualified – {tier}", qual_reason=reason, just=just)


def own_domain(url, domain):
    from ..util import host
    return bool(domain and url.startswith("http") and registrable(host(domain)) == registrable(host(url)))


VENDOR_HINT = re.compile(r"\b(reseller|white[- ]label|platform for (?:businesses|agencies))\b", re.IGNORECASE)
