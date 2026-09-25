"""Monthly salary tasks for Polina in the EGE BLIZKO admin task list."""

import sqlite3
from datetime import datetime

import run_bot_live90 as live90

bot = live90.bot
live79 = live90.live79

TASK_TEXT = "Выплатить Полине зарплату"
REMINDER_TIME = "10:00"

DATES = (
    "2026-09-25",
    "2026-10-30",
    "2026-11-27",
    "2026-12-25",
    "2027-01-29",
    "2027-02-26",
    "2027-03-26",
    "2027-04-30",
    "2027-05-28",
)


def seed():
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    created = 0
    reused = 0
    now = datetime.now(bot.TIMEZONE).isoformat()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for day in DATES:
            task_key = f"polina-salary-{day}"
            existing = conn.execute(
                """
                SELECT id
                FROM admin_tasks
                WHERE completed_at IS NULL
                  AND start_date = ?
                  AND (
                      task_key = ?
                      OR task_text = ?
                      OR task_text = 'Зарплата Полине'
                  )
                LIMIT 1
                """,
                (day, task_key, TASK_TEXT),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE admin_tasks
                    SET reminder_time = ?, task_kind = 'task'
                    WHERE id = ?
                    """,
                    (REMINDER_TIME, int(existing[0])),
                )
                reused += 1
                continue

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO admin_tasks
                    (task_key, task_text, start_date, reminder_time, created_at, task_kind)
                VALUES (?, ?, ?, ?, ?, 'task')
                """,
                (
                    task_key,
                    TASK_TEXT,
                    day,
                    REMINDER_TIME,
                    now,
                ),
            )
            if cur.rowcount:
                created += 1

        conn.commit()

        active = conn.execute(
            """
            SELECT COUNT(*)
            FROM admin_tasks
            WHERE completed_at IS NULL
              AND task_key LIKE 'polina-salary-%'
              AND start_date IN ({})
            """.format(",".join("?" for _ in DATES)),
            DATES,
        ).fetchone()[0]

    print(
        f"Polina salary tasks ready: active={int(active or 0)} "
        f"created={created} reused={reused} time={REMINDER_TIME}",
        flush=True,
    )
