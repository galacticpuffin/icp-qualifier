"""Onboarding -> ICP -> upload -> map -> research -> qualification -> export, for three unrelated ICPs, plus auth and isolation."""
import time
from pathlib import Path

from conftest import Client

ROOT = Path(__file__).resolve().parent.parent
PW = "correct-horse-battery"

FLEET = {"company_name": "Acme Telematics", "sells": "GPS fleet tracking", "pack": "logistics", "industries": [],
         "signals": [{"id": "fleet", "label": "Operates a vehicle fleet", "category": "operational", "patterns": ["our fleet", "fleet of", "service vans"], "requirement": "mandatory", "weight": 20},
                     {"id": "drivers_hiring", "label": "Hiring drivers", "category": "buying", "patterns": ["now hiring drivers", "cdl"], "requirement": "preferred", "weight": 15}],
         "competitors": ["Samsara"], "competitor_stance": "prospect", "titles": ["Fleet Manager"], "departments": ["Operations"], "disqualifiers": ["agency"], "evidence_level": "standard",
         "sources": {"sitemap": False, "search": False, "discover": False}}
CLINIC = {"company_name": "SchedulePro", "sells": "patient scheduling", "pack": "healthcare",
          "signals": [{"id": "online_booking", "label": "Online appointment booking", "category": "behavioral", "patterns": ["book an appointment", "book online", "schedule online"],
                       "markers": ["book online", "schedule online"], "requirement": "mandatory", "weight": 20},
                      {"id": "telehealth", "label": "Telehealth", "category": "behavioral", "patterns": ["telehealth"], "requirement": "preferred", "weight": 10}],
          "evidence_level": "strict", "priority_mode": "score", "a_min_score": 70, "b_min_score": 40, "sources": {"search": False, "discover": False}}
MSG = {"company_name": "MsgCo", "sells": "SMS routing", "pack": "messaging", "competitors": ["TextVendor"], "disqualifiers": ["competitor"],
       "evidence_level": "strict", "sources": {"search": False, "discover": False}}


def setup_and_login(server):
    c = Client(server["base"])
    code = (server["data"] / "SETUP_CODE").read_text().strip()
    st, b = c.call("POST", "/api/setup", {"code": "WRONG", "email": "a@x.io", "password": PW})
    assert st == 403
    st, b = c.call("POST", "/api/setup", {"code": code, "email": "admin@example.com", "password": PW, "workspace": "Fleet WS"})
    assert st == 200, b
    c.login("admin@example.com", PW)
    return c


def build_profile(c, answers):
    st, pack = c.call("GET", "/api/wizard")
    assert st == 200 and len(pack["questions"]) >= 15
    if answers["pack"] == "messaging":       # take the pack's suggested signals, as a user clicking chips would
        answers = {**answers, "signals": [s for p in pack["packs"] if p["id"] == "messaging" for s in p["signals"]]}
    st, b = c.call("POST", "/api/wizard/build", {"answers": answers})
    assert st == 200 and not b["errors"], b["errors"]
    st, b = c.call("POST", "/api/profiles", {"answers": answers})
    assert st == 200, b
    return b["id"]


def run_list(c, csv_name, pid, mapping=None):
    data = (ROOT / "samples/data" / csv_name).read_bytes()
    st, up = c.call("POST", "/api/lists/upload", data, headers={"X-Filename": csv_name, "Content-Type": "application/octet-stream"})
    assert st == 200, up
    st, ing = c.call("POST", f"/api/lists/{up['id']}/ingest", {"mapping": mapping or up["mapping"], "profile_id": pid})
    assert st == 200, ing
    st, r = c.call("POST", "/api/runs", {"list_id": up["id"], "profile_id": pid, "mode": "research", "threads": 2})
    assert st == 200, r
    for _ in range(150):
        runs = c.call("GET", "/api/runs")[1]["runs"]
        if all(x["status"] in ("done", "error", "stopped") for x in runs):
            break
        time.sleep(0.3)
    assert all(x["status"] == "done" for x in runs), runs
    return up["id"], ing["stats"]


def accounts(c):
    st, a = c.call("GET", "/api/accounts.json")
    assert st == 200
    return {x["name"]: x for x in a if x["stage"] != "MERGED"}


