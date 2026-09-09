from datetime import date, datetime, timedelta

import bot

# Расписание курса: понедельник, среда, воскресенье.
# Единственное исключение: урок 08.11.2026 переносится на субботу 07.11.2026.
bot.LESSON_WEEKDAYS = {0, 2, 6}
SPECIAL_LESSON_DATES = {date(2026, 11, 7)}
SKIPPED_LESSON_DATES = {date(2026, 11, 8)}


def is_planned_lesson_date(current_date):
    is_regular = (
        current_date.weekday() in bot.LESSON_WEEKDAYS
        and current_date not in SKIPPED_LESSON_DATES
    )
    return is_regular or current_date in SPECIAL_LESSON_DATES


def build_course_lesson_dates():
    dates = []
    cursor = bot.COURSE_START_DATE
    while len(dates) < bot.TOTAL_LESSONS:
        if is_planned_lesson_date(cursor):
            dates.append(cursor)
        cursor += timedelta(days=1)
    return tuple(dates)


COURSE_LESSON_DATES = build_course_lesson_dates()
COURSE_LESSON_DATE_SET = set(COURSE_LESSON_DATES)


def get_course_lesson_number(for_date=None):
    current_date = for_date or bot.today_moscow()
    if current_date < bot.COURSE_START_DATE:
        return 0
    return sum(1 for lesson_date in COURSE_LESSON_DATES if lesson_date <= current_date)


def get_course_progress_text(for_date=None):
    current_date = for_date or bot.today_moscow()
    lesson_number = get_course_lesson_number(current_date)
    progress = lesson_number / bot.TOTAL_LESSONS if bot.TOTAL_LESSONS else 0
    percent = progress * 100

    if lesson_number == 0:
        filled = 0
    elif lesson_number >= bot.TOTAL_LESSONS:
        filled = bot.PROGRESS_SEGMENTS
    else:
        filled = max(1, round(progress * bot.PROGRESS_SEGMENTS))

    empty = bot.PROGRESS_SEGMENTS - filled
    bar = "🩷" * filled + "🤍" * empty
    percent_text = f"{percent:.1f}".replace(".", ",")

    lines = [
        "💗 <b>Прогресс курса</b>",
        bar,
        f"<b>{lesson_number} / {bot.TOTAL_LESSONS} уроков</b> · {percent_text}%",
    ]

    if current_date in COURSE_LESSON_DATE_SET:
        lines.append(f"Сегодня — урок №{lesson_number} 🧪")

    return "\n".join(lines)


bot.get_course_lesson_number = get_course_lesson_number
bot.get_course_progress_text = get_course_progress_text


LESSON_REMINDER_TEXT = "Начинаем через 30 минут 💗"


async def send_lesson_reminder(context):
    current_date = bot.today_moscow()
    if current_date not in COURSE_LESSON_DATE_SET:
        return

    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=LESSON_REMINDER_TEXT,
    )


async def test_lesson_reminder(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return

    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        await update.message.reply_text("CHAT_ID пока не настроен.")
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=LESSON_REMINDER_TEXT,
    )
    await update.message.reply_text("✅ Тестовое напоминание отправлено в группу курса.")


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", bot.start))
    application.add_handler(bot.CommandHandler("ege", bot.ege))
    application.add_handler(bot.CommandHandler("weeks", bot.weeks))
    application.add_handler(bot.CommandHandler("progress", bot.progress))
    application.add_handler(bot.CommandHandler("chatid", bot.chatid))
    application.add_handler(bot.CommandHandler("threadid", bot.threadid))
    application.add_handler(bot.CommandHandler("myid", bot.myid))
    application.add_handler(bot.CommandHandler("link", bot.link))
    application.add_handler(bot.CommandHandler("corestatus", bot.corestatus))
    application.add_handler(bot.CommandHandler("homeworkstatus", bot.homeworkstatus))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", test_lesson_reminder))
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))

    application.job_queue.run_daily(
        bot.daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        bot.daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 2, 6),
    )

    # Напоминание за 30 минут до урока:
    # понедельник и среда — 18:00, воскресенье — 09:30.
    # 08.11.2026 пропускаем, вместо него 07.11.2026 в 09:30.
    application.job_queue.run_daily(
        send_lesson_reminder,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(1, 3),
    )
    application.job_queue.run_daily(
        send_lesson_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 6),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
