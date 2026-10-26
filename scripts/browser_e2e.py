"""Real-browser end-to-end test + screenshots: setup -> wizard (clicking) -> upload -> map -> research -> dashboard -> row detail.
python scripts/browser_e2e.py --out DIR    (starts its own server on a free port with a temporary data dir and fixture websites)"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
out = Path(sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "test-results")
out.mkdir(parents=True, exist_ok=True)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
data = Path(tempfile.mkdtemp())
env = {**os.environ, "ICPQ_DATA": str(data), "ICPQ_PORT": str(port), "ICPQ_FIXTURE_SITES": str(ROOT / "tests/fixtures/sites"), "ICPQ_PBKDF2_ITER": "2000", "ICPQ_THREADS": "2"}
srv = subprocess.Popen([sys.executable, "-m", "icpq", "serve"], cwd=ROOT, env=env, stderr=subprocess.DEVNULL)
base = f"http://127.0.0.1:{port}"
for _ in range(100):
    try:
        urllib.request.urlopen(base + "/healthz", timeout=1); break
    except Exception:
        time.sleep(0.2)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "/")
        expect(pg).to_have_url(base + "/setup")
        pg.fill("#c", (data / "SETUP_CODE").read_text().strip()); pg.fill("#e", "admin@example.com"); pg.fill("#p", "correct-horse-battery"); pg.fill("#w", "Acme Telematics")
        pg.click("button[type=submit]")
        pg.wait_for_url(base + "/wizard")
        # Q1 company
        pg.locator("#qbody input").nth(0).fill("Acme Telematics"); pg.locator("#qbody textarea").fill("GPS fleet tracking for service businesses")
        pg.click("#next")
        pg.get_by_role("button", name="Logistics / fleet / transportation").click()
        pg.screenshot(path=str(out / "wizard_market.png"))
        pg.click("#next")                                   # ideal
        pg.locator("#qbody textarea").fill("Service companies running their own vans"); pg.click("#next")
        for _ in range(6):                                  # industries, exclude, size, locations, tech, competitors
            pg.click("#skip")
        pg.click("#skip")                                   # problems
        pg.click("#skip")                                   # buying
        pg.get_by_text("Operates a vehicle fleet").click()  # research signals: take a suggestion
        pg.screenshot(path=str(out / "wizard_signals.png"))
        pg.click("#next")                                   # committee
        pg.click("#skip"); pg.click("#skip")                # committee, disqualifiers
        expect(pg.locator("#qprompt")).to_contain_text("mandatory")
        pg.click("#next")                                   # roles (fleet is mandatory by default)
        pg.click("#skip"); pg.click("#skip"); pg.click("#skip"); pg.click("#skip"); pg.click("#skip")   # priority, evidence, hold, sources, export
        expect(pg.locator("#qprompt")).to_contain_text("what your engine will do")
        pg.screenshot(path=str(out / "wizard_review.png"), full_page=True)
        pg.click("#next")
        pg.wait_for_url("**/lists**")
        pg.set_input_files("#file", str(ROOT / "samples/data/fleet_list.csv"))
        expect(pg.locator("#mapBox")).to_be_visible()
        pg.screenshot(path=str(out / "lists_mapping.png"), full_page=True)
        pg.click("#go")
        expect(pg.locator("#gomsg")).to_contain_text("Research started", timeout=20000)
        for _ in range(60):
            if "done" in pg.locator("#ltb").inner_text():
                break
            time.sleep(1); pg.reload()
        time.sleep(11)
        pg.goto(base + "/")
        expect(pg.locator("#kv-READY")).to_have_text("1", timeout=20000)
        pg.screenshot(path=str(out / "dashboard_top.png"))
        pg.screenshot(path=str(out / "dashboard_full.png"), full_page=True)
        pg.click("tr.r >> nth=0"); pg.wait_for_selector("tr.d"); time.sleep(1.5)
        pg.locator(".results").screenshot(path=str(out / "dashboard_row_open.png"))
        pg.click("#fBtn"); pg.screenshot(path=str(out / "dashboard_filters.png"))
        pg.set_viewport_size({"width": 390, "height": 844}); pg.goto(base + "/"); time.sleep(2)
        pg.screenshot(path=str(out / "dashboard_phone_full.png"), full_page=True)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        assert sw <= 390 + 1, f"horizontal scroll on phone: {sw}"
        for path in ("/profiles", "/settings"):
            pg.set_viewport_size({"width": 1440, "height": 900}); pg.goto(base + path); time.sleep(1.5)
            pg.screenshot(path=str(out / f"page{path.replace('/', '_')}.png"), full_page=True)
        assert not errors, errors
        b.close()
    print("BROWSER E2E PASS; screenshots in", out)
finally:
    srv.terminate()
