"""Idempotent one-time tutor reminder requested by Maria for 2026-09-14 10:00 Moscow time."""

import sqlite3
from datetime import datetime

import run_bot_live6 as tutor


REMINDER_TEXT = (
    "У 10 класса на вторник есть письменное ДЗ, поэтому его нужно будет проверять. "
    "Мария Александровна пришлёт."
)
RUN_DATE = "2026-09-14"
RUN_TIME = "10:00"


def seed():
    tutor.ensure_tutor_tables()
    now = datetime.now(tutor.bot.TIMEZONE).isoformat()
    with sqlite3.connect(tutor.bot.COREAPP_DB_PATH) as conn:
        exists = conn.execute(
            """
            SELECT 1
            FROM tutor_reminders
            WHERE reminder_text = ?
              AND schedule_kind = 'once'
              AND run_date = ?
              AND run_time = ?
            LIMIT 1
            """,
            (REMINDER_TEXT, RUN_DATE, RUN_TIME),
        ).fetchone()
        if exists:
            print("Tutor reminder 2026-09-14 10:00 already present", flush=True)
            return

        conn.execute(
            """
            INSERT INTO tutor_reminders (
                reminder_text, schedule_kind, run_date, run_time, weekdays,
                active, last_sent_key, created_at, updated_at
            ) VALUES (?, 'once', ?, ?, NULL, 1, NULL, ?, ?)
            """,
            (REMINDER_TEXT, RUN_DATE, RUN_TIME, now, now),
        )
        conn.commit()
    print("Tutor reminder 2026-09-14 10:00 seeded", flush=True)


seed()
