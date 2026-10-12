#!/usr/bin/env python3
"""Conservative pull-deployer for the *existing* Timeweb EGE BLIZKO service.

Polls only release/ege-blizko-prod; does not git checkout, pull, reset, or
clean in the live tree. Protects live-only files and local edits. Rollback of
code files is automatic; database snapshots are kept, never blindly restored.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path("/opt/bots/ege-blizko")
STATE = Path("/var/lib/ege-blizko-deploy")
BACKUPS = Path("/var/backups/ege-blizko-deploy")
TARGET_REF = "refs/remotes/origin/release/ege-blizko-prod"
FETCH_SPEC = "refs/heads/release/ege-blizko-prod:" + TARGET_REF
SERVICE = "ege-blizko"
DB_PATH = ROOT / "data/coreapp_webhooks.db"
EXTENSIONS = {".py", ".html", ".js", ".css", ".json", ".md", ".txt"}
FORBIDDEN = {
    "runtime-vars.json", "timeweb_runner.py", ".env", ".gitignore",
    "ege_lab_webapp.py",
}
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", "data", ".github"}
SIMPLE_NAME = re.compile(r"[A-Za-z0-9_.\-/]+")


def cmd(*args, check=True, cwd=ROOT):
    proc = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    if check and proc.returncode:
        error = proc.stderr.decode("utf-8", "replace").strip()[:800]
        raise RuntimeError("Command failed: " + " ".join(args[:3]) + ": " + error)
    return proc


def output(*args):
    return cmd(*args).stdout.decode("utf-8", "replace").strip()


def snapshot_sqlite(dest):
    if not DB_PATH.is_file():
        raise RuntimeError("Database missing: " + str(DB_PATH))
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as source:
        with sqlite3.connect(dest, timeout=30) as backup:
            source.backup(backup, pages=512, sleep=0.05)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database snapshot failed integrity_check")
    dest.chmod(0o600)


def safe_path(path):
    p = Path(path)
    if (not SIMPLE_NAME.fullmatch(path) or p.is_absolute() or
            ".." in p.parts or not p.parts or
            any(x in FORBIDDEN_PARTS for x in p.parts) or
            p.name in FORBIDDEN or p.suffix not in EXTENSIONS):
        raise RuntimeError("Unsafe or unsupported release path: " + repr(path))
    current = ROOT
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError("Symbolic links not permitted: " + path)
    return ROOT / p


def git_blob(rev, path, optional=False):
    proc = cmd("git", "show", rev + ":" + path, check=False)
    if proc.returncode != 0:
        if optional:
            return None
        raise RuntimeError("Cannot read Git blob: " + path)
    return proc.stdout


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".ege-deploy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def check_service():
    # Avoid overwriting sensitive information by printing journal text.
    for _ in range(3):
        time.sleep(5)
        if cmd("systemctl", "is-active", "--quiet", SERVICE, check=False).returncode:
            raise RuntimeError("Service is not active after restart")
    # An optional HTTPS probe can be added after it is verified in production.


def deploy():
    os.umask(0o077)
    if os.geteuid() != 0:
        raise RuntimeError("Root required for existing root-managed service")
    if not (ROOT / ".git").is_dir():
        raise RuntimeError("Unexpected application location")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    BACKUPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = STATE / "deployed_commit"
    if not marker.is_file():
        raise RuntimeError("Not initialized. Run deploy bootstrap first.")

    # Fetch from the existing origin, but never change HEAD or working branch.
    cmd("git", "fetch", "--no-tags", "origin", FETCH_SPEC)
    desired = output("git", "rev-parse", TARGET_REF)
    current = marker.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", current):
        raise RuntimeError("Invalid deployed revision marker")
    if current == desired:
        return print("EGE deploy: no new approved release", flush=True)
    if cmd("git", "merge-base", "--is-ancestor", current, desired,
           check=False).returncode:
        raise RuntimeError("Release branch is not a fast-forward of installed release")

    changes = output("git", "diff", "--no-renames", "--name-status", current, desired)
    proposed = []
    for row in changes.splitlines():
        status, sep, relative = row.partition("\t")
        if not sep or status not in {"A", "M"}:
            raise RuntimeError("Unsupported release change: " + row)
        path = safe_path(relative)
        newer = git_blob(desired, relative)
        older = git_blob(current, relative, optional=(status == "A"))
        original = path.read_bytes() if path.exists() else None
        if original == newer:
            continue   # Already installed manually; no overwrite needed.
        if original != older:
            raise RuntimeError("Local modifications protected: " + relative)
        if path.suffix == ".py":
            compile(newer, relative, "exec")
        proposed.append((path, relative, original, newer))

    batch_name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + desired[:12]
    backup_dir = BACKUPS / batch_name
    backup_dir.mkdir(mode=0o700)
    snapshot_sqlite(backup_dir / "coreapp_webhooks.sqlite3")
    saved = []
    for path, relative, older, newer in proposed:
        if older is not None:
            original_path = backup_dir / "files" / relative
            original_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(original_path, older, 0o600)
        saved.append((path, relative, older))

    changed = []
    try:
        for path, relative, older, newer in proposed:
            mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
            atomic_write(path, newer, mode)
            changed.append((path, older))
        if changed:
            cmd("systemctl", "restart", SERVICE)
            check_service()
        atomic_write(marker, (desired + "\n").encode(), 0o600)
        print("EGE deploy SUCCESS revision=" + desired[:12] +
              " files=" + str(len(changed)) + " backup=" + str(backup_dir), flush=True)
    except Exception:
        print("EGE deploy FAILED - rolling back code files", file=sys.stderr, flush=True)
        for path, older in reversed(changed):
            if older is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, older, 0o644)
        if changed:
            cmd("systemctl", "restart", SERVICE, check=False)
        print("EGE deploy rollback complete; database snapshot kept at " + str(backup_dir),
              file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    try:
        deploy()
    except Exception as e:
        print("EGE deploy ERROR: " + str(e), file=sys.stderr, flush=True)
        sys.exit(1)
