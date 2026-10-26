"""Credentials (API keys) for research and AI providers.

Stored in <data>/secrets.json with owner-only permissions (0600), never written to logs, exports or API responses
(the Settings page only ever sees a masked value). An environment variable ICPQ_SECRET_<NAME> overrides the file, so
container deployments can inject keys from a secret manager instead."""
import json
import os
import threading

from .db import data_dir

_lock = threading.Lock()


def _path():
    return data_dir() / "secrets.json"


def _load():
    p = _path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except ValueError:
        return {}


def get_secret(name):
    env = os.environ.get("ICPQ_SECRET_" + name.upper())
    if env:
        return env
    return _load().get(name, "")


def set_secret(name, value):
    with _lock:
        d = _load()
        if value:
            d[name] = value
        else:
            d.pop(name, None)
        p = _path()
        tmp = p.with_name(".secrets.tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(d, f)
        os.replace(tmp, p)
        os.chmod(p, 0o600)


def masked(name):
    v = get_secret(name)
    return ("•" * 6 + v[-4:]) if len(v) > 8 else ("set" if v else "")
