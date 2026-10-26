"""HTTP server: pages, JSON API, exports. Standard library only (ThreadingHTTPServer).

Every /api and /export request except setup/login/health needs a signed-in session; every workspace-scoped request is
checked against the user's membership of the session's current workspace, and only that workspace's database is opened.
State-changing requests need the session's CSRF token (X-CSRF header)."""
import gzip
import json
import logging
import os
import re
import threading
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, auth, db, ingest
from . import dashboard as DASH
from . import exports as EXP
from .engine import ai as AI
from .engine import extract
from .engine import search as SEARCH
from .icp import packs, schema, wizard
from .runner import Runner, create_run, set_run_status
from .secrets import masked, set_secret
from .sheets import to_csv_text
from .util import jdump, jload, now

log = logging.getLogger("icpq.server")
WEB = Path(__file__).resolve().parent / "web"
MAX_UPLOAD = int(os.environ.get("ICPQ_MAX_UPLOAD_MB", "25")) * 1024 * 1024
RUNNER = Runner()
NO_AUTH = os.environ.get("ICPQ_NO_AUTH") == "1"
_cache = {}
_cache_lock = threading.Lock()
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
PAGES = {"/": "master.html", "/index.html": "master.html", "/wizard": "wizard.html", "/profiles": "profiles.html", "/lists": "lists.html",
         "/settings": "settings.html", "/login": "login.html", "/setup": "setup.html"}
PUBLIC = {"/login", "/setup", "/healthz", "/readyz", "/api/login", "/api/setup", "/api/setup-state"}


class HTTPError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def invalidate(wid):
    with _cache_lock:
        _cache.pop(int(wid), None)


def runner_info():
    alive = [k for k, t in RUNNER.active.items() if t.is_alive()]
    return {"active_runs": len(alive), "threads_default": RUNNER.threads_default}


def snapshot(wid, max_age=10):
    with _cache_lock:
        c = _cache.get(int(wid))
        if c and time.time() - c["t"] < max_age:
            return c
    ws, app = db.ws_db(wid), db.app_db()
    try:
        s, a = DASH.build(ws, app, runner_info())
    finally:
        ws.close()
        app.close()
    c = {"t": time.time(), "summary": s, "accts": a, "gz": gzip.compress(json.dumps(a, separators=(",", ":"), default=str).encode(), 6)}
    with _cache_lock:
        _cache[int(wid)] = c
    return c


