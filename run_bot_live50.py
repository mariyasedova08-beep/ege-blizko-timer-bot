import sqlite3
from datetime import date, datetime

import run_bot_live49

live49 = run_bot_live49
live48 = live49.live48
live47 = live49.live47
live46 = live49.live46
live45 = live49.live45
live44 = live49.live44
live43 = live49.live43
live41 = live49.live41
live39 = live49.live39
live37 = live49.live37
live35 = live49.live35
live34 = live49.live34
live31 = live49.live31
live24 = live49.live24
live17 = live49.live17
bot = live49.bot

MOLAR_MASS_TASK_KEY = "connect-molar-mass-table-2026-09-14"
MOLAR_MASS_TASK_DATE = date(2026, 9, 14)
MOLAR_MASS_TASK_TEXT = "Подключить таблицу с молярными массами к боту"
MOLAR_MASS_TASK_TIME = "10:00"


def seed_molar_mass_task():
    live35.ensure_admin_tasks_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO admin_tasks
                (task_key, task_text, start_date, reminder_time, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                MOLAR_MASS_TASK_KEY,
                MOLAR_MASS_TASK_TEXT,
                MOLAR_MASS_TASK_DATE.isoformat(),
                MOLAR_MASS_TASK_TIME,
                datetime.now(bot.TIMEZONE).isoformat(),
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
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    seed_molar_mass_task()
    live24.main()
