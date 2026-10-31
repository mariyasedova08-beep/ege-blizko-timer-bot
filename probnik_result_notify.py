"""Personal probnik publication notifications.

Isolated, opt-in queue. Never sends from the Sheets webhook thread.
PROBNIK_RESULT_NOTIFY_ENABLED=1 is required for enqueue AND delivery.
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

ENV_FLAG = "PROBNIK_RESULT_NOTIFY_ENABLED"
_dispatch_running = False


def enabled():
    return os.getenv(ENV_FLAG, "").strip() == "1"


def ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS probnik_result_notice_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            student_name TEXT NOT NULL,
            event_name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sent_at TEXT,
            reason TEXT
        )
    """)


def queue_publication(conn, *, student_name, event_name, event_date,
                      new_primary, new_secondary):
    """Send at most one notice per published student/event, irrespective of edits.

    Only the publication transition coming from status-aware sheets may queue.
    """
    if not enabled() or (new_primary is None and new_secondary is None):
        return False
    ensure_tables(conn)
    fingerprint = hashlib.sha256(
        json.dumps([student_name, event_name, event_date],
                   ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cur = conn.execute("""
        INSERT OR IGNORE INTO probnik_result_notice_queue
        (fingerprint, student_name, event_name, event_date, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (fingerprint, student_name, event_name, event_date,
          datetime.now(timezone.utc).isoformat()))
    return bool(cur.rowcount)


async def dispatch_pending(context):
    """Prevent overlapping delivery ticks in this bot process.

    This is a single-process guard, not a cross-process delivery guarantee.
    """
    global _dispatch_running
    if not enabled() or _dispatch_running:
        return
    # No await between checking and setting: atomic within the bot event loop.
    _dispatch_running = True
    try:
        await _dispatch_pending(context)
        if os.getenv("PROBNIK_PARENT_NOTIFY_ENABLED", "").strip() == "1":
            try:
                import probnik_parent_notify
                await probnik_parent_notify.dispatch_pending(context)
            except Exception as exc:
                print("Probnik parent dispatch failed:", type(exc).__name__, flush=True)
    finally:
        _dispatch_running = False


async def _dispatch_pending(context):
    """Deliver only to an unambiguously matched, Telegram-linked student."""
    if not enabled():
        return
    import run_bot_live56 as live56
    from run_bot_live56 import bot

    student_rows = live56._all_active_students()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        ensure_tables(conn)
        pending = conn.execute("""
            SELECT id, student_name, event_name, event_date
            FROM probnik_result_notice_queue
            WHERE status = 'pending'
            ORDER BY id LIMIT 30
        """).fetchall()

    for notice_id, student_name, event_name, event_date in pending:
        student = live56.unique_probnik_student_match(student_name, student_rows)
        if student is None:
            status, reason = "blocked", "ambiguous_or_missing_student"
        elif len(student) < 6 or student[5] is None:
            status, reason = "blocked", "no_telegram_link"
        else:
            # Message contains no score: results remain private in the cabinet.
            message = (
                "🧪 ЕГЭ БЛИЗКО\n\n"
                "Твой результат пробника опубликован!\n"
                f"📝 {event_name} · {event_date}\n\n"
                "Открой свой личный кабинет → «Пробники», "
                "чтобы посмотреть баллы и задания. 💗"
            )
            try:
                await context.bot.send_message(chat_id=int(student[5]), text=message)
            except Exception as exc:
                # Keep pending for later retry; never expose chat ids in logs.
                print("Probnik result notification send failed:", type(exc).__name__, flush=True)
                continue
            status, reason = "sent", None

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute("""
                UPDATE probnik_result_notice_queue
                SET status = ?, reason = ?,
                    sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
                WHERE id = ? AND status = 'pending'
            """, (status, reason, status, datetime.now(timezone.utc).isoformat(), notice_id))
            conn.commit()

