import sqlite3
from datetime import date, datetime

import run_bot_live65

live65 = run_bot_live65
live64 = live65.live64
live63 = live65.live63
live61 = live65.live61
live60 = live65.live60
live59 = live65.live59
live56 = live65.live56
live55 = live65.live55
live54 = live65.live54
live52 = live65.live52
live51 = live65.live51
live50 = live65.live50
live49 = live65.live49
live48 = live65.live48
live46 = live65.live46
live44 = live65.live44
live43 = live65.live43
live41 = live65.live41
live39 = live65.live39
live37 = live65.live37
live35 = live65.live35
live34 = live65.live34
live31 = live65.live31
live24 = live65.live24
live17 = live65.live17
bot = live65.bot

ZLATA_ACCOUNTING_TASK_KEY = "add-zlata-to-accounting-2026-09-12"
ZLATA_ACCOUNTING_TASK_TEXT = "Внести Злату в бухгалтерию"
ZLATA_ACCOUNTING_TASK_START_DATE = date(2026, 9, 12)
ZLATA_ACCOUNTING_TASK_TIME = "10:00"


def seed_zlata_accounting_task():
    live35.ensure_admin_tasks_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO admin_tasks
                (task_key, task_text, start_date, reminder_time, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ZLATA_ACCOUNTING_TASK_KEY,
                ZLATA_ACCOUNTING_TASK_TEXT,
                ZLATA_ACCOUNTING_TASK_START_DATE.isoformat(),
                ZLATA_ACCOUNTING_TASK_TIME,
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


if __name__ == "__main__":
    live59.ensure_coreapp_webhook_audit_table()
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
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    seed_zlata_accounting_task()
    live56.log_probnik_cabinet_audit()
    print("Zlata accounting task seeded for 12.09.2026 10:00", flush=True)
    print("New student registration button ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
