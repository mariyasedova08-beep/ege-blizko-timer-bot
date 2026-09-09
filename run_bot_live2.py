from datetime import datetime

import run_bot_live

run_bot = run_bot_live.run_bot
bot = run_bot.bot


def save_zoom_link(url):
    run_bot.save_asset("probnik_zoom", url)


def get_zoom_link():
    return run_bot.get_asset("probnik_zoom")


def saturday_text(number, zoom_url):
    return (
        f"💗 <b>Пробник №{number} — сегодня</b>\n\n"
        "В <b>10:00</b> начинаем.\n"
        "Пожалуйста, подключайтесь заранее.\n\n"
        "🎥 <b>Камеры обязательно включены.</b>\n\n"
        f"Zoom:\n{zoom_url}"
    )


async def set_probnik_zoom(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Отправьте эту команду мне в личном чате.")
        return
    if not context.args:
        await update.message.reply_text(
            "Отправьте команду так:\n/setprobnikzoom https://ваша-ссылка-zoom"
        )
        return

    url = context.args[0].strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        await update.message.reply_text("Похоже, это не ссылка. Нужна ссылка, начинающаяся с https://")
        return

    save_zoom_link(url)
    await update.message.reply_text("✅ Ссылка Zoom для пробников сохранена.")


async def send_probnik_saturday_reminder(context, probnik_date):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False, "CHAT_ID пока не настроен."

    zoom_url = get_zoom_link()
    if not zoom_url:
        return False, "Сначала сохраните ссылку Zoom командой /setprobnikzoom."

    number = run_bot.probnik_number(probnik_date)
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=saturday_text(number, zoom_url),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return True, None


async def probnik_saturday_reminder(context):
    today = bot.today_moscow()
    if today in run_bot.PROBNIK_DATES:
        await send_probnik_saturday_reminder(context, today)


async def test_probnik_saturday(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return

    target = run_bot.upcoming_probnik()
    ok, error = await send_probnik_saturday_reminder(context, target)
    if ok:
        await update.message.reply_text("✅ Тест субботнего напоминания отправлен в группу курса.")
    else:
        await update.message.reply_text(error)


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
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
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", test_probnik_saturday))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
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

    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(1, 3),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 6),
    )

    application.job_queue.run_daily(
        run_bot.probnik_daily_reminder,
        time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        probnik_saturday_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(6,),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
