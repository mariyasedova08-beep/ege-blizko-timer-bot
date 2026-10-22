#!/usr/bin/env python3
"""Consistent, private PREPODMIN SQLite + immutable homework attachments bundle.

Uses SQLite online backup *before* selecting files referenced by the snapshot.
Does not edit source data, contact S3, read credentials, or restart services.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
from urllib.parse import quote

NAME = re.compile(r"[0-9a-f]{32}\.(?:pdf|png|jpg)\Z")


def safe_source(p: Path, label: str, *, directory: bool) -> Path:
    if not p.is_absolute() or p.is_symlink():
        raise RuntimeError(f"{label}: unsafe path")
    try:
        state = p.lstat()
    except OSError:
        raise RuntimeError(f"{label}: unavailable") from None
    if directory and not stat.S_ISDIR(state.st_mode):
        raise RuntimeError(f"{label}: not a directory")
    if not directory and not stat.S_ISREG(state.st_mode):
        raise RuntimeError(f"{label}: not a regular file")
    return p


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def snapshot(source: Path, output: Path):
    uri = "file:" + quote(str(source), safe="/") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as live, sqlite3.connect(output, timeout=30) as copy:
        live.backup(copy, pages=100, sleep=0.1)
    os.chmod(output, 0o600)
    with sqlite3.connect(output) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite snapshot integrity failed")


def referenced_files(snapshot_path: Path):
    with sqlite3.connect(snapshot_path) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='teacher_webapp_homework_files'").fetchone()
        if not exists:
            return []
        return db.execute("SELECT stored_name, size_bytes FROM teacher_webapp_homework_files ORDER BY stored_name").fetchall()


def prepare(db_path: Path, attachments_path: Path, destination: Path) -> dict:
    safe_source(db_path, "database", directory=False)
    safe_source(attachments_path, "attachments", directory=True)
    if not destination.is_absolute() or destination.is_symlink() or destination.exists():
        raise RuntimeError("bundle destination must be a new absolute path")
    destination.mkdir(mode=0o700)
    files_dest = destination / "homework_uploads"
    files_dest.mkdir(mode=0o700)
    backup_db = destination / "teacher_product.sqlite3"
    snapshot(db_path, backup_db)
    entries = []
    for name, expected in referenced_files(backup_db):
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise RuntimeError("Untrusted attachment name")
        if not isinstance(expected, int) or expected <= 0:
            raise RuntimeError("Untrusted attachment size")
        src = attachments_path / name
        safe_source(src, "attachment", directory=False)
        if src.stat().st_size != expected:
            raise RuntimeError("Attachment missing or size mismatch")
        target = files_dest / name
        # Uploaded files are immutable; hardlink if same filesystem, otherwise
        # copy and verify. Never modify an existing source file.
        try:
            os.link(src, target, follow_symlinks=False)
        except OSError:
            shutil.copyfile(src, target, follow_symlinks=False)
        if target.stat().st_size != expected or sha256(src) != sha256(target):
            raise RuntimeError("Attachment content mismatch")
        entries.append({"name": name, "bytes": expected, "sha256": sha256(target)})
    manifest = {
        "format": "prepodmin-offsite-v1",
        "database": {"sha256": sha256(backup_db), "bytes": backup_db.stat().st_size},
        "attachments": entries,
    }
    output = destination / "manifest.json"
    with output.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(",", ":"))
    os.chmod(output, 0o600)
    return {"files": len(entries), "db_bytes": backup_db.stat().st_size}


def verify(bundle: Path) -> int:
    safe_source(bundle, "restored bundle", directory=True)
    with (bundle / "manifest.json").open(encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("format") != "prepodmin-offsite-v1":
        raise RuntimeError("Unsupported bundle format")
    db = bundle / "teacher_product.sqlite3"
    safe_source(db, "restored SQLite", directory=False)
    if sha256(db) != manifest["database"]["sha256"] or db.stat().st_size != manifest["database"]["bytes"]:
        raise RuntimeError("Restored SQLite mismatch")
    with sqlite3.connect(db) as c:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Restored SQLite integrity failed")
    got = {name: size for name, size in referenced_files(db)}
    expected = {x["name"]: x["bytes"] for x in manifest["attachments"]}
    if got != expected:
        raise RuntimeError("Restored database and files manifest disagree")
    directory = bundle / "homework_uploads"
    safe_source(directory, "restored attachments", directory=True)
    for x in manifest["attachments"]:
        name = x["name"]
        if not NAME.fullmatch(name):
            raise RuntimeError("Unsafe restored filename")
        src = directory / name
        safe_source(src, "restored attachment", directory=False)
        if src.stat().st_size != x["bytes"] or sha256(src) != x["sha256"]:
            raise RuntimeError("Restored attachment mismatch")
    return len(expected)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("prepare", "verify"))
    p.add_argument("--db", type=Path)
    p.add_argument("--attachments", type=Path)
    p.add_argument("--bundle", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.mode == "prepare":
            if not args.db or not args.attachments:
                p.error("prepare requires --db and --attachments")
            metrics = prepare(args.db, args.attachments, args.bundle)
            print("PREPODMIN_OFFSITE_STAGE_OK attachments=" + str(metrics["files"]))
        else:
            count = verify(args.bundle)
            print("PREPODMIN_OFFSITE_RESTORE_VERIFY_OK attachments=" + str(count))
    except Exception as exc:
        print("PREPODMIN_OFFSITE_STAGE_OR_VERIFY_FAILED:" + type(exc).__name__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
