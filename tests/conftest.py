import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, ""
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, headers=None, raw=False):
        h = {"X-CSRF": self.csrf, **(headers or {})}
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        if data is not None and not isinstance(body, bytes):
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            r = self.op.open(req, timeout=60)
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                b = gzip.decompress(b)
            return r.status, (b if raw else json.loads(b or b"{}"))
        except urllib.error.HTTPError as e:
            b = e.read()
            try:
                return e.code, json.loads(b)
            except ValueError:
                return e.code, b

    def login(self, email, pw):
        st, _ = self.call("POST", "/api/login", {"email": email, "password": pw})
        assert st == 200
        self.csrf = self.call("GET", "/api/me")[1]["csrf"]


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    port = free_port()
    env = {**os.environ, "ICPQ_DATA": str(data), "ICPQ_PORT": str(port), "ICPQ_FIXTURE_SITES": str(ROOT / "tests/fixtures/sites"),
           "ICPQ_PBKDF2_ITER": "2000", "ICPQ_THREADS": "2", "ICPQ_LOG_LEVEL": "WARNING"}
    p = subprocess.Popen([sys.executable, "-m", "icpq", "serve"], cwd=ROOT, env=env, stderr=open(data / "server.err", "w"))
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    yield {"base": base, "data": data, "proc": p}
    p.terminate()
    p.wait(10)
