"""Workspace dashboard data (port of the original master dashboard backend). Read-only over the workspace database.

Account stages (one per company; first match wins):
  PENDING          not researched yet                      PENDING_WEBSITE  no website -> nothing researched (NOT complete)
  DQ / ROUTED      disqualified / unit routed to its parent HOLD             passes the gate, held (profile's hold rule)
  READY            A/B/C passing every outreach check      QUALIFIED        A/B/C held back from outreach (reason kept)
  RETRY            research incomplete (needed searches blocked / site unreadable / failed)
  REVIEW           research complete, fit not verified     MERGED           duplicate source row counted under its company
READY = A/B/C + fit verified + evidence + http URL on the company's own registrable domain (when the profile requires it) +
evidence audit PASS + not flagged weak + not a competitor/vendor; deduplicated across lists by website. Every text field is
copied from the research records; nothing is invented."""
import time

from .engine import ai as AI
from .engine import search as SEARCH
from .util import ago_iso, host, jload, norm_name, now, registrable

STAGES = ["READY", "QUALIFIED", "HOLD", "REVIEW", "RETRY", "PENDING_WEBSITE", "PENDING", "DQ", "ROUTED", "MERGED"]


def outreach_check(icp_cfg, a, weak):
    why = []
    ea = a.get("ea")
    if icp_cfg["evidence"]["audit"]:
        if ea is None:
            why.append("evidence audit pending")
        elif ea["s"] != "PASS":
            why.append(f"evidence audit {ea['s']}: {ea['r'] or 'see detail'}")
    if a.get("sms") != "Yes":
        why.append("fit not verified")
    if not (a.get("ev") or "").strip() or not (a.get("url") or "").startswith("http"):
        why.append("evidence or URL missing")
    if a["id"] in weak:
        why.append("flagged weak evidence: " + (weak[a["id"]] or "re-verify"))
    if a.get("domain") and (a.get("url") or "").startswith("http") and icp_cfg["evidence"]["own_domain_required"] \
            and registrable(host(a["domain"])) != registrable(host(a["url"])):
        why.append(f"evidence on another site ({host(a['url'])}) - re-verify on {host(a['domain'])}")
    return "; ".join(why)


def stage_of(r, v):
    """r: research row, v: verdict row (or None)."""
    if r["state"] in ("pending", "working", "requeue") and not (r["state"] == "requeue" and v):
        return "PENDING"
    if r["state"] == "failed":
        return "RETRY"
    if not v:
        return "PENDING_WEBSITE" if r["state"] == "done" else "PENDING"
    pr = v["priority"]
    if pr == "DQ":
        return "ROUTED" if (v["status"] or "").startswith("Disqualified – duplicate: routed") else "DQ"
    if pr == "HOLD":
        return "HOLD"
    if pr in ("A", "B", "C"):
        return "QUALIFIED"          # READY decided later (outreach check + dedupe)
    if v["core"] in ("Yes", "Signal"):
        return "REVIEW"
    if not r["crawl_ok"] or r["search_state"] == "pending":
        return "RETRY"
    return "REVIEW"


def retry_why(r):
    if r["state"] == "failed":
        return "research error after retries: " + (r["error"] or "").split("\n")[0][:120]
    if not r["crawl_ok"]:
        return "website unreadable / blocked"
    if r["search_state"] == "pending":
        lg = jload(r["log"], {}) or {}
        err = next((s.get("error") for s in lg.get("search", []) if s.get("error")), "")
        return "verification searches not run: " + (err or "search provider unavailable") + "; retry queued"
    return "external search not run yet"


def profile_cfgs(ws):
    from .icp.schema import normalize
    return {r["id"]: normalize(jload(r["config"], {})) for r in ws.execute("SELECT id, config FROM profiles")}


