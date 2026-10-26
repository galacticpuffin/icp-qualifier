"""Build a self-contained, read-only snapshot of the dashboard (demo data from the fixture sites) as one HTML file.
python scripts/build_snapshot.py OUT.html"""
import json, os, re, sys, time, tempfile, subprocess, socket, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT))
from conftest import Client
import test_e2e_workflow as T

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
data = Path(tempfile.mkdtemp())
env = {**os.environ, "ICPQ_DATA": str(data), "ICPQ_PORT": str(port), "ICPQ_FIXTURE_SITES": str(ROOT / "tests/fixtures/sites"),
       "ICPQ_PBKDF2_ITER": "2000", "ICPQ_THREADS": "2", "ICPQ_ADMIN_EMAIL": "demo@example.com", "ICPQ_ADMIN_PASSWORD": "demo-password-123", "ICPQ_WORKSPACE": "Demo Workspace"}
srv = subprocess.Popen([sys.executable, "-m", "icpq", "serve"], cwd=ROOT, env=env, stderr=subprocess.DEVNULL)
base = f"http://127.0.0.1:{port}"
for _ in range(100):
    try: urllib.request.urlopen(base + "/healthz", timeout=1); break
    except Exception: time.sleep(0.2)
try:
    c = Client(base); c.login("demo@example.com", "demo-password-123")
    for ans, csvf in [] if "--empty" in sys.argv else ((T.FLEET, "fleet_list.csv"), (T.CLINIC, "clinic_list.csv"), (T.MSG, "messaging_list.csv")):
        T.run_list(c, csvf, T.build_profile(c, dict(ans)))
    time.sleep(11)
    S = c.call("GET", "/api/summary.json")[1]
    A = c.call("GET", "/api/accounts.json")[1]
    D = {a["k"]: c.call("GET", "/api/account?k=" + a["k"])[1] for a in A if a["stage"] != "MERGED"}
    P = {pid: c.call("GET", f"/api/profiles/{pid}")[1]["rules"] for pid in S["profiles"]}
finally:
    srv.terminate()
W = ROOT / "icpq/web"
html = (W / "master.html").read_text()
body = html.split('<div class="wrap">', 1)[1].split('<script src=')[0]
body = body.replace('<nav class="nav" id="nav" aria-label="Main"></nav>',
                    '<p class="snapnote">ICP Qualifier dashboard. This view is read-only. Set up your ICP, upload your list and run research in the app (http://localhost:8890); your results appear here once you publish a new snapshot.</p>')
css = (W / "static/orig.css").read_text() + (W / "static/app.css").read_text() + """
body{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.edit,#exp,#expx,.results details.btn,#sigForm{display:none!important}
.snapnote{margin:0;font-size:.82rem;color:var(--muted);border:1px solid var(--line-2);border-radius:10px;padding:10px 14px;background:var(--surface)}
"""
js = (W / "static/master.js").read_text()
shim = """
const SNAP = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => (n ?? 0).toLocaleString("en-US");
const $ = id => document.getElementById(id);
let ME = {csrf: ""};
async function loadMe(){ return ME; }
function nav(){}
function download(){}
async function api(path){
  if (path.startsWith("/api/summary.json")) return {...SNAP.summary, last_success: new Date().toISOString()};
  if (path.startsWith("/api/accounts.json")) return SNAP.accounts;
  if (path.startsWith("/api/account?k=")) return SNAP.details[decodeURIComponent(path.split("k=")[1])] || {error: "not in snapshot"};
  const m = /^\\/api\\/profiles\\/(\\d+)$/.exec(path); if (m) return {rules: SNAP.rules[m[1]] || []};
  throw new Error("This is a read-only snapshot");
}
"""
snap = json.dumps({"summary": S, "accounts": A, "details": D, "rules": P}).replace("</", "<\\/")
out = f"""<title>ICP Qualifier Dashboard</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>{css}</style>
<div class="wrap">{body}
<script>{shim.replace("__DATA__", snap)}
{js}</script>
"""
Path(sys.argv[1]).write_text(out)
print("wrote", sys.argv[1], len(out), "bytes;", len(A), "accounts")
