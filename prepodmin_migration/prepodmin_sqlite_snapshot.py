#!/usr/bin/env python3
"""Make a consistent, private SQLite snapshot for PREPADMIN migration.

Does not start the Telegram bot, change the source database, or print row data.
Usage:
    python prepodmin_sqlite_snapshot.py --source /data/teacher_product.sqlite3 --dest /data/prepodmin-export.sqlite3

Keep snapshots OUT of Git repositories. Export only over authenticated transport.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


TABLES_TO_COUNT = (
    "teachers", "students", "teacher_groups", "teacher_homework",
    "teacher_homework_status", "teacher_tasks", "student_payment_plans",
)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if not source.is_file():
        raise FileNotFoundError("Source SQLite database was not found: " + str(source))
    if source == dest:
        raise ValueError("Destination must differ from the source database")
    if dest.exists():
        raise FileExistsError("Destination exists; use a new timestamped filename: " + str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".prepodmin-copy-", suffix=".sqlite3", dir=str(dest.parent))
    os.fchmod(fd, 0o600)
    os.close(fd)
    try:
        # SQLite's online backup API includes committed WAL data consistently.
        # Opening the source read-only guarantees this tool will not change it.
        source_uri = source.as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True, timeout=30) as src:
            with sqlite3.connect(temporary, timeout=30) as dst:
                src.backup(dst, pages=256, sleep=0.1)
        with sqlite3.connect(temporary) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError("Snapshot integrity_check failed")
            present = {row[0] for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            counts = {}
            for table in TABLES_TO_COUNT:
                if table in present:
                    counts[table] = check.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
        os.replace(temporary, dest)
        os.chmod(dest, 0o600)
        return {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_filename": dest.name,
            "bytes": dest.stat().st_size,
            "sha256": sha256(dest),
            "integrity_check": "ok",
            "table_counts": counts,
        }
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv(
        "TEACHER_PRODUCT_DB_PATH", "/data/teacher_product.sqlite3"))
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source, args.dest), ensure_ascii=False, indent=2))