def build(ws, app=None, runner_info=None):
    cfgs = profile_cfgs(ws)
    lists = [dict(x) for x in ws.execute("SELECT * FROM lists ORDER BY id")]
    default_pid = next((x["profile_id"] for x in lists if x["profile_id"]), None) or (min(cfgs) if cfgs else None)
    weak = {r["account_id"]: r["note"] for r in ws.execute("SELECT account_id, note FROM weak")}
    rows = ws.execute("""SELECT a.*, r.state, r.pages_checked, r.searches_used, r.search_state, r.crawl_ok, r.researched_at, r.error, r.log,
                                r.profile_version AS rpv, v.priority, v.status, v.core, v.use_case, v.evidence, v.url, v.confidence, v.scale,
                                v.scale_level, v.segment, v.buyer, v.qual_reason, v.review_reason, v.missing, v.signals, v.fit_score,
                                v.score_parts, v.tech, v.tech_mentions, v.competitors, v.triggers, v.channel, v.channel_score, v.angle,
                                v.persona, v.target_tech, v.audit, v.ai, v.override, v.decided_at, v.profile_id AS vpid
                         FROM accounts a LEFT JOIN research r ON r.account_id=a.id LEFT JOIN verdicts v ON v.account_id=a.id
                         ORDER BY a.list_id, a.company_order, a.id""").fetchall()
    prim = {r["id"]: r for r in rows if r["is_primary"]}
    lname = {x["id"]: x["name"] for x in lists}
    accts = []
    for r in rows:
        lid = str(r["list_id"])
        mem = jload(r["members"], []) or []
        rowlbl = ", ".join(str(m.get("row")) for m in mem[:4]) + (" …" if len(mem) > 4 else "")
        a = {"k": f"{lid}:{r['id']}", "list": lid, "src": lname.get(r["list_id"], ""), "id": r["id"], "name": r["name"], "domain": r["domain"] or "",
             "row": rowlbl, "pos": r["company_order"] or 0, "ind": r["industry"] or "", "emp": r["employees"], "rev": r["revenue"], "loc": r["location"] or ""}
        if not r["is_primary"]:
            p = prim.get(r["company_id"])
            a.update(stage="MERGED", pr="", note=f"duplicate source row, counted under company #{p['company_order'] if p else '?'} {p['name'] if p else ''}",
                     parent=f"{lid}:{p['id']}" if p else "")
            accts.append(a)
            continue
        v = r if r["priority"] is not None else None
        st = stage_of(r, v)
        ov = jload(r["override"]) if v else None
        pr = (v["priority"] or "") if v and st not in ("PENDING",) else ""
        if ov and ov.get("priority"):
            pr = ov["priority"]
            st = {"A": "QUALIFIED", "B": "QUALIFIED", "C": "QUALIFIED", "HOLD": "HOLD", "REVIEW": "REVIEW", "DQ": "DQ"}.get(pr, st)
        cfg = cfgs.get(r["vpid"] or default_pid) or {}
        ea = jload(r["audit"]) if v else None
        aic = jload(r["ai"]) if v else None
        sigs = jload(r["signals"], {}) if v else {}
        a.update(stage=st, pr=pr, sms=(v["core"] if v["core"] in ("Yes", "Signal") else "Unverified" if v["core"] == "No" else "") if v else "",
                 uc=(v["use_case"] if v else "") or "", vert=(v["segment"] if v else "") or "GENERAL", buyer=(v["buyer"] if v else "") or "",
                 ev=((v["evidence"] if v else "") or "")[:260], url=(v["url"] if v else "") or "", conf=(v["confidence"] if v else "") or "",
                 status=(v["status"] if v else "") or "", hold="", note="", scale=(v["scale"] if v else "") or "",
                 just=(v["qual_reason"] if v else "") or "", at=r["researched_at"] or "", relation=r["relation"] or "",
                 missing=", ".join(jload(r["missing"], []) or []) if v else "", pid=r["vpid"] or default_pid,
                 sigv=", ".join(x["label"] for x in sigs.values() if x.get("status") == "VERIFIED"),
                 sigi=", ".join(x["label"] for x in sigs.values() if x.get("status") == "INFERRED"),
                 opp=(v["fit_score"] if v else None), oppx="; ".join(f"{c} {'+' if p >= 0 else ''}{p}: {w}" for c, p, w in (jload(r["score_parts"], []) or [])) if v else "",
                 cc=", ".join(jload(r["tech"], []) or []) if v else "", cci=", ".join((jload(r["tech_mentions"], []) or [])[:3]) if v else "",
                 vend=", ".join(jload(r["competitors"], []) or []) if v else "", chan=(v["channel"] if v else "") or "", chs=(v["channel_score"] if v else 0) or 0,
                 trig="; ".join((jload(r["triggers"], []) or [])[:3]) if v else "", angle=(v["angle"] if v else "") or "", persona=(v["persona"] if v else "") or "",
                 tw=(v["target_tech"] if v else "") or "", ov=ov or None)
        if ov:
            a["status"] = f"{a['status']} · edited: {ov.get('priority')} ({ov.get('note') or 'manual override'})"
        if ea and pr in ("A", "B", "C", "HOLD"):
            a["ea"] = ea
        if aic and not aic.get("none"):
            a["aic"] = aic
        if st == "QUALIFIED":
            a["hold"] = outreach_check(cfg, a, weak) if cfg else "profile missing"
            if not a["hold"]:
                a["stage"] = "READY"
        if a["stage"] == "RETRY":
            a["note"] = retry_why(r)
        elif a["stage"] == "PENDING_WEBSITE":
            a["note"] = (jload(r["log"], {}) or {}).get("note") or "no website matched - research not run"
        elif a["stage"] == "REVIEW" and v:
            a["note"] = v["review_reason"] or ""
        a["rs"] = {"PENDING": "Pending research", "PENDING_WEBSITE": "Blocked: no verified website", "RETRY": "Blocked: " + (a.get("note") or "search")}.get(a["stage"], "Research complete")
        a["nv"] = sum(1 for x in sigs.values() if x.get("status") == "VERIFIED")
        accts.append(a)
    # cross-list membership (same website, or same normalised name without a website) - never merges records
    where = {}
    for a in accts:
        if a["stage"] == "MERGED":
            continue
        for key in filter(None, {a["domain"], "n:" + norm_name(a["name"])}):
            where.setdefault(key, set()).add(a["list"])
    for a in accts:
        if a["stage"] != "MERGED":
            other = set().union(*(where.get(k, set()) for k in filter(None, {a["domain"], "n:" + norm_name(a["name"])}))) - {a["list"]}
            a["also"] = ",".join(sorted(other))
    # outreach dedupe: one READY record per website across lists
    seen = {}
    for a in sorted((a for a in accts if a["stage"] == "READY"), key=lambda a: ("ABC".index(a["pr"]) if a["pr"] in "ABC" else 3, int(a["list"]), a["pos"])):
        key = a["domain"] or "n:" + norm_name(a["name"])
        if key in seen:
            a["stage"], a["hold"] = "QUALIFIED", f"duplicate of READY {seen[key]['src']} account {seen[key]['name']} ({key})"
        else:
            seen[key] = a
    summary = {"generated": now(), "lists": {}, "profiles": {}}
    for lst in lists:
        lid = str(lst["id"])
        L = [a for a in accts if a["list"] == lid]
        C = [a for a in L if a["stage"] != "MERGED"]
        cnt = {s: sum(a["stage"] == s for a in L) for s in STAGES}
        ing = jload(lst["ingest"], {}) or {}
        recon = [["Rows in the uploaded file", lst["rows_in_file"] or 0], ["Blank rows skipped", ing.get("blank_rows", 0)],
                 ["Companies after merging same-company rows", ing.get("companies", len(C))], ["Duplicate rows merged", ing.get("merged_rows", 0)],
                 ["Units routed to a parent in the list", ing.get("routed_units", 0)], ["Entity checks (shared site / name conflict)", ing.get("entity_checks", 0)],
                 ["Original rows traced to a visible company state", (lst["rows_in_file"] or 0) - ing.get("blank_rows", 0)]]
        last_r = ws.execute("SELECT max(r.researched_at) FROM research r JOIN accounts a ON a.id=r.account_id WHERE a.list_id=?", (lst["id"],)).fetchone()[0]
        last_v = ws.execute("SELECT max(v.decided_at) FROM verdicts v JOIN accounts a ON a.id=v.account_id WHERE a.list_id=?", (lst["id"],)).fetchone()[0]
        run = ws.execute("SELECT * FROM runs WHERE list_id=? ORDER BY id DESC LIMIT 1", (lst["id"],)).fetchone()
        summary["lists"][lid] = {
            "name": lst["name"], "filename": lst["filename"], "profile_id": lst["profile_id"], "companies": len(C), "stages": cnt,
            "health": {"last_research": last_r, "last_verify": last_v}, "run": dict(run) if run else None,
            "PROCESSED": sum(a["stage"] not in ("PENDING", "MERGED") for a in L),
            "RESEARCH_COMPLETE": sum(a["stage"] in ("READY", "QUALIFIED", "HOLD", "REVIEW", "DQ", "ROUTED") for a in L),
            "EVIDENCE_AUDIT": {k: sum((a.get("ea") or {}).get("s") == k for a in C) for k in ("PASS", "NEEDS REVIEW", "FAIL")},
            "VERIFIED_SMS": sum(a.get("sms") == "Yes" and a["stage"] not in ("DQ", "ROUTED", "MERGED") for a in L),
            "ABC": {p: sum(a.get("pr") == p for a in C) for p in "ABC"},
            "READY_ABC": {p: sum(a.get("pr") == p and a["stage"] == "READY" for a in C) for p in "ABC"},
            "ready_target_verified": sum(a["stage"] == "READY" and a.get("tw") == "TARGET TECH VERIFIED" for a in C),
            "recon": recon}
    for pid, c in cfgs.items():
        summary["profiles"][str(pid)] = {"name": c["name"], "labels": c["labels"], "segments": [[s["key"], s["label"]] for s in c["segments"]] + [["GENERAL", "General"]],
                                         "has_target_tech": bool(c["target_technology"]), "describe_priority": c["priority"]["describe"],
                                         "hold_enabled": c["hold"]["enabled"]}
    summary["default_profile"] = default_pid
    summary["READY_deduped"] = sum(a["stage"] == "READY" for a in accts)
    summary["ops"] = ops_status(ws, app, runner_info)
    summary["intel"] = intel_status(ws, app, accts, runner_info)
    return summary, accts


