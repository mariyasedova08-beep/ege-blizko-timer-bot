from datetime import date, datetime, timedelta
import sqlite3

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


# Пробники: последняя суббота каждого месяца с октября 2026 по май 2027.
PROBNIK_DATES = (
    date(2026, 10, 31),
    date(2026, 11, 28),
    date(2026, 12, 26),
    date(2027, 1, 30),
    date(2027, 2, 27),
    date(2027, 3, 27),
    date(2027, 4, 24),
    date(2027, 5, 29),
)


def ensure_probnik_assets_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_assets (
                asset_key TEXT PRIMARY KEY,
                telegram_file_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_asset(asset_key, telegram_file_id):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bot_assets (asset_key, telegram_file_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(asset_key) DO UPDATE SET
                telegram_file_id = excluded.telegram_file_id,
                updated_at = excluded.updated_at
            """,
            (asset_key, telegram_file_id, now),
        )
        conn.commit()


def get_asset(asset_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT telegram_file_id FROM bot_assets WHERE asset_key = ? LIMIT 1",
            (asset_key,),
        ).fetchone()
    return row[0] if row else None


def probnik_number(probnik_date):
    return PROBNIK_DATES.index(probnik_date) + 1


def upcoming_probnik(from_date=None):
    current_date = from_date or bot.today_moscow()
    for probnik_date in PROBNIK_DATES:
        if probnik_date >= current_date:
            return probnik_date
    return PROBNIK_DATES[-1]


def thursday_text(number):
    return (
        f"📝 <b>Пробник №{number} — уже в эту субботу 💗</b>\n\n"
        "Начинаем в <b>10:00</b>.\n"
        "<b>Присутствие обязательно.</b>\n\n"
        "Ниже отправляю бланк ответов — подготовьте его заранее."
    )


def friday_text(number):
    return (
        f"💗 <b>Напоминаю: завтра пробник №{number}</b>\n\n"
        "Начинаем в <b>10:00</b>.\n"
        "<b>Присутствие обязательно.</b>\n\n"
        "Проверьте, что бланк ответов у вас готов 📝"
    )


async def send_probnik_bundle(context, probnik_date, weekday_kind):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False, "CHAT_ID пока не настроен."

    card_file_id = get_asset("probnik_card")
    blank_file_id = get_asset("probnik_blank")
    number = probnik_number(probnik_date)

    if not card_file_id:
        return False, "Сначала нужно сохранить карточку пробника командой /setprobnikcard."
    if weekday_kind == "thursday" and not blank_file_id:
        return False, "Сначала нужно сохранить бланк командой /setprobnikblank."

    target_chat_id = int(chat_id)
    thread_id = bot.get_target_thread_id()

    await context.bot.send_photo(
        chat_id=target_chat_id,
        message_thread_id=thread_id,
        photo=card_file_id,
    )

    if weekday_kind == "thursday":
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            text=thursday_text(number),
            parse_mode="HTML",
        )
        await context.bot.send_document(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            document=blank_file_id,
            caption="Бланк ответов для пробника 💗",
        )
    else:
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            text=friday_text(number),
            parse_mode="HTML",
        )

    return True, None


async def probnik_daily_reminder(context):
    today = bot.today_moscow()
    for probnik_date in PROBNIK_DATES:
        if today == probnik_date - timedelta(days=2):
            await send_probnik_bundle(context, probnik_date, "thursday")
            return
        if today == probnik_date - timedelta(days=1):
            await send_probnik_bundle(context, probnik_date, "friday")
            return


async def set_probnik_card(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Отправьте эту команду мне в личном чате.")
        return
    context.user_data["awaiting_probnik_asset"] = "probnik_card"
    await update.message.reply_text("Теперь отправьте мне карточку «Пробник уже в эту субботу» как фото 💗")


async def set_probnik_blank(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Отправьте эту команду мне в личном чате.")
        return
    context.user_data["awaiting_probnik_asset"] = "probnik_blank"
    await update.message.reply_text("Теперь отправьте PDF с бланком ответов.")


async def save_probnik_asset_from_message(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    asset_key = context.user_data.get("awaiting_probnik_asset")
    if not asset_key:
        return

    if asset_key == "probnik_card":
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
            file_id = update.message.document.file_id
        else:
            await update.message.reply_text("Нужно отправить именно картинку карточки.")
            return
        save_asset("probnik_card", file_id)
        context.user_data.pop("awaiting_probnik_asset", None)
        await update.message.reply_text("✅ Карточка пробника сохранена.")
        return

    if asset_key == "probnik_blank":
        document = update.message.document
        if not document or document.mime_type != "application/pdf":
            await update.message.reply_text("Нужно отправить PDF-файл с бланком ответов.")
            return
        save_asset("probnik_blank", document.file_id)
        context.user_data.pop("awaiting_probnik_asset", None)
        await update.message.reply_text("✅ Бланк ответов сохранён.")


async def test_probnik_thursday(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    target = upcoming_probnik()
    ok, error = await send_probnik_bundle(context, target, "thursday")
    if ok:
        await update.message.reply_text("✅ Тест четвергового напоминания отправлен в группу курса.")
    else:
        await update.message.reply_text(error)


async def test_probnik_friday(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    target = upcoming_probnik()
    ok, error = await send_probnik_bundle(context, target, "friday")
    if ok:
        await update.message.reply_text("✅ Тест пятничного напоминания отправлен в группу курса.")
    else:
        await update.message.reply_text(error)


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    ensure_probnik_assets_table()
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
    application.add_handler(bot.CommandHandler("setprobnikcard", set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", set_probnik_blank))
    application.add_handler(bot.CommandHandler("testprobnikthu", test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", test_probnik_friday))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            save_probnik_asset_from_message,
        )
    )
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

    # Каждый день в 10:00 проверяем, не четверг/пятница ли перед одним из 8 пробников.
    application.job_queue.run_daily(
        probnik_daily_reminder,
        time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
