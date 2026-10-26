"""Structured logging: one JSON object per line on stderr (and <data>/logs/icpq.log), easy to ship to any log system."""
import json
import logging
import logging.handlers
import os
import sys

from .db import data_dir


class JSONFormatter(logging.Formatter):
    def format(self, r):
        d = {"t": self.formatTime(r, "%Y-%m-%dT%H:%M:%S%z"), "level": r.levelname, "logger": r.name, "msg": r.getMessage()}
        if r.exc_info:
            d["exc"] = self.formatException(r.exc_info)[-2000:]
        return json.dumps(d)


def setup(level=None):
    lvl = getattr(logging, (level or os.environ.get("ICPQ_LOG_LEVEL", "INFO")).upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(lvl)
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(JSONFormatter())
    root.addHandler(h)
    d = data_dir() / "logs"
    d.mkdir(exist_ok=True)
    f = logging.handlers.RotatingFileHandler(d / "icpq.log", maxBytes=5_000_000, backupCount=5)
    f.setFormatter(JSONFormatter())
    root.addHandler(f)