def ops_status(ws, app, runner_info):
    lists = {}
    for lst in ws.execute("SELECT id FROM lists"):
        lid = lst["id"]
        one = lambda q, *p: ws.execute(q, (lid, *p)).fetchone()[0]
        J = "FROM research r JOIN accounts a ON a.id=r.account_id WHERE a.list_id=? AND a.is_primary=1"
        lists[str(lid)] = {"researched_1h": one(f"SELECT count(*) {J} AND r.researched_at>=?", ago_iso(1)),
                           "researched_24h": one(f"SELECT count(*) {J} AND r.researched_at>=?", ago_iso(24)),
                           "not_researched": one(f"SELECT count(*) {J} AND r.state IN ('pending','working')"),
                           "search_queue": one(f"SELECT count(*) {J} AND r.state='done' AND r.search_state='pending'"),
                           "failed": one(f"SELECT count(*) {J} AND r.state='failed'"),
                           "evidence_24h": ws.execute("SELECT count(*) FROM evidence e JOIN accounts a ON a.id=e.account_id WHERE a.list_id=? AND e.found_at>=?", (lid, ago_iso(24))).fetchone()[0],
                           "last_checkpoint": one(f"SELECT max(r.researched_at) {J}")}
    search, aist = {}, {}
    if app is not None:
        try:
            search = SEARCH.status(app)
        except Exception as e:
            search = {"error": str(e)[:120]}
        s = AI.settings(app)
        day = now()[:10]
        aist = {"provider": s["provider"], "model": s["model"] or "default", "daily_cap": s["daily_call_cap"],
                "calls_today": app.execute("SELECT count(*) FROM usage WHERE kind='ai' AND substr(at,1,10)=?", (day,)).fetchone()[0],
                "month_usd": round(app.execute("SELECT COALESCE(sum(usd),0) FROM usage WHERE kind='ai' AND substr(at,1,7)=?", (day[:7],)).fetchone()[0], 4),
                "paid_cap": s["monthly_cap_usd"], "approved": bool(s["approved"])}
    rate = sum(v["researched_1h"] for v in lists.values())
    todo = sum(v["not_researched"] for v in lists.values())
    return {"lists": lists, "search": search, "ai": aist, "runner": runner_info or {}, "research_rate_1h": rate, "not_researched": todo,
            "eta_hours_new_research": round(todo / rate, 1) if rate else None,
            "spend": {"search_month_usd": (search or {}).get("this_month_usd", 0), "ai_month_usd": aist.get("month_usd", 0)}}


