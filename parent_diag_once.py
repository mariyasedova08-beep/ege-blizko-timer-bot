"""Temporary read-only diagnostics for parent cabinet SQLite schema."""
import sqlite3
import traceback
import parent_admin_ui
import parent_cabinet

bot = parent_cabinet.bot

try:
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for table in ("parent_invites", "parent_links", "students"):
            try:
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
                print(f"PARENT_DIAG schema {table}={[(c[1], c[2]) for c in cols]}", flush=True)
            except Exception as exc:
                print(f"PARENT_DIAG schema_error {table}: {type(exc).__name__}: {exc}", flush=True)
    try:
        text = parent_admin_ui.parents_text()
        print(f"PARENT_DIAG parents_text_ok len={len(text)}", flush=True)
    except Exception as exc:
        print(f"PARENT_DIAG parents_text_error {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
except Exception as exc:
    print(f"PARENT_DIAG outer_error {type(exc).__name__}: {exc}", flush=True)
    traceback.print_exc()
