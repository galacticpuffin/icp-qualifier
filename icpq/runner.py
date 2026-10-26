"""Batch processing: reliable, resumable, checkpointed per account.

A run = (list, profile, mode). Modes:
  research   research every not-yet-researched account (network: website crawl + optional searches + optional AI)
  retry      re-research accounts left RETRY (searches blocked / site unreadable) or failed
  requalify  re-judge every researched account with the profile as it is now, from the page cache only (no network);
             accounts that would need new pages or searches are marked RETRY with that reason
Each account is claimed with a lease (state=working, lease_until); a crash or restart releases expired leases, so a run
resumes where it stopped. Every finished account is committed immediately (its checkpoint). Failures are retried up to
MAX_ATTEMPTS times, then the account is marked failed (shown as RETRY with the error, never as complete)."""
import logging
import os
import threading
import time
import traceback

from . import db
from .engine import ai as AI
from .engine import extract
from .engine.audit import audit
from .engine.fetch import Fetcher
from .engine.qualify import decide
from .engine.research import collect, discover, identity_ok
from .engine.search import Searcher, SearchUnavailable
from .icp.schema import compile_icp
from .util import jdump, jload, now

log = logging.getLogger("icpq.runner")
MAX_ATTEMPTS = 3
LEASE_S = 900


class CacheOnlyFetcher(Fetcher):
    def get(self, url, raw=False):
        r = self.ws.execute("SELECT * FROM pages WHERE url=?", (url,)).fetchone()
        if r:
            return dict(r)
        return {"url": url, "final_url": url, "status": 0, "html": "", "text": "", "title": "", "error": "not cached (requalify reads cached pages only)"}

    def robots_ok(self, url):
        return True


class CacheOnlySearcher:
    def __init__(self, ws):
        self.ws, self.used = ws, 0

    def enabled(self):
        return False

    def search(self, q):
        r = self.ws.execute("SELECT urls FROM searches WHERE q=? AND (error IS NULL OR error='') ORDER BY fetched_at DESC LIMIT 1", (q,)).fetchone()
        if r:
            return [u for u in (r["urls"] or "").split("\n") if u]
        raise SearchUnavailable("new search needed: start a research or retry run")


def load_profile(ws, pid):
    r = ws.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
    if not r:
        raise ValueError("profile not found")
    return r["version"], compile_icp(jload(r["config"], {}))