def intel_status(ws, app, accts, runner_info):
    pend = sum(a["stage"] == "PENDING" for a in accts)
    per_h = ws.execute("SELECT count(*) FROM research WHERE researched_at>=?", (ago_iso(1),)).fetchone()[0]
    s = AI.settings(app) if app is not None else {"provider": "off", "model": ""}
    review_q = sum(1 for a in accts if a["stage"] == "REVIEW" and not a.get("aic"))
    return {"ai": {"provider": s["provider"], "model": s.get("model") or "default"}, "ai_queue": review_q if s["provider"] != "off" else None,
            "researched_last_hour": per_h, "pending": pend, "eta_hours_pending": round(pend / per_h, 1) if per_h else None,
            "blocked": {"retry": sum(a["stage"] == "RETRY" for a in accts), "no_website": sum(a["stage"] == "PENDING_WEBSITE" for a in accts)},
            "ai_candidates": sum(bool(a.get("aic")) for a in accts),
            "ai_candidates_strong": sum((a.get("aic") or {}).get("strength") == "STRONG" for a in accts),
            "with_verified_signals": sum((a.get("nv") or 0) > 0 for a in accts), "runner": runner_info or {}, "at": time.time()}


def detail(ws, aid):
    one = lambda q: dict(ws.execute(q, (aid,)).fetchone() or {})
    many = lambda q: [dict(x) for x in ws.execute(q, (aid,))]
    d = {"account": one("SELECT * FROM accounts WHERE id=?"), "research": one("SELECT * FROM research WHERE account_id=?"),
         "verdict": one("SELECT * FROM verdicts WHERE account_id=?"),
         "evidence": many("SELECT signal_id,label,kind,status,confidence,url,snippet,use_cases,marker,mentions_org,found_at,reason FROM evidence WHERE account_id=? "
                          "ORDER BY CASE status WHEN 'VERIFIED' THEN 0 WHEN 'INFERRED' THEN 1 ELSE 2 END, marker DESC LIMIT 40"),
         "history": many("SELECT changed_at,change,old_priority,new_priority,note FROM verdict_history WHERE account_id=? ORDER BY id"),
         "discovery": one("SELECT found_at,domain,verified,query FROM website_discovery WHERE account_id=?")}
    r = d["research"]
    if r.get("log") and len(r["log"]) > 6000:
        r["log"] = r["log"][:6000] + " …"
    if d["account"].get("parent_id"):
        p = ws.execute("SELECT name, domain FROM accounts WHERE id=?", (d["account"]["parent_id"],)).fetchone()
        d["parent"] = dict(p) if p else None
    return d


