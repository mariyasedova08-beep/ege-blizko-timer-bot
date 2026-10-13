#!/usr/bin/env python3
"""Daily, local-only, consistent SQLite backups for PREPODMIN on Timeweb.

Never opens or modifies EGE BLIZKO databases. Does not contact external services.
Run as root from the dedicated prepodmin-backup.service.
"""
from datetime import datetime, timedelta, timezone
import fcntl
import os
from pathlib import Path
import re
import time

from sqlite_snapshot import snapshot, sha256_file

SOURCE = Path("/opt/bots/prepodmin/data/teacher_product.sqlite3")
BACKUPS = Path("/var/backups/prepodmin/daily")
LOCK = BACKUPS / ".backup.lock"
BACKUP_NAME = re.compile(r"^prepodmin-daily-\d{8}T\d{6}Z\.sqlite3$")


def main():
    os.umask(0o077)
    if not SOURCE.is_file():
        raise FileNotFoundError("PREPODMIN SQLite source missing; no backup generated")
    if not BACKUPS.is_dir() or BACKUPS.is_symlink():
        raise RuntimeError("Protected PREPODMIN backup directory must already exist")
    if BACKUPS.stat().st_uid != 0 or BACKUPS.stat().st_mode & 0o077:
        raise PermissionError("PREPODMIN backups directory must be root-owned mode 0700")

    # Avoid concurrent writes or cleanup if a manual backup overlaps the timer.
    fd = os.open(str(LOCK), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            now = datetime.now(timezone.utc)
            dest = BACKUPS / ("prepodmin-daily-" + now.strftime("%Y%m%dT%H%M%SZ") + ".sqlite3")
            metrics = snapshot(SOURCE, dest)
            if metrics["integrity_check"] != "ok":
                raise RuntimeError("PREPODMIN backup integrity check failed")

            # Only delete files created by this daily-backup scheme, older than
            # 30 days, and only after a new verified copy was created.
            cutoff = time.time() - timedelta(days=30).total_seconds()
            pruned = 0
            for old in BACKUPS.iterdir():
                if old == dest or not BACKUP_NAME.fullmatch(old.name):
                    continue
                if old.is_symlink() or not old.is_file():
                    continue
                if old.stat().st_mtime < cutoff:
                    old.unlink()
                    pruned += 1

            print("PREPODMIN_BACKUP_OK", flush=True)
            print("backup=" + str(dest), flush=True)
            print("bytes=" + str(dest.stat().st_size), flush=True)
            print("integrity_check=ok", flush=True)
            print("sha256=" + sha256_file(dest), flush=True)
            print("pruned_older_than_30_days=" + str(pruned), flush=True)
            print("BACKUP_STORAGE=LOCAL_ONLY", flush=True)
    except BaseException:
        # snapshot() already removes partial new files on failure. No deletion
        # is attempted before snapshot() + integrity check both succeed.
        raise


if __name__ == "__main__":
    main()
