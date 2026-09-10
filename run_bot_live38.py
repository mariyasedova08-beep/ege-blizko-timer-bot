import run_bot_live37

live37 = run_bot_live37
live36 = live37.live36
live35 = live36.live35
live34 = live36.live34
live31 = live36.live31
live24 = live36.live24
live17 = live36.live17
run_bot = live34.run_bot

# Fix for the attention-zone trainer metric: older run_bot does not expose
# COURSE_START_DATE, while the course start is the first lesson date.
if not hasattr(run_bot, "COURSE_START_DATE"):
    run_bot.COURSE_START_DATE = min(run_bot.COURSE_LESSON_DATES)


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
    live24.main()
