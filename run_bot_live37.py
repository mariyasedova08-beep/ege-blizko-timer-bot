import sqlite3

import run_bot_live36

live36 = run_bot_live36
live35 = live36.live35
live34 = live36.live34
live31 = live36.live31
live24 = live36.live24
live17 = live36.live17
bot = live36.bot

TASK_TEXT = "Добавь родителей в бот"


def update_monday_task_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE admin_tasks
            SET task_text = ?
            WHERE task_key = ? AND completed_at IS NULL
            """,
            (TASK_TEXT, live35.MONDAY_TASK_KEY),
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
    update_monday_task_text()
    live24.main()
