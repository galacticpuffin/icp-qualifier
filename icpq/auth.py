"""Users, sessions and the first-run setup code.

* Passwords: PBKDF2-HMAC-SHA256 with a per-user salt.
* Sessions: a random token in an HttpOnly, SameSite=Strict cookie; only its SHA-256 is stored. 14-day expiry.
* CSRF: every state-changing request must send the session's CSRF token in the X-CSRF header.
* Login throttling: 8 failed attempts per e-mail / address in 15 minutes locks that key for the rest of the window.
* First run: the first admin needs the one-time setup code written to <data>/SETUP_CODE (owner-only) and the server log,
  unless ICPQ_ADMIN_EMAIL / ICPQ_ADMIN_PASSWORD pre-create the admin."""
import hashlib
import hmac
import os
import secrets
import time

from .db import data_dir
from .util import now

ITER = int(os.environ.get("ICPQ_PBKDF2_ITER", "240000"))
SESSION_S = 14 * 86400


def hash_pw(pw, salt=None, it=ITER):
    salt = salt or secrets.token_hex(16)
    d = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), it).hex()
    return f"pbkdf2${it}${salt}${d}"


def check_pw(pw, stored):
    try:
        _, it, salt, d = stored.split("$")
        return hmac.compare_digest(hash_pw(pw, salt, int(it)).split("$")[3], d)
    except (ValueError, AttributeError):
        return False


def valid_password(pw):
    if len(pw or "") < 10:
        return "Use at least 10 characters."
    return None


def setup_code():
    p = data_dir() / "SETUP_CODE"
    if not p.exists():
        code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(code)
    return p.read_text().strip()


def needs_setup(app):
    return app.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def create_user(app, email, pw, name="", admin=False):
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 200:
        raise ValueError("Enter a valid e-mail address.")
    err = valid_password(pw)
    if err:
        raise ValueError(err)
    if app.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ValueError("That e-mail already has an account.")
    with app:
        cur = app.execute("INSERT INTO users(email,name,pw,is_admin,created_at) VALUES(?,?,?,?,?)", (email, name or email.split("@")[0], hash_pw(pw), int(admin), now()))
    return cur.lastrowid


def create_workspace(app, name, user_id):
    with app:
        cur = app.execute("INSERT INTO workspaces(name,created_at,created_by) VALUES(?,?,?)", (name.strip()[:80] or "Workspace", now(), user_id))
        app.execute("INSERT INTO members(workspace_id,user_id,role) VALUES(?,?,?)", (cur.lastrowid, user_id, "owner"))
    return cur.lastrowid


def throttled(app, key):
    r = app.execute("SELECT n, first_at FROM login_attempts WHERE key=?", (key,)).fetchone()
    return bool(r and r["n"] >= 8 and time.time() - r["first_at"] < 900)


def note_fail(app, key):
    with app:
        r = app.execute("SELECT n, first_at FROM login_attempts WHERE key=?", (key,)).fetchone()
        if not r or time.time() - r["first_at"] >= 900:
            app.execute("INSERT OR REPLACE INTO login_attempts(key,n,first_at) VALUES(?,1,?)", (key, time.time()))
        else:
            app.execute("UPDATE login_attempts SET n=n+1 WHERE key=?", (key,))


def login(app, email, pw, ip=""):
    email = (email or "").strip().lower()
    keys = [f"e:{email}", f"i:{ip}"]
    if any(throttled(app, k) for k in keys):
        raise PermissionError("Too many attempts. Wait 15 minutes and try again.")
    u = app.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u or not check_pw(pw or "", u["pw"]):
        for k in keys:
            note_fail(app, k)
        raise PermissionError("E-mail or password is wrong.")
    with app:
        app.execute("DELETE FROM login_attempts WHERE key IN (?,?)", keys)
        app.execute("UPDATE users SET last_login=? WHERE id=?", (now(), u["id"]))
    return new_session(app, u["id"])


def new_session(app, user_id):
    tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    ws = app.execute("SELECT workspace_id FROM members WHERE user_id=? ORDER BY workspace_id LIMIT 1", (user_id,)).fetchone()
    with app:
        app.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
        app.execute("INSERT INTO sessions(token_hash,user_id,csrf,created_at,expires_at,workspace_id) VALUES(?,?,?,?,?,?)",
                    (hashlib.sha256(tok.encode()).hexdigest(), user_id, csrf, now(), time.time() + SESSION_S, ws[0] if ws else None))
    return tok


def session(app, tok):
    if not tok:
        return None
    r = app.execute("""SELECT s.*, u.email, u.name, u.is_admin FROM sessions s JOIN users u ON u.id=s.user_id
                       WHERE s.token_hash=? AND s.expires_at>?""", (hashlib.sha256(tok.encode()).hexdigest(), time.time())).fetchone()
    return dict(r) if r else None


def logout(app, tok):
    with app:
        app.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256((tok or "").encode()).hexdigest(),))


def role(app, user_id, ws_id):
    r = app.execute("SELECT role FROM members WHERE user_id=? AND workspace_id=?", (user_id, ws_id)).fetchone()
    return r[0] if r else None