def files(accts, lists):
    ready = sorted((a for a in accts if a["stage"] == "READY"), key=lambda a: ("ABC".index(a["pr"]), -(a.get("opp") or 0), a["list"], a["name"]))
    live = [a for a in accts if a["stage"] != "MERGED"]
    out = {"MASTER_ALL_ACCOUNTS": accts,
           "OUTREACH_READY": ready,
           "PRIORITY_A_ACCOUNTS": [a for a in ready if a["pr"] == "A"],
           "TECHNOLOGY_OPPORTUNITIES": sorted((a for a in live if a.get("cc") and a["stage"] not in ("DQ", "ROUTED")), key=lambda a: -(a.get("opp") or 0)),
           "CHANNEL_PARTNER_OPPORTUNITIES": sorted((a for a in live if a.get("chan", "").startswith("CHANNEL")), key=lambda a: -(a.get("chs") or 0)),
           "ACTIVE_BUYING_SIGNALS": sorted((a for a in live if a.get("trig") and a["stage"] not in ("DQ", "ROUTED")), key=lambda a: -(a.get("opp") or 0)),
           "REVIEW_AND_HOLD": [a for a in live if a["stage"] in ("REVIEW", "QUALIFIED", "HOLD") or (a.get("aic") and a["stage"] != "READY")],
           "RESEARCH_BLOCKED": [a for a in live if a["stage"] in ("RETRY", "PENDING_WEBSITE")],
           "TARGET_TECH_VERIFIED": [a for a in ready if a.get("tw") == "TARGET TECH VERIFIED"]}
    for lst in lists:
        lid = str(lst["id"])
        out[f"LIST_{lid}_QUALIFIED"] = [a for a in ready if a["list"] == lid]
        out[f"LIST_{lid}_ALL"] = [a for a in accts if a["list"] == lid]
    return out
