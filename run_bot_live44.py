import sqlite3
from datetime import datetime

import run_bot_live43

live43 = run_bot_live43
live42 = live43.live42
live41 = live43.live41
live40 = live43.live40
live39 = live43.live39
live37 = live43.live37
live35 = live43.live35
live34 = live43.live34
live31 = live43.live31
live24 = live43.live24
live17 = live43.live17
bot = live43.bot


def enable_probnik_analysis_now():
    """Enable only automatic post-probnik analysis; regular probnik reminders stay paused."""
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE probnik_analysis_settings
            SET enabled = 1,
                enabled_at = CASE
                    WHEN enabled = 0 OR enabled_at IS NULL THEN ?
                    ELSE enabled_at
                END
            WHERE id = 1
            """,
            (now,),
        )
        # The January task now refers only to the still-paused reminder/poll system.
        conn.execute(
            """
            UPDATE admin_tasks
            SET task_text = ?
            WHERE task_key = ?
            """,
            (
                "Включить обратно напоминания и опросы про пробники в боте",
                live39.PROBNIK_RETURN_TASK_KEY,
            ),
        )
        conn.commit()


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live43.ensure_probnik_analysis_tables()
    enable_probnik_analysis_now()
    live24.main()
