"""One-day hourly reminder for the Timeweb migration task.

Task date: 2026-10-08.
Reminders: 09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 Moscow.
Stops immediately when the admin task is marked completed.
"""
import sqlite3
from datetime import date, datetime

import run_bot_live90 as live90

bot = live90.bot
live79 = live90.live79
live7 = live79.live7
live35 = live79.live35

TASK_KEY = "timeweb-migration-2026-10-08"
TASK_TEXT = "Перенести ботов с Railway на Timeweb Cloud"
TASK_DATE = date(2026, 10, 8)
REMINDER_MINUTE = 30
REMINDER_HOURS = tuple(range(9, 16))


def ensure_delivery_table():
    live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_hourly_task_deliveries (
                task_key TEXT NOT NULL,
                slot_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(task_key, slot_key)
            )
            """
        )
        conn.commit()


def seed():
    ensure_delivery_table()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM admin_tasks WHERE task_key=? LIMIT 1",
            (TASK_KEY,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE admin_tasks
                SET task_text=?, start_date=?, reminder_time='09:30', task_kind='task'
                WHERE task_key=?
                """,
                (TASK_TEXT, TASK_DATE.isoformat(), TASK_KEY),
            )
        else:
            conn.execute(
                """
                INSERT INTO admin_tasks(
                    task_key, task_text, start_date, reminder_time, created_at, task_kind
                ) VALUES(?,?,?,?,?,'task')
                """,
                (TASK_KEY, TASK_TEXT, TASK_DATE.isoformat(), "09:30", now),
            )
        conn.commit()
    print(
        "Timeweb migration task ready: 2026-10-08 reminders=09:30..15:30 hourly",
        flush=True,
    )


def _task_row():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, completed_at
            FROM admin_tasks
            WHERE task_key=?
            LIMIT 1
            """,
            (TASK_KEY,),
        ).fetchone()


def _slot_sent(slot_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM admin_hourly_task_deliveries
                WHERE task_key=? AND slot_key=? LIMIT 1
                """,
                (TASK_KEY, slot_key),
            ).fetchone()
        )


def _mark_slot_sent(slot_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO admin_hourly_task_deliveries(task_key,slot_key,sent_at)
            VALUES(?,?,?)
            """,
            (TASK_KEY, slot_key, datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


async def hourly_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.date() != TASK_DATE:
        return
    if now.hour not in REMINDER_HOURS or now.minute < REMINDER_MINUTE:
        return

    row = _task_row()
    if not row:
        seed()
        row = _task_row()
    if not row:
        return

    task_id, completed_at = row
    if completed_at:
        return

    slot_key = f"{TASK_DATE.isoformat()}-{now.hour:02d}:30"
    if _slot_sent(slot_key):
        return

    admin_id = bot.get_admin_id()
    if not admin_id:
        return

    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "⏰ <b>Рабочая задача</b>\n\n"
                f"{TASK_TEXT}\n\n"
                f"Напоминание {now.hour:02d}:30 · до 15:30 сегодня."
            ),
            parse_mode="HTML",
            reply_markup=live35._task_markup(int(task_id)),
        )
    except Exception as exc:
        print(
            f"TIMEWEB_MIGRATION_REMINDER failed slot={slot_key} "
            f"error={type(exc).__name__}",
            flush=True,
        )
        return

    _mark_slot_sent(slot_key)
    print(f"TIMEWEB_MIGRATION_REMINDER sent slot={slot_key}", flush=True)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_timeweb_task(context):
    try:
        await _previous_tick(context)
    finally:
        await hourly_tick(context)


live7.friday_trivial_tick = combined_tick_with_timeweb_task
seed()
