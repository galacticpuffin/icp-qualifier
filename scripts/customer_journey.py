"""Real-browser test of the whole customer journey as a NEW customer on a server they don't run:
sign up -> describe business (+ Draft) -> guided ICP -> upload + auto-mapping -> Start research -> live progress -> dashboard
(filters, scores, reasons, sources, decision-makers) -> edit ICP with guided questions -> requalify -> exports -> settings.
python scripts/customer_journey.py --out DIR"""
import os, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
out = Path(sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "test-results"); out.mkdir(parents=True, exist_ok=True)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
data = Path(tempfile.mkdtemp())
env = {**os.environ, "ICPQ_DATA": str(data), "ICPQ_PORT": str(port), "ICPQ_FIXTURE_SITES": str(ROOT / "tests/fixtures/sites"), "ICPQ_PBKDF2_ITER": "2000",
       "ICPQ_THREADS": "2", "ICPQ_ADMIN_EMAIL": "operator@host.example", "ICPQ_ADMIN_PASSWORD": "operator-password-1"}
srv = subprocess.Popen([sys.executable, "-m", "icpq", "serve"], cwd=ROOT, env=env, stderr=subprocess.DEVNULL)
base = f"http://127.0.0.1:{port}"
for _ in range(100):
    try: urllib.request.urlopen(base + "/healthz", timeout=1); break
    except Exception: time.sleep(0.2)
step = lambda n, msg: print(f"{n:>2}. {msg}", flush=True)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base + "/"); expect(pg).to_have_url(base + "/login")
        pg.click("#toSignup"); pg.wait_for_url("**/signup")
        pg.fill("#n", "Pat Customer"); pg.fill("#e", "pat@customer.example"); pg.fill("#p", "pat-strong-password"); pg.fill("#w", "Acme Telematics")
        pg.click("button[type=submit]"); pg.wait_for_url("**/wizard"); step(1, "signed up, private workspace created, landed in the wizard")
        f = pg.locator("#qbody input, #qbody textarea")
        f.nth(0).fill("Acme Telematics"); f.nth(1).fill("GPS fleet tracking"); f.nth(2).fill("We sell to HVAC and plumbing companies that run their own service vans.")
        pg.click("#draft"); expect(pg.locator("#draftMsg")).not_to_contain_text("Drafting", timeout=60000)
        step(2, "Draft my ICP: " + pg.locator("#draftMsg").inner_text()[:110])
        pg.click("#next")
        pg.get_by_role("button", name="Logistics / fleet / transportation").click(); pg.click("#next")
        pg.locator("#qbody textarea").fill("Service companies running their own vans"); pg.click("#next")
        while "buying committee" not in pg.locator("#qprompt").inner_text():
            if "website" in pg.locator("#qprompt").inner_text() and "signals" in pg.locator("#qprompt").inner_text():
                pg.get_by_text("Operates a vehicle fleet").click()
            pg.click("#skip")
        pg.locator("#qbody input").nth(0).fill("Fleet Manager"); pg.keyboard.press("Enter"); pg.click("#next")
        while "what your engine will do" not in pg.locator("#qprompt").inner_text(): pg.click("#skip")
        pg.screenshot(path=str(out / "j_review.png"), full_page=True)
        pg.click("#next"); pg.wait_for_url("**/lists**"); step(3, "guided ICP saved (rules reviewed in plain English)")
        pg.set_input_files("#file", str(ROOT / "samples/data/fleet_list.csv")); expect(pg.locator("#mapBox")).to_be_visible()
        assert pg.locator('[data-f=name]').input_value() == "Company" and pg.locator('[data-f=website]').input_value() == "Website"
        step(4, "uploaded; columns auto-mapped (Company, Website, Industry, Employees, Revenue)")
        pg.click("#go"); expect(pg.locator("#gomsg")).to_contain_text("Research started", timeout=20000); step(5, "Start research clicked")
        seen = set()
        for _ in range(90):
            t = pg.locator("#ltb").inner_text(); seen.add(" ".join(t.split())[:80])
            if " done" in t: break
            time.sleep(2); pg.reload()
        step(6, f"live progress observed ({len(seen)} distinct states), run done")
        time.sleep(11); pg.goto(base + "/"); expect(pg.locator("#kv-READY")).to_have_text("1", timeout=20000)
        pg.click("tr.r >> nth=0"); expect(pg.locator("tr.d")).to_contain_text("Jane Smith", timeout=15000)
        dtxt = pg.locator("tr.d").inner_text().lower(); assert "jane.smith@fastfleet-hvac.com" in dtxt and "evidence pass" in dtxt and "fit score" in dtxt, dtxt[:600]
        pg.locator(".results").screenshot(path=str(out / "j_row.png")); step(7, "dashboard: READY account, score, reasons, source link, audit PASS, decision-maker Jane Smith (Fleet Manager) with e-mail")
        pg.click("#fBtn"); pg.click("label[for=fp-Y]"); pg.click("#fDone"); expect(pg.locator("#ttl")).to_contain_text("1"); step(8, "filter 'Has decision-makers' works")
        with pg.expect_download() as d: pg.click("#exp")
        d.value.save_as(out / "view.csv"); assert "FastFleet" in (out / "view.csv").read_text()
        with pg.expect_download() as d: pg.click("#expx")
        d.value.save_as(out / "view.xlsx"); assert (out / "view.xlsx").read_bytes()[:2] == b"PK"
        pg.click("summary:has-text('Final files')")
        with pg.expect_download() as d: pg.click("a[href='/export/DECISION_MAKERS.csv']")
        d.value.save_as(out / "dm.csv"); assert "Jane Smith" in (out / "dm.csv").read_text()
        step(9, "exports: view CSV + Excel, decision-makers CSV downloaded from the UI")
        pg.goto(base + "/profiles"); pg.click("#editWiz"); pg.wait_for_url("**/wizard?profile=*")
        while "Target industries" not in pg.locator("#wtopic").inner_text(): pg.click("#next")
        pg.locator("#qbody input").first.fill("HVAC Services"); pg.keyboard.press("Enter")
        while "what your engine will do" not in pg.locator("#qprompt").inner_text(): pg.click("#next")
        pg.click("#next"); pg.wait_for_url("**/profiles?id=*"); expect(pg.locator("#ptitle")).to_contain_text("v2")
        pg.click("#rq"); pg.wait_for_url("**/lists")
        for _ in range(60):
            if "requalify · done" in pg.locator("#ltb").inner_text(): break
            time.sleep(2); pg.reload()
        step(10, "edited ICP with guided questions (v2) and requalified without re-uploading")
        pg.goto(base + "/settings"); time.sleep(1.5)
        opts = pg.locator("#aiP option").all_inner_texts(); assert not any("CLI" in o for o in opts)
        pg.select_option("#cP", "site"); pg.click("#cSave"); expect(pg.locator("#cMsg")).to_contain_text("Saved")
        pg.screenshot(path=str(out / "j_settings.png"), full_page=True); step(11, "settings: providers, keys, caps, contacts, usage, team all in the UI")
        assert not errs, errs
        b.close()
    print("CUSTOMER JOURNEY PASS")
finally:
    srv.terminate()
