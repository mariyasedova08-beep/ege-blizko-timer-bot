"""Restart-safe active trainer sessions for EGE BLIZKO.

Telegram callback buttons can be pressed long after a deployment/restart.  The
trainer modules historically kept the active quiz only in context.user_data,
which is process memory.  This helper mirrors active session state into the
existing persistent SQLite database so a learner can continue after a restart.
"""
import json
import sqlite3
from datetime import datetime

import run_bot_live90 as live90

bot = live90.bot


def ensure_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trainer_active_sessions (
                trainer TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                session_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (trainer, telegram_user_id)
            )
            """
        )
        conn.commit()


def save(trainer, user_id, session):
    if not session:
        return
    ensure_table()
    payload = json.dumps(session, ensure_ascii=False, separators=(",", ":"))
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO trainer_active_sessions(
                trainer,telegram_user_id,session_json,updated_at
            ) VALUES(?,?,?,?)
            ON CONFLICT(trainer,telegram_user_id) DO UPDATE SET
                session_json=excluded.session_json,
                updated_at=excluded.updated_at
            """,
            (str(trainer), int(user_id), payload, now),
        )
        conn.commit()


def load(trainer, user_id):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT session_json
            FROM trainer_active_sessions
            WHERE trainer=? AND telegram_user_id=?
            """,
            (str(trainer), int(user_id)),
        ).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row[0])
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def delete(trainer, user_id):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "DELETE FROM trainer_active_sessions WHERE trainer=? AND telegram_user_id=?",
            (str(trainer), int(user_id)),
        )
        conn.commit()


def restore_if_matches(context, context_key, trainer, user_id, token):
    session = context.user_data.get(context_key)
    if session and session.get("token") == token:
        return session
    restored = load(trainer, user_id)
    if restored and restored.get("token") == token:
        context.user_data[context_key] = restored
        return restored
    return None
