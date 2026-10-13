#!/usr/bin/env python3
"""Create a brand-new PRIVATE SQLite database for an isolated PREPODMIN instance.

No Railway data is read. Fails if the destination already exists, even if empty.
Application schema is subsequently created by teacher_product_runner.py on boot.
"""
import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def initialize(path: Path) -> Path:
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise FileExistsError(f"Refusing a symlink: {path}")
    # The base directory must be provisioned for the dedicated prepodmin user.
    if not path.parent.is_dir():
        raise FileNotFoundError(f"Create the protected data directory first: {path.parent}")
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.execute("""
                CREATE TABLE prepodmin_install_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    created_at TEXT NOT NULL,
                    origin TEXT NOT NULL CHECK (origin = 'fresh-empty')
                )
            """)
            conn.execute(
                "INSERT INTO prepodmin_install_meta VALUES (1, ?, 'fresh-empty')",
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.commit()
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        os.chmod(path, 0o600)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True,
                        help="New destination, for example /opt/bots/prepodmin/data/teacher_product.sqlite3")
    args = parser.parse_args()
    db = initialize(args.db)
    print(f"Fresh PREPODMIN SQLite database created: {db}")
    print("SQLite integrity_check: ok")
    print("No Railway data has been copied; bot token is NOT configured by this command.")


if __name__ == "__main__":
    main()
