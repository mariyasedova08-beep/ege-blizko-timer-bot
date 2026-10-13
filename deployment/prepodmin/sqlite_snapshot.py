#!/usr/bin/env python3
"""Create or inspect a privacy-preserving, online SQLite snapshot for PREPODMIN.

Does not change the source database or expose teacher/student rows. Run with
--source and --output on a host that can read the source database. The backup
uses SQLite's supported online backup API; do not use cp on a live WAL database.
"""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

TABLES = (
    "teachers", "students", "teacher_groups", "student_reminder_people",
    "schedule_slots", "group_schedule_slots", "teacher_homework",
    "student_payment_plans", "group_member_payment_plans",
    "teacher_tasks", "teacher_materials",
)


def db_metrics(path: Path) -> dict:
    uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as connection:
        outcome = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if outcome != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {outcome}")
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        counts = {}
        for name in TABLES:
            if name in names:
                counts[name] = int(connection.execute(
                    f'SELECT COUNT(*) FROM "{name}"'
                ).fetchone()[0])
        return {
            "integrity_check": "ok",
            "table_count": len(names),
            "user_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "row_counts": counts,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(source: Path, output: Path):
    source = source.resolve(strict=True)
    output = output.absolute()
    if source == output or (output.exists() and os.path.samefile(source, output)):
        raise ValueError("Source and backup must be different files")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        uri = "file:" + quote(str(source), safe="/") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=30) as src:
            with sqlite3.connect(str(output), timeout=30) as dst:
                src.backup(dst, pages=100, sleep=0.2)
        os.chmod(output, 0o600)
        metrics = db_metrics(output)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Existing SQLite database or snapshot to inspect")
    parser.add_argument("--output", type=Path,
                        help="New backup destination; must not exist")
    args = parser.parse_args()
    src = args.source
    if not src.is_file() or not src.stat().st_size:
        parser.error("Source SQLite file is missing or empty")
    if args.output:
        metrics = snapshot(src, args.output)
        target = args.output.absolute()
        mode = "snapshot"
    else:
        metrics = db_metrics(src)
        target = src.absolute()
        mode = "inspect"
    print(json.dumps({
        "mode": mode,
        "file": str(target),
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        **metrics,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