def test_full_workflow_three_icps(server):
    c = setup_and_login(server)
    assert c.call("GET", "/api/profiles")[0] == 200
    # ---- ICP 1: fleet telematics
    p1 = build_profile(c, FLEET)
    lid, stats = run_list(c, "fleet_list.csv", p1)
    assert stats["rows_in_file"] == 4 and stats["companies"] == 3 and stats["merged_rows"] == 1 and stats["no_website"] == 1
    time.sleep(11)          # dashboard snapshot cache
    A = accounts(c)
    ff = A["FastFleet HVAC"]
    assert ff["pr"] in ("A", "B", "C") and ff["sms"] == "Yes", ff
    assert ff["url"].startswith("https://fastfleet-hvac.com"), ff
    assert "Samsara" in ff["vend"]
    assert ff["ea"]["s"] == "PASS" and ff["stage"] == "READY", ff
    assert ff["npl"] >= 2 and ff["dmc"] >= 1 and "jane.smith@fastfleet-hvac.com" in ff["dm"], ff
    st, dm = c.call("GET", "/export/DECISION_MAKERS.csv", raw=True)
    assert st == 200 and b"Jane Smith" in dm and b"Fleet Manager" in dm
    assert A["DeskOnly Consulting"]["stage"] in ("REVIEW", "DQ")
    assert A["No Website Plumbing"]["stage"] == "PENDING_WEBSITE"
    merged = [x for x in c.call("GET", "/api/accounts.json")[1] if x["stage"] == "MERGED"]
    assert len(merged) == 1
    st, s = c.call("GET", "/api/summary.json")
    rec = s["lists"][str(lid)]
    assert sum(rec["stages"].values()) == rec["recon"][-1][1]       # every original row has a visible state
    # exports
    st, csv = c.call("GET", "/export/OUTREACH_READY.csv", raw=True)
    assert st == 200 and b"FastFleet HVAC" in csv and b"DeskOnly" not in csv
    st, x = c.call("GET", "/export/MASTER_ALL_ACCOUNTS.xlsx", raw=True)
    assert st == 200 and x[:2] == b"PK"
    st, m = c.call("GET", "/export/MANIFEST.json")
    assert st == 200 and "OUTREACH_READY.csv" in m["files"]
    # override + history
    k = ff["k"]
    assert c.call("POST", "/api/account/override", {"k": k, "priority": "B", "note": "rep call"})[0] == 200
    st, d = c.call("GET", f"/api/account?k={k}")
    assert any(h["change"] == "manual override" for h in d["history"])
    # ---- ICP 2 in a separate workspace: isolation
    assert c.call("POST", "/api/workspaces", {"name": "Clinic WS"})[0] == 200
    assert c.call("GET", "/api/profiles")[1]["profiles"] == []
    p2 = build_profile(c, CLINIC)
    run_list(c, "clinic_list.csv", p2)
    time.sleep(11)
    A = accounts(c)
    assert "FastFleet HVAC" not in A
    bs = A["BrightSmile Dental Group"]
    assert bs["sms"] == "Yes" and bs["pr"] in ("A", "B", "C"), bs
    assert A["BrightSmile Dental - Austin Office"]["stage"] == "ROUTED"
    assert A["WellCare Clinic"]["stage"] == "REVIEW"          # only a blog page: rejected evidence, never verified
    # ---- ICP 3: messaging, competitor DQ, warning text rejected
    assert c.call("POST", "/api/workspaces", {"name": "Messaging WS"})[0] == 200
    p3 = build_profile(c, MSG)
    lid3, _ = run_list(c, "messaging_list.csv", p3)
    time.sleep(11)
    A = accounts(c)
    assert A["Metro Credit Union"]["stage"] == "READY", A["Metro Credit Union"]
    assert A["ScamWarn Bank"]["sms"] != "Yes"
    assert A["TextVendor"]["stage"] == "DQ"
    # requalify with a stricter rule: no network needed, verdict changes, history records it
    st, prof = c.call("GET", f"/api/profiles/{p3}")
    cfg = prof["config"]
    cfg["signals"][0]["patterns"] = ["this phrase appears nowhere"]
    cfg["signals"][0]["markers"] = []
    assert c.call("PUT", f"/api/profiles/{p3}", {"config": cfg, "note": "stricter"})[0] == 200
    c.call("POST", "/api/runs", {"list_id": lid3, "profile_id": p3, "mode": "requalify"})
    for _ in range(100):
        if all(x["status"] in ("done", "error") for x in c.call("GET", "/api/runs")[1]["runs"]):
            break
        time.sleep(0.3)
    time.sleep(11)
    assert accounts(c)["Metro Credit Union"]["stage"] == "REVIEW"


def test_signup_creates_private_workspace(server):
    c = Client(server["base"])
    st, b = c.call("POST", "/api/signup", {"name": "Pat", "email": "pat@customer.example", "password": "another-long-password", "workspace": "Pat Co"})
    assert st == 200, b
    c.csrf = c.call("GET", "/api/me")[1]["csrf"]
    me = c.call("GET", "/api/me")[1]
    assert [w["name"] for w in me["workspaces"]] == ["Pat Co"]
    assert c.call("GET", "/api/profiles")[1]["profiles"] == []          # nothing from other customers
    st, s = c.call("GET", "/api/settings")
    assert st == 200 and s["is_admin"] and s["ai"]["provider"] == "off"   # owner of their own workspace, own provider settings
    assert c.call("POST", "/api/settings", {"ai": {"provider": "claude-cli"}})[0] == 400   # server's own CLI is not offered to customers


def test_auth_and_csrf(server):
    anon = Client(server["base"])
    assert anon.call("GET", "/api/summary.json")[0] == 401
    st, _ = anon.call("POST", "/api/login", {"email": "admin@example.com", "password": "wrong-password"})
    assert st == 403
    c = Client(server["base"])
    c.login("admin@example.com", PW)
    c.csrf = "bad"
    assert c.call("POST", "/api/workspaces", {"name": "x"})[0] == 403
