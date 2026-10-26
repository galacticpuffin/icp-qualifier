"""python -m icpq <command>

  serve [--host H] [--port P]   web app + background workers (default 127.0.0.1:8890)
  worker                        background workers only (when the web app runs with ICPQ_RUN_WORKERS=0)
  migrate                       create / upgrade every database, then exit
  backup [--out DIR]            consistent backup of all data
  restore FILE --yes            restore a backup (keeps the current data next to it)
  validate-profile FILE.json    check an ICP profile and print its rules in plain English"""
import json
import sys
import time

from . import __version__, db, logs


def main(argv):
    cmd = argv[0] if argv else "serve"
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else d
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd == "--version":
        print(__version__)
        return 0
    logs.setup()
    if cmd == "serve":
        from .server import serve
        serve(opt("--host"), opt("--port"))
    elif cmd == "worker":
        from .runner import Runner
        r = Runner()
        r.start()
        while True:
            time.sleep(3600)
    elif cmd == "migrate":
        app = db.app_db()
        for (wid,) in app.execute("SELECT id FROM workspaces").fetchall():
            db.ws_db(wid).close()
        app.close()
        print("databases up to date")
    elif cmd == "backup":
        from .backup import backup
        print(backup(opt("--out")))
    elif cmd == "restore":
        if "--yes" not in argv or len(argv) < 2:
            print("usage: python -m icpq restore FILE --yes")
            return 2
        from .backup import restore
        print("restored; previous data kept at", restore(argv[1]))
    elif cmd == "validate-profile":
        from .icp.schema import describe, normalize, validate
        cfg = json.load(open(argv[1]))
        cfg = cfg.get("config", cfg)
        errs = validate(cfg)
        for t, d in describe(normalize(cfg)):
            print(f"## {t}\n{d}\n")
        print("ERRORS:\n" + "\n".join(errs) if errs else "OK: profile is valid")
        return 1 if errs else 0
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
