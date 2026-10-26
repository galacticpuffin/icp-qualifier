"""SQLite storage with versioned migrations.

Two kinds of database keep customer data isolated:
  app.db                       users, sessions, workspaces, memberships, provider settings, usage ledger, audit log
  workspaces/<id>/ws.db        one workspace's ICP profiles, lists, accounts, research, evidence, page cache, runs

A workspace database is never opened by a request that isn't a member of that workspace (server.py checks), and
nothing is ever shared between workspace databases."""
import os
import sqlite3
import threading
from pathlib import Path

from .util import now

APP_MIGRATIONS = [
    """
    CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, pw TEXT NOT NULL, is_admin INTEGER DEFAULT 0,
                       created_at TEXT, last_login TEXT);
    CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, created_at TEXT, expires_at REAL,
                          workspace_id INTEGER);
    CREATE TABLE workspaces(id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT, created_by INTEGER);
    CREATE TABLE members(workspace_id INTEGER, user_id INTEGER, role TEXT DEFAULT 'member', PRIMARY KEY(workspace_id, user_id));
    CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE usage(id INTEGER PRIMARY KEY, at TEXT, provider TEXT, kind TEXT, workspace_id INTEGER, units INTEGER, usd REAL, ok INTEGER, note TEXT);
    CREATE TABLE audit_log(id INTEGER PRIMARY KEY, at TEXT, user_id INTEGER, workspace_id INTEGER, action TEXT, detail TEXT);
    CREATE TABLE login_attempts(key TEXT PRIMARY KEY, n INTEGER, first_at REAL);
    CREATE TABLE search_engines(engine TEXT PRIMARY KEY, last_at REAL, paused_until REAL, ok INTEGER DEFAULT 0, fail INTEGER DEFAULT 0);
    """,
]

WS_MIGRATIONS = [
    """
    CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL, answers TEXT, version INTEGER DEFAULT 1,
                          created_at TEXT, updated_at TEXT, archived INTEGER DEFAULT 0);
    CREATE TABLE profile_versions(id INTEGER PRIMARY KEY, profile_id INTEGER, version INTEGER, config TEXT, saved_at TEXT, note TEXT);
    CREATE TABLE lists(id INTEGER PRIMARY KEY, name TEXT NOT NULL, filename TEXT, uploaded_at TEXT, rows_in_file INTEGER,
                       header TEXT, mapping TEXT, profile_id INTEGER, ingest TEXT, status TEXT DEFAULT 'uploaded', raw TEXT);
    CREATE TABLE accounts(id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL, key TEXT, name TEXT, domain TEXT, industry TEXT,
                          employees REAL, revenue REAL, location TEXT, extra TEXT, members TEXT, is_primary INTEGER DEFAULT 1,
                          company_id INTEGER, company_order INTEGER, merge_notes TEXT, flags TEXT, relation TEXT, parent_id INTEGER,
                          website_source TEXT);
    CREATE INDEX acc_list ON accounts(list_id);
    CREATE INDEX acc_domain ON accounts(domain);
    CREATE TABLE research(account_id INTEGER PRIMARY KEY, state TEXT DEFAULT 'pending', lease_until REAL, attempts INTEGER DEFAULT 0,
                          pages_checked INTEGER, searches_used INTEGER, search_state TEXT, crawl_ok INTEGER, log TEXT, error TEXT,
                          researched_at TEXT, profile_id INTEGER, profile_version INTEGER);
    CREATE INDEX res_state ON research(state);
    CREATE TABLE verdicts(account_id INTEGER PRIMARY KEY, profile_id INTEGER, profile_version INTEGER, priority TEXT, status TEXT,
                          core TEXT, use_case TEXT, evidence TEXT, url TEXT, confidence TEXT, scale TEXT, scale_level TEXT,
                          segment TEXT, buyer TEXT, qual_reason TEXT, review_reason TEXT, missing TEXT, signals TEXT, fit_score INTEGER,
                          score_parts TEXT, tech TEXT, tech_mentions TEXT, competitors TEXT, triggers TEXT, channel TEXT,
                          channel_score INTEGER, angle TEXT, persona TEXT, target_tech TEXT, audit TEXT, ai TEXT, decided_at TEXT,
                          override TEXT);
    CREATE TABLE evidence(id INTEGER PRIMARY KEY, account_id INTEGER, signal_id TEXT, label TEXT, kind TEXT, status TEXT,
                          confidence TEXT, url TEXT, snippet TEXT, use_cases TEXT, marker INTEGER, mentions_org INTEGER,
                          found_at TEXT, reason TEXT);
    CREATE INDEX ev_acc ON evidence(account_id);
    CREATE TABLE verdict_history(id INTEGER PRIMARY KEY, account_id INTEGER, changed_at TEXT, change TEXT, old_priority TEXT,
                                 new_priority TEXT, note TEXT, user_id INTEGER);
    CREATE TABLE website_discovery(account_id INTEGER PRIMARY KEY, found_at TEXT, domain TEXT, verified TEXT, query TEXT);
    CREATE TABLE pages(url TEXT PRIMARY KEY, final_url TEXT, status INTEGER, fetched_at TEXT, html TEXT, text TEXT, title TEXT, error TEXT);
    CREATE TABLE searches(q TEXT, provider TEXT, fetched_at TEXT, urls TEXT, error TEXT, PRIMARY KEY(q, provider));
    CREATE TABLE runs(id INTEGER PRIMARY KEY, list_id INTEGER, profile_id INTEGER, mode TEXT, status TEXT, threads INTEGER,
                      created_at TEXT, started_at TEXT, finished_at TEXT, created_by INTEGER, note TEXT, error TEXT,
                      ai_calls INTEGER DEFAULT 0, search_calls INTEGER DEFAULT 0);
    CREATE TABLE weak(account_id INTEGER PRIMARY KEY, note TEXT, at TEXT);
    """,
]

_init_lock = threading.Lock()


def data_dir():
    d = Path(os.environ.get("ICPQ_DATA", Path.cwd() / "data")).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connect(path):
    c = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def migrate(c, migrations):
    c.execute("CREATE TABLE IF NOT EXISTS schema_version(v INTEGER)")
    row = c.execute("SELECT v FROM schema_version").fetchone()
    v = row[0] if row else 0
    if not row:
        c.execute("INSERT INTO schema_version VALUES(0)")
    for i, sql in enumerate(migrations[v:], start=v + 1):
        with c:
            c.executescript("BEGIN;" + sql + f";UPDATE schema_version SET v={i};COMMIT;")
    return len(migrations)


def app_db():
    with _init_lock:
        c = _connect(data_dir() / "app.db")
        migrate(c, APP_MIGRATIONS)
    try:
        os.chmod(data_dir() / "app.db", 0o600)
    except OSError:
        pass
    return c


def ws_path(ws_id):
    ws_id = int(ws_id)        # never a path fragment from a request
    d = data_dir() / "workspaces" / str(ws_id)
    d.mkdir(parents=True, exist_ok=True)
    return d / "ws.db"


def ws_db(ws_id):
    p = ws_path(ws_id)
    with _init_lock:
        c = _connect(p)
        migrate(c, WS_MIGRATIONS)
    return c


def audit(app, user_id, ws_id, action, detail=""):
    with app:
        app.execute("INSERT INTO audit_log(at,user_id,workspace_id,action,detail) VALUES(?,?,?,?,?)",
                    (now(), user_id, ws_id, action, str(detail)[:2000]))


def get_setting(app, k, default=None):
    r = app.execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def set_setting(app, k, v):
    with app:
        app.execute("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
