from datetime import time

import run_bot_live46

live46 = run_bot_live46
live45 = live46.live45
live44 = live46.live44
live43 = live46.live43
live41 = live46.live41
live39 = live46.live39
live37 = live46.live37
live35 = live46.live35
live34 = live46.live34
live31 = live46.live31
live24 = live46.live24
live17 = live46.live17

# Ежемесячная автоматическая рассылка — в 20:00 по Москве.
live46.MONTHLY_REPORT_AFTER = time(20, 0)


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
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live24.main()
