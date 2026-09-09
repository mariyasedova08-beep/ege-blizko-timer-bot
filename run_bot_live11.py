import json
import secrets
import sqlite3
from urllib.parse import parse_qs, urlparse

import run_bot_live10

live10 = run_bot_live10
bot = live10.bot


def ensure_sheets_sync_settings():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sheets_sync_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                secret TEXT
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO sheets_sync_settings (id, secret) VALUES (1, NULL)")
        conn.commit()


def get_or_create_sheets_secret():
    ensure_sheets_sync_settings()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute("SELECT secret FROM sheets_sync_settings WHERE id = 1").fetchone()
        value = (row[0] or "").strip() if row else ""
        if not value:
            value = secrets.token_urlsafe(24)
            conn.execute("UPDATE sheets_sync_settings SET secret = ? WHERE id = 1", (value,))
            conn.commit()
    return value


def get_sheets_secret():
    ensure_sheets_sync_settings()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute("SELECT secret FROM sheets_sync_settings WHERE id = 1").fetchone()
    return (row[0] or "").strip() if row else ""


_base_do_post = live10._original_do_post


def sheets_do_post_v2(self):
    parsed = urlparse(self.path)
    if parsed.path != "/sheets/probnik-sync":
        return _base_do_post(self)

    expected_secret = get_sheets_secret()
    supplied_secret = parse_qs(parsed.query).get("secret", [""])[0]
    if not expected_secret or supplied_secret != expected_secret:
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return

    try:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body or "{}")
    except Exception:
        self._send_json(400, {"ok": False, "error": "invalid_json"})
        return

    try:
        rows_saved, students = live10.save_probnik_sync(payload)
    except Exception as exc:
        print("Google Sheets probnik sync error:", repr(exc))
        self._send_json(500, {"ok": False, "error": "storage_error"})
        return

    print("Google Sheets probnik sync:", rows_saved, "rows,", students, "students")
    self._send_json(200, {"ok": True, "rows_saved": rows_saved, "students": students})


bot.CoreAppWebhookHandler.do_POST = sheets_do_post_v2

_original_sheetsstatus = live10.sheetsstatus_command


async def sheetsstatus_with_setup(update, context):
    if not (update.effective_chat.type == "private" and bot.user_is_admin(update)):
        return
    if context.args and context.args[0].lower() == "setup":
        value = get_or_create_sheets_secret()
        await update.message.reply_text(
            "🔐 Код для синхронизации Google Sheets:\n\n"
            + value
            + "\n\nСкопируй его в Apps Script. Никому его не пересылай."
        )
        return
    await _original_sheetsstatus(update, context)


live10.sheetsstatus_command = sheetsstatus_with_setup


if __name__ == "__main__":
    ensure_sheets_sync_settings()
    live10.main()
