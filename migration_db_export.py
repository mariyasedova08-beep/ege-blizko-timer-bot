"""Temporary final HTTP wrapper for safe SQLite migration backup.

Remove after Timeweb migration is complete.
"""
import os
import sqlite3
import tempfile
from urllib.parse import urlparse

import run_bot_live90 as live90

bot = live90.bot
PATH = "/admin/migration-db-backup"
_previous_get = bot.CoreAppWebhookHandler.do_GET


def _migration_get(self):
    if urlparse(self.path).path != PATH:
        return _previous_get(self)

    expected = os.getenv("COREAPP_DIAG_SECRET", "").strip()
    supplied = self.headers.get("X-Migration-Secret", "").strip()
    if not expected or supplied != expected:
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="ege-migration-", suffix=".db")
        os.close(fd)
        with sqlite3.connect(bot.COREAPP_DB_PATH) as source:
            with sqlite3.connect(temp_path) as target:
                source.backup(target)
        with open(temp_path, "rb") as handle:
            body = handle.read()

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition",
            'attachment; filename="ege-blizko-coreapp.db"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        print(f"Migration DB backup served: bytes={len(body)}", flush=True)
    except Exception as exc:
        print(
            f"Migration DB backup failed: {type(exc).__name__}",
            flush=True,
        )
        self._send_json(500, {"ok": False, "error": "backup_failed"})
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


bot.CoreAppWebhookHandler.do_GET = _migration_get
print(f"Migration DB export ready: GET {PATH}", flush=True)