def process_account(ws, app_factory, wid, icp, pver, pid, acct, mode, ai_client=None, run=None):
    """Research (or requalify) one account and store its verdict. Returns the verdict dict."""
    acct = dict(acct)
    cache_only = mode == "requalify"
    fetcher = CacheOnlyFetcher(ws) if cache_only else Fetcher(ws, delay=float(icp.cfg["research"].get("politeness_s") or 0.6))
    searcher = CacheOnlySearcher(ws) if cache_only else Searcher(app_factory, ws, wid)
    if acct.get("parent_id"):
        p = ws.execute("SELECT name FROM accounts WHERE id=?", (acct["parent_id"],)).fetchone()
        acct["parent_name"] = p["name"] if p else ""
    note = ""
    if not acct.get("domain"):
        if icp.cfg["research"]["discover_websites"] and not cache_only and searcher.enabled():
            dom, note, q = discover(acct, fetcher, searcher)
            with ws:
                ws.execute("INSERT OR REPLACE INTO website_discovery(account_id,found_at,domain,verified,query) VALUES(?,?,?,?,?)",
                           (acct["id"], now(), dom, "VERIFIED (home page names the company)" if dom else "NOT FOUND", q))
                if dom:
                    ws.execute("UPDATE accounts SET domain=?, website_source='discovered' WHERE id=?", (dom, acct["id"]))
            acct["domain"] = dom
        else:
            note = "no website in the list" + ("" if cache_only else "; website discovery needs a search provider (Settings)")
    if not acct.get("domain"):
        with ws:
            ws.execute("""UPDATE research SET state='done', lease_until=NULL, pages_checked=0, searches_used=?, search_state=?, crawl_ok=0,
                          log=?, error=NULL, researched_at=?, profile_id=?, profile_version=? WHERE account_id=?""",
                       (searcher.used, "n/a", jdump({"note": note}), now(), pid, pver, acct["id"]))
            ws.execute("DELETE FROM verdicts WHERE account_id=?", (acct["id"],))
        return None
    res = collect(icp, acct, fetcher, searcher, cache_only=cache_only)
    if acct.get("relation") == "SINGLE_MISMATCH" and res["pages"]:
        ok = identity_ok(acct["name"], res["pages"])
        acct["relation"] = "" if ok in (True, None) else "SPLIT_OUT"
    own = [(p.get("final_url") or p["url"], p.get("text") or "") for p in res["pages"]]
    v = decide(icp, acct, res["evidence"], res["stack"], res["crawl_ok"], own)
    if v["priority"] in ("A", "B", "C", "HOLD") and icp.cfg["evidence"]["audit"]:
        v["audit"] = audit(icp, ws, acct, v, None if cache_only else fetcher)
    prev = ws.execute("SELECT priority, ai, override FROM verdicts WHERE account_id=?", (acct["id"],)).fetchone()
    aiv = jload(prev["ai"]) if prev and prev["ai"] else None
    if ai_client is not None and v["priority"] == "REVIEW" and icp.cfg["ai"]["use"] == "shadow" and not aiv and res["pages"]:
        app = app_factory()
        try:
            aiv = AI.shadow_review(ai_client, app, icp, acct, res["pages"], wid) or {"none": True, "at": now(), "model": ai_client.label}
            if run is not None:
                with ws:
                    ws.execute("UPDATE runs SET ai_calls=ai_calls+1 WHERE id=?", (run,))
        except AI.AIUnavailable as e:
            aiv = None
            note = f"AI review skipped: {e}"
        finally:
            app.close()
    evrows = [e for e in res["evidence"]][:40]
    with ws:
        ws.execute("DELETE FROM evidence WHERE account_id=?", (acct["id"],))
        ws.executemany("""INSERT INTO evidence(account_id,signal_id,label,kind,status,confidence,url,snippet,use_cases,marker,mentions_org,found_at,reason)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       [(acct["id"], e["signal_id"], e["label"], e["kind"], e["status"], e["confidence"], e["url"], e["snippet"][:900],
                         jdump(e["use_cases"]), int(e["marker"]), int(e["mentions_org"]), now(), e.get("reason", "")) for e in evrows])
        fields = ("priority", "status", "core", "use_case", "evidence", "url", "confidence", "scale", "scale_level", "segment", "buyer", "qual_reason",
                  "review_reason", "fit_score", "channel", "channel_score", "angle", "persona", "target_tech")
        vals = [v.get(k) for k in fields]
        js = {"missing": v["missing"], "signals": v["signals"], "score_parts": v["score_parts"], "tech": v["tech"], "tech_mentions": v["tech_mentions"],
              "competitors": v["competitors"], "triggers": v["triggers"], "audit": v.get("audit"), "ai": aiv}
        ws.execute(f"""INSERT INTO verdicts(account_id,profile_id,profile_version,{",".join(fields)},{",".join(js)},decided_at) VALUES(?,?,?,{",".join("?" * len(fields))},{",".join("?" * len(js))},?)
                       ON CONFLICT(account_id) DO UPDATE SET profile_id=excluded.profile_id, profile_version=excluded.profile_version,
                       {",".join(f"{k}=excluded.{k}" for k in list(fields) + list(js))}, decided_at=excluded.decided_at""",
                   [acct["id"], pid, pver] + vals + [jdump(x) if x is not None else None for x in js.values()] + [now()])
        if prev is None or prev["priority"] != v["priority"]:
            ws.execute("INSERT INTO verdict_history(account_id,changed_at,change,old_priority,new_priority,note) VALUES(?,?,?,?,?,?)",
                       (acct["id"], now(), mode, prev["priority"] if prev else None, v["priority"], f"profile v{pver}: {v['status'][:200]}"))
        search_state = res["search_state"]
        if cache_only and search_state == "pending":
            note = "new searches needed for this profile: start a research or retry run"
        ws.execute("""UPDATE research SET state='done', lease_until=NULL, pages_checked=?, searches_used=?, search_state=?, crawl_ok=?, log=?,
                      error=?, researched_at=?, profile_id=?, profile_version=? WHERE account_id=?""",
                   (len(res["pages"]), searcher.used, search_state, int(res["crawl_ok"]), jdump({**res["log"], "note": note})[:20000],
                    None, now(), pid, pver, acct["id"]))
    return v


class Runner:
    """In-process scheduler: one thread per active run, each with a small pool of worker threads."""

    def __init__(self, threads_default=None):
        self.threads_default = int(threads_default or os.environ.get("ICPQ_THREADS", "4"))
        self.active = {}            # (wid, run_id) -> thread
        self.stop_all = threading.Event()
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, name="icpq-runner", daemon=True).start()

    def _loop(self):
        while not self.stop_all.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("runner tick failed")
            self.stop_all.wait(2)

    def tick(self):
        app = db.app_db()
        try:
            wids = [r[0] for r in app.execute("SELECT id FROM workspaces")]
        finally:
            app.close()
        for wid in wids:
            ws = db.ws_db(wid)
            try:
                ws.execute("UPDATE research SET state='pending', lease_until=NULL WHERE state='working' AND lease_until<?", (time.time(),))
                ws.commit()
                for r in ws.execute("SELECT id FROM runs WHERE status IN ('queued','running') ORDER BY id"):
                    key = (wid, r["id"])
                    with self.lock:
                        if key not in self.active or not self.active[key].is_alive():
                            t = threading.Thread(target=self.run, args=(wid, r["id"]), name=f"run-{wid}-{r['id']}", daemon=True)
                            self.active[key] = t
                            t.start()
                    break           # one run at a time per workspace (others wait in the queue)
            finally:
                ws.close()

    def run(self, wid, run_id):
        ws = db.ws_db(wid)
        try:
            run = ws.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            pver, icp = load_profile(ws, run["profile_id"])
            with ws:
                ws.execute("UPDATE runs SET status='running', started_at=COALESCE(started_at,?) WHERE id=?", (now(), run_id))
                if run["mode"] == "requalify":
                    ws.execute("""UPDATE research SET state='requeue' WHERE state='done' AND account_id IN
                                  (SELECT id FROM accounts WHERE list_id=? AND is_primary=1)""", (run["list_id"],))
                elif run["mode"] == "retry":
                    ws.execute("""UPDATE research SET state='pending', attempts=0 WHERE account_id IN (SELECT id FROM accounts WHERE list_id=? AND is_primary=1)
                                  AND (state='failed' OR (state='done' AND (crawl_ok=0 OR search_state='pending')))""", (run["list_id"],))
            app = db.app_db()
            try:
                aic = AI.client(app) if icp.cfg["ai"]["use"] == "shadow" and AI.settings(app)["provider"] != "off" else None
            finally:
                app.close()
            n = max(1, min(32, int(run["threads"] or self.threads_default)))
            workers = [threading.Thread(target=self._work, args=(wid, run_id, run["list_id"], run["profile_id"], pver, icp, run["mode"], aic), daemon=True)
                       for _ in range(n)]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            st = ws.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()["status"]
            if st == "running":
                with ws:
                    ws.execute("UPDATE runs SET status='done', finished_at=? WHERE id=?", (now(), run_id))
        except Exception as e:
            log.exception("run %s/%s failed", wid, run_id)
            with ws:
                ws.execute("UPDATE runs SET status='error', error=?, finished_at=? WHERE id=?", (f"{type(e).__name__}: {e}"[:500], now(), run_id))
        finally:
            ws.close()

    def _claim(self, ws, list_id, mode):
        src = "requeue" if mode == "requalify" else "pending"
        with self.lock:
            with ws:
                r = ws.execute(f"""UPDATE research SET state='working', lease_until=?, attempts=attempts+1 WHERE account_id=(
                                     SELECT r.account_id FROM research r JOIN accounts a ON a.id=r.account_id
                                     WHERE r.state='{src}' AND a.list_id=? AND a.is_primary=1 ORDER BY a.company_order LIMIT 1)
                                   RETURNING account_id, attempts""", (time.time() + LEASE_S, list_id)).fetchone()
        return (r[0], r[1]) if r else (None, 0)

    def _work(self, wid, run_id, list_id, pid, pver, icp, mode, aic):
        ws = db.ws_db(wid)
        try:
            while not self.stop_all.is_set():
                st = ws.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()["status"]
                if st != "running":
                    return
                aid, attempts = self._claim(ws, list_id, mode)
                if aid is None:
                    return
                acct = ws.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()
                try:
                    process_account(ws, db.app_db, wid, icp, pver, pid, acct, mode, aic, run_id)
                except Exception as e:
                    log.warning("account %s failed: %s", aid, e)
                    with ws:
                        ws.execute("UPDATE research SET state=?, lease_until=NULL, error=? WHERE account_id=?",
                                   ("failed" if attempts >= MAX_ATTEMPTS else ("requeue" if mode == "requalify" else "pending"),
                                    f"{type(e).__name__}: {e}"[:300] + "\n" + traceback.format_exc()[-600:], aid))
        finally:
            ws.close()


def create_run(ws, list_id, profile_id, mode, threads=None, user_id=None):
    if mode not in ("research", "retry", "requalify"):
        raise ValueError("mode must be research, retry or requalify")
    if not ws.execute("SELECT 1 FROM lists WHERE id=?", (list_id,)).fetchone():
        raise ValueError("list not found")
    r = ws.execute("SELECT config FROM profiles WHERE id=?", (profile_id,)).fetchone()
    if not r:
        raise ValueError("profile not found")
    from .icp.schema import validate
    errs = validate(jload(r["config"], {}))
    if errs:
        raise ValueError("The profile has problems: " + " ".join(errs[:3]))
    with ws:
        ws.execute("UPDATE lists SET profile_id=? WHERE id=?", (profile_id, list_id))
        cur = ws.execute("INSERT INTO runs(list_id,profile_id,mode,status,threads,created_at,created_by) VALUES(?,?,?,?,?,?,?)",
                         (list_id, profile_id, mode, "queued", threads, now(), user_id))
    return cur.lastrowid


def set_run_status(ws, run_id, action):
    to = {"pause": ("running", "queued"), "resume": ("paused",), "stop": ("running", "queued", "paused")}[action]
    new = {"pause": "paused", "resume": "queued", "stop": "stopped"}[action]
    with ws:
        n = ws.execute(f"UPDATE runs SET status=? WHERE id=? AND status IN ({','.join('?' * len(to))})", (new, run_id, *to)).rowcount
        if action == "stop":
            ws.execute("UPDATE runs SET finished_at=? WHERE id=?", (now(), run_id))
            ws.execute("UPDATE research SET state='done' WHERE state='requeue'")      # an interrupted requalify keeps the old verdicts
    return n


__all__ = ["Runner", "create_run", "extract", "process_account", "set_run_status"]
