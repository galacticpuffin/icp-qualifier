"""Backup and restore of the whole data directory (all databases, consistent snapshots via the SQLite backup API).

  python -m icpq backup [--out DIR]      -> DIR/icpq-backup-<UTC>.tar.gz
  python -m icpq restore FILE --yes      replaces the data directory (the current one is kept as data.before-restore-<UTC>)"""
import io
import shutil
import sqlite3
import tarfile
import time
from pathlib import Path

from .db import data_dir


def backup(out=None):
    d = data_dir()
    out = Path(out or d / "backups")
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = out / f"icpq-backup-{stamp}.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        for f in sorted(d.rglob("*")):
            rel = f.relative_to(d)
            if not f.is_file() or rel.parts[0] in ("backups", "logs") or f.suffix in (".db-wal", ".db-shm") or f.name.endswith(("-wal", "-shm")):
                continue
            if f.suffix == ".db":
                src, mem = sqlite3.connect(str(f)), sqlite3.connect(":memory:")
                src.backup(mem)
                src.close()
                data = mem.serialize()
                mem.close()
                ti = tarfile.TarInfo(str(rel))
                ti.size, ti.mtime, ti.mode = len(data), int(time.time()), 0o600
                tar.addfile(ti, io.BytesIO(data))
            else:
                tar.add(f, arcname=str(rel))
    dest.chmod(0o600)
    return dest


def restore(path):
    d = data_dir()
    path = Path(path)
    with tarfile.open(path, "r:gz") as tar:
        names = tar.getnames()
        if not any(n == "app.db" for n in names):
            raise ValueError("not an ICP Qualifier backup (app.db missing)")
        for m in tar.getmembers():
            if m.name.startswith(("/", "..")) or ".." in Path(m.name).parts or not (m.isfile() or m.isdir()):
                raise ValueError(f"unsafe path in backup: {m.name}")
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        keep = d.with_name(d.name + f".before-restore-{stamp}")
        shutil.copytree(d, keep, ignore=shutil.ignore_patterns("backups"))
        for f in d.iterdir():
            if f.name != "backups":
                shutil.rmtree(f) if f.is_dir() else f.unlink()
        tar.extractall(d, filter="data")
    return keep
