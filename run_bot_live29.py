import run_bot_live28

# Напоминание тем, кто не ответил на опрос, теперь отправляется
# за 1,5 часа до урока или пробника.
run_bot_live28.REMIND_BEFORE_HOURS = 1.5


if __name__ == "__main__":
    run_bot_live28.live25.ensure_lesson_day_before_table()
    run_bot_live28.live24.ensure_probnik_poll_tables()
    run_bot_live28.ensure_unanswered_reminder_tables()
    run_bot_live28.live24.main()
