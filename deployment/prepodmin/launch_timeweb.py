#!/usr/bin/env python3
"""Isolated Timeweb launcher for PREPODMIN; refuses unsafe env/DB configuration.

This launcher is an additional guard, not a replacement for systemd privileges.
"""
import os
import pwd
import sqlite3
import sys
from pathlib import Path

APP_ROOT = Path("/opt/bots/prepodmin/current")
DB_FILE = Path("/opt/bots/prepodmin/data/teacher_product.sqlite3")
EXPECTED = {
    "TEACHER_PRODUCT_DB_PATH": str(DB_FILE),
    "PORT": "8091",
    "TEACHER_PRODUCT_BIND_HOST": "127.0.0.1",
}


def verify() -> None:
    if os.geteuid() == 0 or pwd.getpwuid(os.geteuid()).pw_name != "prepodmin":
        raise RuntimeError("Refusing to start: must run as dedicated prepodmin user")
    for name, value in EXPECTED.items():
        if os.environ.get(name) != value:
            raise RuntimeError(f"Refusing to start: invalid {name}")
    if not APP_ROOT.joinpath("teacher_product_runner.py").is_file():
        raise FileNotFoundError("PREPODMIN application entrypoint is missing")
    if not DB_FILE.is_file():
        raise FileNotFoundError("Fresh PREPODMIN database missing")
    # A never-before-created DB should not be auto-created by the application.
    db_uri = "file:" + str(DB_FILE) + "?mode=ro"
    with sqlite3.connect(db_uri, uri=True, timeout=15) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("PREPODMIN database integrity check failed")
        row = connection.execute(
            "SELECT origin FROM prepodmin_install_meta WHERE id=1"
        ).fetchone()
        if not row or row[0] != "fresh-empty":
            raise RuntimeError("Refusing to start non-fresh or unexpected database")

    # Before token activation, the WebApp can safely run on loopback for health tests.
    if os.getenv("TEACHER_PRODUCT_BOT_TOKEN", "").strip():
        urls = (
            "TEACHER_PRODUCT_WEBAPP_URL",
            "TEACHER_PRODUCT_STUDENT_WEBAPP_URL",
        )
        for name in urls:
            url = os.getenv(name, "").strip()
            if not url.startswith("https://") or ".up.railway.app" in url:
                raise RuntimeError(f"Refusing Telegram polling: {name} needs new HTTPS host")
        if os.environ["TEACHER_PRODUCT_WEBAPP_URL"] == os.environ["TEACHER_PRODUCT_STUDENT_WEBAPP_URL"]:
            raise RuntimeError("Teacher and student WebApp URLs must be distinct paths")


if __name__ == "__main__":
    verify()
    print("PREPODMIN Timeweb environment verified; starting isolated runner", flush=True)
    os.execv(sys.executable, [sys.executable, str(APP_ROOT / "teacher_product_runner.py")])