class Handler(BaseHTTPRequestHandler):
    server_version = "ICPQualifier"
    sys_version = ""

    def log_message(self, fmt, *a):
        log.debug("%s %s", self.address_string(), fmt % a)

    # ------------------------------------------------------------ plumbing
    def send(self, body, ctype="application/json", code=200, extra=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if getattr(self, "_new_cookie", None) and not any(k == "Set-Cookie" for k in (extra or {})):
            for k, v in self.set_session_cookie(self._new_cookie).items():
                self.send_header(k, v)
            self._new_cookie = None
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def j(self, obj, code=200, extra=None):
        return self.send(json.dumps(obj, default=str), "application/json", code, extra)

    def cookie(self, name):
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return c[name].value if name in c else ""

    def body(self, limit=2 * 1024 * 1024):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit:
            raise HTTPError(413, f"Upload too large (limit {limit // 1024 // 1024} MB).")
        return self.rfile.read(n) if n else b""

    def json_body(self):
        try:
            return json.loads(self.body() or b"{}")
        except ValueError:
            raise HTTPError(400, "Request body is not valid JSON.")

    def ip(self):
        return self.client_address[0]

    def secure_cookie(self):
        return os.environ.get("ICPQ_SECURE_COOKIES") == "1"

    def set_session_cookie(self, tok, clear=False):
        attrs = "; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if self.secure_cookie() else "")
        return {"Set-Cookie": f"icpq={'' if clear else tok}{attrs}; Max-Age={0 if clear else auth.SESSION_S}"}

    # ------------------------------------------------------------ dispatch
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        app = db.app_db()
        try:
            if p in ("/healthz", "/readyz"):
                app.execute("SELECT 1").fetchone()
                return self.j({"ok": True, "version": __version__, "time": now()})
            if p.startswith("/static/"):
                return self.static(p)
            sess = auth.session(app, self.cookie("icpq"))
            if not sess and NO_AUTH:          # single-user local mode: sign in automatically as the local admin
                tok = auth.local_session(app)
                if p in ("/login", "/setup"):
                    self.send_response(303)
                    self.send_header("Location", "/")
                    for k, v in self.set_session_cookie(tok).items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self._new_cookie = tok
                sess = auth.session(app, tok)
            if p not in PUBLIC and not sess:
                if p.startswith("/api/") or p.startswith("/export/"):
                    raise HTTPError(401, "Sign in first.")
                return self.redirect("/setup" if auth.needs_setup(app) else "/login")
            if method != "GET" and p not in ("/api/login", "/api/setup") and sess:
                if (self.headers.get("X-CSRF") or "") != sess["csrf"]:
                    raise HTTPError(403, "Security check failed: reload the page and try again.")
            if method == "GET" and p in PAGES:
                return self.page(p, app, sess)
            return self.api(method, p, q, app, sess)
        except HTTPError as e:
            return self.j({"error": e.msg}, e.code)
        except (ValueError, PermissionError) as e:
            return self.j({"error": str(e)}, 400 if isinstance(e, ValueError) else 403)
        except Exception as e:
            log.error("request failed: %s %s\n%s", method, p, traceback.format_exc())
            return self.j({"error": f"Server error ({type(e).__name__}). Details are in the server log."}, 500)
        finally:
            app.close()

    def redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def static(self, p):
        name = p.removeprefix("/static/")
        if not re.fullmatch(r"[a-z0-9_.-]+\.(css|js|svg|png|woff2)", name):
            raise HTTPError(404, "not found")
        f = WEB / "static" / name
        if not f.is_file():
            raise HTTPError(404, "not found")
        ctype = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml", "png": "image/png", "woff2": "font/woff2"}[name.rsplit(".", 1)[1]]
        return self.send(f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))

    def page(self, p, app, sess):
        if p == "/setup" and not auth.needs_setup(app):
            return self.redirect("/login")
        if p in ("/", "/index.html") and sess and sess.get("workspace_id"):
            ws = db.ws_db(sess["workspace_id"])
            try:
                if not ws.execute("SELECT 1 FROM profiles WHERE archived=0").fetchone():
                    return self.redirect("/wizard")
            finally:
                ws.close()
        html = (WEB / PAGES[p]).read_text(encoding="utf-8")
        return self.send(html, "text/html; charset=utf-8")

    # ------------------------------------------------------------ API
    def ws_of(self, app, sess, need="member"):
        wid = sess.get("workspace_id")
        if not wid:
            raise HTTPError(409, "Create or choose a workspace first.")
        r = auth.role(app, sess["user_id"], wid)
        if not r:
            raise HTTPError(403, "You are not a member of this workspace.")
        if need == "owner" and r != "owner" and not sess["is_admin"]:
            raise HTTPError(403, "Only the workspace owner can do that.")
        return wid, db.ws_db(wid)

    def api(self, method, p, q, app, sess):
        # ---------------- setup / auth
        if p == "/api/setup-state":
            return self.j({"needs_setup": auth.needs_setup(app)})
        if p == "/api/setup" and method == "POST":
            if not auth.needs_setup(app):
                raise HTTPError(409, "Setup is already done. Sign in instead.")
            b = self.json_body()
            key = f"setup:{self.ip()}"
            if auth.throttled(app, key):
                raise HTTPError(429, "Too many attempts. Wait 15 minutes.")
            if (b.get("code") or "").strip().upper() != auth.setup_code():
                auth.note_fail(app, key)
                raise HTTPError(403, "That setup code is wrong. It is in the server log and in data/SETUP_CODE.")
            uid = auth.create_user(app, b.get("email"), b.get("password"), b.get("name"), admin=True)
            auth.create_workspace(app, b.get("workspace") or "My workspace", uid)
            try:
                (db.data_dir() / "SETUP_CODE").unlink()
            except OSError:
                pass
            tok = auth.new_session(app, uid)
            db.audit(app, uid, None, "setup", b.get("email"))
            return self.j({"ok": True}, extra=self.set_session_cookie(tok))
        if p == "/api/login" and method == "POST":
            b = self.json_body()
            tok = auth.login(app, b.get("email"), b.get("password"), self.ip())
            return self.j({"ok": True}, extra=self.set_session_cookie(tok))
        if p == "/api/logout" and method == "POST" and NO_AUTH:
            return self.j({"ok": True})
        if p == "/api/logout" and method == "POST":
            auth.logout(app, self.cookie("icpq"))
            return self.j({"ok": True}, extra=self.set_session_cookie("", clear=True))
        if p == "/api/me":
            wss = [dict(r) for r in app.execute("SELECT w.id, w.name, m.role FROM workspaces w JOIN members m ON m.workspace_id=w.id WHERE m.user_id=? ORDER BY w.id", (sess["user_id"],))]
            return self.j({"email": sess["email"], "name": sess["name"], "is_admin": bool(sess["is_admin"]), "csrf": sess["csrf"],
                           "workspace_id": sess["workspace_id"], "workspaces": wss, "version": __version__})
        if p == "/api/workspaces" and method == "POST":
            b = self.json_body()
            wid = auth.create_workspace(app, b.get("name") or "Workspace", sess["user_id"])
            self._switch(app, sess, wid)
            db.audit(app, sess["user_id"], wid, "workspace.create", b.get("name"))
            return self.j({"id": wid})
        if p == "/api/workspaces/switch" and method == "POST":
            wid = int(self.json_body().get("id") or 0)
            if not auth.role(app, sess["user_id"], wid):
                raise HTTPError(403, "You are not a member of that workspace.")
            self._switch(app, sess, wid)
            return self.j({"ok": True})
        if p == "/api/workspaces/members" and method == "POST":
            wid, ws = self.ws_of(app, sess, "owner")
            ws.close()
            b = self.json_body()
            u = app.execute("SELECT id FROM users WHERE email=?", ((b.get("email") or "").strip().lower(),)).fetchone()
            if not u:
                if not b.get("password"):
                    raise HTTPError(404, "No user with that e-mail. Add a temporary password to create the account.")
                uid = auth.create_user(app, b.get("email"), b.get("password"))
            else:
                uid = u[0]
            with app:
                app.execute("INSERT OR IGNORE INTO members(workspace_id,user_id,role) VALUES(?,?,?)", (wid, uid, "member"))
            db.audit(app, sess["user_id"], wid, "member.add", b.get("email"))
            return self.j({"ok": True})
        if p == "/api/password" and method == "POST":
            b = self.json_body()
            u = app.execute("SELECT pw FROM users WHERE id=?", (sess["user_id"],)).fetchone()
            if not auth.check_pw(b.get("old") or "", u["pw"]):
                raise HTTPError(403, "Current password is wrong.")
            err = auth.valid_password(b.get("new"))
            if err:
                raise HTTPError(400, err)
            with app:
                app.execute("UPDATE users SET pw=? WHERE id=?", (auth.hash_pw(b["new"]), sess["user_id"]))
            return self.j({"ok": True})
        # ---------------- wizard
        if p == "/api/wizard":
            pk = packs.public()
            return self.j({"questions": wizard.QUESTIONS, "packs": pk["packs"], "disqualifiers": pk["disqualifiers"],
                           "export_columns": wizard.EXPORT_COLUMNS, "default_export": wizard.DEFAULT_EXPORT, "categories": schema.CATEGORIES})
        if p == "/api/wizard/guess" and method == "POST":
            b = self.json_body()
            return self.j({"pack": packs.guess(" ".join(str(b.get(k) or "") for k in ("sells", "market_text", "company_name")))})
        if p == "/api/wizard/build" and method == "POST":
            cfg = wizard.build_config(self.json_body().get("answers") or {})
            return self.j({"config": cfg, "rules": schema.describe(cfg), "errors": schema.validate(cfg)})
        if p == "/api/wizard/ai-suggest" and method == "POST":
            cl = AI.client(app)
            try:
                return self.j({"signals": AI.suggest_signals(cl, app, self.json_body().get("answers") or {})})
            except AI.AIUnavailable as e:
                raise HTTPError(409, str(e))
        # ---------------- profiles
        if p == "/api/profiles/check" and method == "POST":
            b = self.json_body()
            cfg = schema.normalize(b.get("config") or {})
            return self.j({"config": cfg, "rules": schema.describe(cfg), "errors": schema.validate(cfg)})
        if p == "/api/profiles/test" and method == "POST":
            b = self.json_body()
            errs = schema.validate(b.get("config") or {})
            if errs:
                raise HTTPError(400, errs[0])
            icp = schema.compile_icp(b.get("config"))
            acct = {"name": b.get("name") or "Test company", "domain": b.get("domain") or "example.com"}
            url = b.get("url") or f"https://{acct['domain']}/"
            evs = extract.grade(icp, extract.find(icp, b.get("text") or "", url, acct), acct)
            hits = {e["signal_id"] for e in evs if e["status"] == "VERIFIED"}
            ok, why = icp.gate(hits)
            return self.j({"evidence": [{k: e[k] for k in ("label", "status", "reason", "snippet", "marker", "confidence", "use_cases")} for e in evs[:20]],
                           "gate": ok, "gate_why": why})
        m = re.fullmatch(r"/api/profiles(?:/(\d+))?(?:/(duplicate|versions|export))?", p)
        if m:
            wid, ws = self.ws_of(app, sess)
            try:
                return self.profiles(method, m, ws, wid, app, sess)
            finally:
                ws.close()
        # ---------------- lists and runs
        m = re.fullmatch(r"/api/lists(?:/(\d+))?(?:/(upload|ingest|preview))?", p)
        if m:
            wid, ws = self.ws_of(app, sess)
            try:
                return self.lists(method, m, ws, wid, app, sess)
            finally:
                ws.close()
        m = re.fullmatch(r"/api/runs(?:/(\d+)/(pause|resume|stop))?", p)
        if m:
            wid, ws = self.ws_of(app, sess)
            try:
                if method == "POST" and not m.group(1):
                    b = self.json_body()
                    rid = create_run(ws, int(b.get("list_id") or 0), int(b.get("profile_id") or 0), b.get("mode") or "research",
                                     int(b["threads"]) if b.get("threads") else None, sess["user_id"])
                    db.audit(app, sess["user_id"], wid, "run.create", jdump(b))
                    invalidate(wid)
                    return self.j({"id": rid})
                if method == "POST":
                    n = set_run_status(ws, int(m.group(1)), m.group(2))
                    invalidate(wid)
                    return self.j({"ok": bool(n)})
                return self.j({"runs": [dict(r) for r in ws.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 50")]})
            finally:
                ws.close()
        # ---------------- dashboard data
        if p in ("/api/summary.json", "/api/accounts.json"):
            wid, ws = self.ws_of(app, sess)
            ws.close()
            c = snapshot(wid)
            if p == "/api/summary.json":
                return self.j({**c["summary"], "last_success": now(), "error": None, "workspace": app.execute("SELECT name FROM workspaces WHERE id=?", (wid,)).fetchone()[0]})
            return self.send(c["gz"], "application/json", extra={"Content-Encoding": "gzip", "X-Generated": c["summary"]["generated"]})
        if p == "/api/account":
            wid, ws = self.ws_of(app, sess)
            try:
                k = (q.get("k") or [""])[0]
                aid = int(k.split(":")[1]) if re.fullmatch(r"\d+:\d+", k) else 0
                return self.j(DASH.detail(ws, aid))
            finally:
                ws.close()
        if p in ("/api/account/override", "/api/account/weak") and method == "POST":
            wid, ws = self.ws_of(app, sess)
            try:
                b = self.json_body()
                k = b.get("k") or ""
                if not re.fullmatch(r"\d+:\d+", k):
                    raise HTTPError(400, "bad account key")
                aid = int(k.split(":")[1])
                if p.endswith("weak"):
                    with ws:
                        if b.get("on", True):
                            ws.execute("INSERT OR REPLACE INTO weak(account_id,note,at) VALUES(?,?,?)", (aid, (b.get("note") or "")[:300], now()))
                        else:
                            ws.execute("DELETE FROM weak WHERE account_id=?", (aid,))
                else:
                    pr = b.get("priority") or ""
                    if pr not in ("", "A", "B", "C", "HOLD", "REVIEW", "DQ"):
                        raise HTTPError(400, "priority must be A, B, C, HOLD, REVIEW, DQ or empty (clear)")
                    cur = ws.execute("SELECT priority, override FROM verdicts WHERE account_id=?", (aid,)).fetchone()
                    if not cur:
                        raise HTTPError(409, "This account has no verdict yet; research it first.")
                    ov = {"priority": pr, "note": (b.get("note") or "")[:300], "by": sess["email"], "at": now()} if pr else None
                    with ws:
                        ws.execute("UPDATE verdicts SET override=? WHERE account_id=?", (jdump(ov) if ov else None, aid))
                        ws.execute("INSERT INTO verdict_history(account_id,changed_at,change,old_priority,new_priority,note,user_id) VALUES(?,?,?,?,?,?,?)",
                                   (aid, now(), "manual override" if pr else "override cleared", cur["priority"], pr or cur["priority"],
                                    (b.get("note") or "")[:300] + f" (by {sess['email']})", sess["user_id"]))
                db.audit(app, sess["user_id"], wid, p.rsplit("/", 1)[1], jdump(b))
                invalidate(wid)
                return self.j({"ok": True})
            finally:
                ws.close()
        if p.startswith("/export/") or p == "/api/export/view":
            return self.export(method, p, q, app, sess)
        # ---------------- settings
        if p == "/api/settings":
            if method == "POST":
                if not sess["is_admin"]:
                    raise HTTPError(403, "Only an admin can change providers and limits.")
                b = self.json_body()
                if "search" in b:
                    s = SEARCH.settings(app)
                    s.update({k: b["search"][k] for k in ("provider", "approved", "monthly_cap_usd", "gap_s", "usd_per_1k") if k in b["search"]})
                    if s["provider"] not in ("none", "duckduckgo", "serper", "brave", "tavily", "mock"):
                        raise HTTPError(400, "unknown search provider")
                    db.set_setting(app, "search", jdump(s))
                if "ai" in b:
                    s = AI.settings(app)
                    s.update({k: b["ai"][k] for k in ("provider", "model", "effort", "url", "approved", "daily_call_cap", "monthly_cap_usd", "usd_per_call", "timeout") if k in b["ai"]})
                    if s["provider"] not in ("off", "claude-cli", "codex-cli", "openai", "anthropic", "mock"):
                        raise HTTPError(400, "unknown AI provider")
                    db.set_setting(app, "ai", jdump(s))
                db.audit(app, sess["user_id"], None, "settings", jdump(b))
                with _cache_lock:
                    _cache.clear()
            return self.j({"search": SEARCH.settings(app), "ai": AI.settings(app), "search_status": SEARCH.status(app),
                           "secrets": {n: masked(n) for n in ("search_serper", "search_brave", "search_tavily", "ai_openai", "ai_anthropic")},
                           "threads_default": RUNNER.threads_default, "is_admin": bool(sess["is_admin"])})
        if p == "/api/settings/secret" and method == "POST":
            if not sess["is_admin"]:
                raise HTTPError(403, "Only an admin can save credentials.")
            b = self.json_body()
            if b.get("name") not in ("search_serper", "search_brave", "search_tavily", "ai_openai", "ai_anthropic"):
                raise HTTPError(400, "unknown credential")
            set_secret(b["name"], (b.get("value") or "").strip())
            db.audit(app, sess["user_id"], None, "secret.set", b["name"])
            return self.j({"ok": True, "masked": masked(b["name"])})
        if p == "/api/settings/test-ai" and method == "POST":
            ok, msg, secs = AI.client(app).health(app)
            return self.j({"ok": ok, "message": msg, "seconds": secs})
        if p == "/api/settings/test-search" and method == "POST":
            wid, ws = self.ws_of(app, sess)
            try:
                urls = SEARCH.Searcher(db.app_db, ws, wid).search((self.json_body().get("q") or "example").strip()[:200])
                return self.j({"ok": True, "results": urls[:10]})
            except SEARCH.SearchUnavailable as e:
                return self.j({"ok": False, "message": str(e)})
            finally:
                ws.close()
        if p == "/api/usage":
            rows = [dict(r) for r in app.execute("SELECT provider, kind, substr(at,1,7) AS month, count(*) AS calls, sum(ok) AS ok, round(sum(usd),4) AS usd FROM usage GROUP BY 1,2,3 ORDER BY 3 DESC")]
            return self.j({"usage": rows})
        raise HTTPError(404, "not found")

    def _switch(self, app, sess, wid):
        import hashlib
        with app:
            app.execute("UPDATE sessions SET workspace_id=? WHERE token_hash=?", (wid, hashlib.sha256(self.cookie("icpq").encode()).hexdigest()))
        sess["workspace_id"] = wid

    def profiles(self, method, m, ws, wid, app, sess):
        pid, sub = (int(m.group(1)) if m.group(1) else None), m.group(2)
        if pid is None and method == "GET":
            rows = [dict(r) for r in ws.execute("SELECT id, name, version, updated_at, created_at, archived FROM profiles WHERE archived=0 ORDER BY id")]
            for r in rows:
                r["lists"] = [x[0] for x in ws.execute("SELECT name FROM lists WHERE profile_id=?", (r["id"],))]
            return self.j({"profiles": rows})
        if pid is None and method == "POST":
            b = self.json_body()
            cfg = schema.normalize(b.get("config") or wizard.build_config(b.get("answers") or {}))
            if b.get("name"):
                cfg["name"] = str(b["name"])[:80]
            errs = schema.validate(cfg)
            if errs and not b.get("draft"):
                raise HTTPError(400, "The profile has problems: " + " ".join(errs[:3]))
            with ws:
                cur = ws.execute("INSERT INTO profiles(name,config,answers,version,created_at,updated_at) VALUES(?,?,?,1,?,?)",
                                 (cfg["name"], jdump(cfg), jdump(b.get("answers") or {}), now(), now()))
                ws.execute("INSERT INTO profile_versions(profile_id,version,config,saved_at,note) VALUES(?,?,?,?,?)", (cur.lastrowid, 1, jdump(cfg), now(), "created"))
            db.audit(app, sess["user_id"], wid, "profile.create", cfg["name"])
            invalidate(wid)
            return self.j({"id": cur.lastrowid, "errors": errs})
        r = ws.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
        if not r:
            raise HTTPError(404, "Profile not found.")
        if sub == "versions":
            return self.j({"versions": [dict(x) for x in ws.execute("SELECT version, saved_at, note FROM profile_versions WHERE profile_id=? ORDER BY version DESC", (pid,))]})
        if sub == "export":
            return self.send(json.dumps({"icp_qualifier_profile": 1, "config": jload(r["config"])}, indent=1), "application/json",
                             extra={"Content-Disposition": f'attachment; filename="{re.sub(r"[^A-Za-z0-9_-]+", "_", r["name"])}.icp.json"'})
        if sub == "duplicate" and method == "POST":
            cfg = jload(r["config"])
            cfg["name"] = (cfg.get("name") or "Profile") + " (copy)"
            with ws:
                cur = ws.execute("INSERT INTO profiles(name,config,answers,version,created_at,updated_at) VALUES(?,?,?,1,?,?)",
                                 (cfg["name"], jdump(cfg), r["answers"], now(), now()))
            return self.j({"id": cur.lastrowid})
        if method == "GET":
            cfg = jload(r["config"])
            return self.j({"id": pid, "name": r["name"], "version": r["version"], "config": cfg, "answers": jload(r["answers"], {}),
                           "rules": schema.describe(cfg), "errors": schema.validate(cfg)})
        if method == "PUT":
            b = self.json_body()
            cfg = schema.normalize(b.get("config") or {})
            errs = schema.validate(cfg)
            if errs:
                raise HTTPError(400, "Not saved: " + " ".join(errs[:3]))
            v = r["version"] + 1
            with ws:
                ws.execute("UPDATE profiles SET name=?, config=?, version=?, updated_at=? WHERE id=?", (cfg["name"], jdump(cfg), v, now(), pid))
                ws.execute("INSERT INTO profile_versions(profile_id,version,config,saved_at,note) VALUES(?,?,?,?,?)", (pid, v, jdump(cfg), now(), (b.get("note") or "edited")[:200]))
            db.audit(app, sess["user_id"], wid, "profile.update", f"{pid} v{v}")
            invalidate(wid)
            return self.j({"id": pid, "version": v})
        if method == "DELETE":
            with ws:
                ws.execute("UPDATE profiles SET archived=1 WHERE id=?", (pid,))
            invalidate(wid)
            return self.j({"ok": True})
        raise HTTPError(405, "method not allowed")

    def lists(self, method, m, ws, wid, app, sess):
        lid, sub = (int(m.group(1)) if m.group(1) else None), m.group(2)
        if lid is None and sub is None and method == "GET":
            out = []
            for r in ws.execute("SELECT id, name, filename, uploaded_at, rows_in_file, profile_id, status, ingest, mapping, header FROM lists ORDER BY id"):
                d = dict(r)
                d["ingest"], d["mapping"], d["header"] = jload(d["ingest"], {}), jload(d["mapping"], {}), jload(d["header"], [])
                d["counts"] = dict(ws.execute("""SELECT r.state, count(*) FROM research r JOIN accounts a ON a.id=r.account_id WHERE a.list_id=? GROUP BY 1""", (r["id"],)).fetchall())
                run = ws.execute("SELECT * FROM runs WHERE list_id=? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
                d["run"] = dict(run) if run else None
                out.append(d)
            return self.j({"lists": out})
        if sub == "upload" or (lid is None and method == "POST"):
            fn = os.path.basename(self.headers.get("X-Filename") or "upload.csv")[:120]
            data = self.body(MAX_UPLOAD)
            if not data:
                raise HTTPError(400, "The file is empty.")
            text = to_csv_text(data, fn)
            header, body = ingest.read_table(text)
            name = (self.headers.get("X-List-Name") or "").strip()[:80] or re.sub(r"\.(csv|xlsx|xlsm|txt)$", "", fn, flags=re.IGNORECASE)
            with ws:
                cur = ws.execute("INSERT INTO lists(name,filename,uploaded_at,rows_in_file,header,raw,status) VALUES(?,?,?,?,?,?,?)",
                                 (name, fn, now(), len(body), jdump(header), text, "uploaded"))
            db.audit(app, sess["user_id"], wid, "list.upload", f"{fn} {len(body)} rows")
            return self.j({"id": cur.lastrowid, "name": name, "header": header, "rows": len(body), "sample": [r for _, r in body[:5]],
                           "mapping": ingest.suggest_mapping(header)})
        r = ws.execute("SELECT * FROM lists WHERE id=?", (lid,)).fetchone()
        if not r:
            raise HTTPError(404, "List not found.")
        if sub == "ingest" and method == "POST":
            b = self.json_body()
            mapping = {k: v for k, v in (b.get("mapping") or {}).items() if k in ingest.SYNONYMS and v}
            header, body = ingest.read_table(r["raw"])
            stats = ingest.ingest(ws, lid, header, body, mapping)
            if b.get("profile_id"):
                with ws:
                    ws.execute("UPDATE lists SET profile_id=? WHERE id=?", (int(b["profile_id"]), lid))
            if b.get("name"):
                with ws:
                    ws.execute("UPDATE lists SET name=? WHERE id=?", (str(b["name"])[:80], lid))
            invalidate(wid)
            return self.j({"ok": True, "stats": stats})
        if sub == "preview":
            header, body = ingest.read_table(r["raw"])
            return self.j({"header": header, "rows": len(body), "sample": [x for _, x in body[:5]], "mapping": jload(r["mapping"], {}) or ingest.suggest_mapping(header)})
        if method == "DELETE":
            with ws:
                for t in ("evidence", "verdicts", "research", "verdict_history", "website_discovery", "weak"):
                    ws.execute(f"DELETE FROM {t} WHERE account_id IN (SELECT id FROM accounts WHERE list_id=?)", (lid,))
                ws.execute("DELETE FROM accounts WHERE list_id=?", (lid,))
                ws.execute("UPDATE runs SET status='stopped' WHERE list_id=? AND status IN ('queued','running','paused')", (lid,))
                ws.execute("DELETE FROM lists WHERE id=?", (lid,))
            db.audit(app, sess["user_id"], wid, "list.delete", r["name"])
            invalidate(wid)
            return self.j({"ok": True})
        raise HTTPError(405, "method not allowed")

    def export(self, method, p, q, app, sess):
        wid, ws = self.ws_of(app, sess)
        try:
            cfgs = DASH.profile_cfgs(ws)
            lists = [dict(x) for x in ws.execute("SELECT id, name FROM lists")]
        finally:
            ws.close()
        c = snapshot(wid, max_age=2)
        pid = c["summary"].get("default_profile")
        cfg = cfgs.get(pid) or schema.normalize({})
        cols, labels = EXP.columns(cfg), cfg["labels"]
        fm = DASH.files(c["accts"], lists)
        if p == "/api/export/view" and method == "POST":
            b = self.json_body()
            keys = set(b.get("keys") or [])
            rows = [a for a in c["accts"] if a["k"] in keys]
            order = {k: i for i, k in enumerate(b.get("keys") or [])}
            rows.sort(key=lambda a: order.get(a["k"], 0))
            if b.get("format") == "xlsx":
                return self.send(EXP.to_xlsx(rows, cols, labels), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 extra={"Content-Disposition": 'attachment; filename="accounts.xlsx"'})
            return self.send(EXP.to_csv(rows, cols, labels), "text/csv; charset=utf-8", extra={"Content-Disposition": 'attachment; filename="accounts.csv"'})
        name = p.removeprefix("/export/")
        if name == "MANIFEST.json":
            return self.send(EXP.manifest(fm, cols, labels), "application/json", extra={"Content-Disposition": 'attachment; filename="MANIFEST.json"'})
        mm = re.fullmatch(r"([A-Z0-9_]+)\.(csv|xlsx)", name)
        if not mm or mm.group(1) not in fm:
            raise HTTPError(404, "No such export.")
        rows = fm[mm.group(1)]
        if mm.group(2) == "xlsx":
            return self.send(EXP.to_xlsx(rows, cols, labels, mm.group(1)[:31]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             extra={"Content-Disposition": f'attachment; filename="{name}"'})
        return self.send(EXP.to_csv(rows, cols, labels), "text/csv; charset=utf-8", extra={"Content-Disposition": f'attachment; filename="{name}"'})


def serve(host=None, port=None, run_workers=True):
    host = host or os.environ.get("ICPQ_HOST", "127.0.0.1")
    port = int(port or os.environ.get("ICPQ_PORT", "8890"))
    app = db.app_db()
    try:
        if os.environ.get("ICPQ_ADMIN_EMAIL") and os.environ.get("ICPQ_ADMIN_PASSWORD") and auth.needs_setup(app):
            uid = auth.create_user(app, os.environ["ICPQ_ADMIN_EMAIL"], os.environ["ICPQ_ADMIN_PASSWORD"], admin=True)
            auth.create_workspace(app, os.environ.get("ICPQ_WORKSPACE", "My workspace"), uid)
            log.info("admin %s created from the environment", os.environ["ICPQ_ADMIN_EMAIL"])
        if auth.needs_setup(app):
            log.warning("FIRST RUN: open http://%s:%s/setup and enter the setup code %s (also in %s)", host, port, auth.setup_code(), db.data_dir() / "SETUP_CODE")
    finally:
        app.close()
    global NO_AUTH
    if NO_AUTH and host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("ICPQ_NO_AUTH ignored: no-login mode only works on localhost (ICPQ_HOST=%s)", host)
        NO_AUTH = False
    if run_workers and os.environ.get("ICPQ_RUN_WORKERS", "1") == "1":
        RUNNER.start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    log.info("ICP Qualifier %s listening on http://%s:%s/", __version__, host, port)
    try:
        httpd.serve_forever()
    finally:
        RUNNER.stop_all.set()
