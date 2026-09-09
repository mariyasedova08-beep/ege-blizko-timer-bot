import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from phrases import DAILY_PHRASES

# Дата ЕГЭ по химии
EXAM_DATE = date(2027, 6, 1)

# 264 уникальные фразы идут с 10.09.2026 по 31.05.2027 включительно
PHRASE_START_DATE = date(2026, 9, 10)

# Часовой пояс
TIMEZONE = ZoneInfo("Europe/Moscow")


def today_moscow():
    return datetime.now(TIMEZONE).date()


def days_left():
    return (EXAM_DATE - today_moscow()).days


def get_daily_phrase(for_date=None):
    current_date = for_date or today_moscow()
    index = (current_date - PHRASE_START_DATE).days

    if 0 <= index < len(DAILY_PHRASES):
        return DAILY_PHRASES[index]

    return "Каждый день — ещё один маленький шаг к сотке."


def get_countdown_text():
    days = days_left()

    if days > 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            f"До ЕГЭ по химии осталось\n"
            f"<b>{days} дней</b> 💗\n\n"
            f"{get_daily_phrase()}"
        )

    if days == 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "До ЕГЭ по химии остался\n"
            "<b>1 день</b> 💗\n\n"
            f"{get_daily_phrase()}"
        )

    if days == 0:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "<b>ЕГЭ ПО ХИМИИИ — СЕГОДНЯ!</b> 💗\n\n"
            "Вы уже сделали огромную работу. "
            "Теперь спокойно показываем всё, что умеем."
        )

    return (
        "🧪 <b>ЕГЭ близко</b>\n\n"
        "ЕГЭ по химии уже позади 💗"
    )


def get_homework_reminder_text():
    return (
        "📝 <b>Время домашки</b> 💗\n\n"
        "Не откладываем на потом — проверьте, что сегодняшняя домашняя работа сделана и отправлена в CoreApp.\n\n"
        "Спокойно, системно и по чуть-чуть каждый день — так и приходят к сильному результату 🧪"
    )


def get_target_thread_id():
    thread_id = os.getenv("MESSAGE_THREAD_ID")
    return int(thread_id) if thread_id else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я таймер курса «ЕГЭ близко» 🧪\n\n"
        "Мои команды:\n"
        "/ege — сколько дней до ЕГЭ\n"
        "/weeks — сколько недель до ЕГЭ\n"
        "/chatid — показать ID этого чата\n"
        "/threadid — показать ID текущей темы\n"
        "/test — отправить тестовый отсчёт в группу курса"
    )


async def ege(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_countdown_text(),
        parse_mode="HTML"
    )


async def weeks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = days_left()

    if days <= 0:
        await update.message.reply_text("ЕГЭ уже наступил 🧪")
        return

    weeks_count = days // 7
    remainder = days % 7

    await update.message.reply_text(
        "🧪 <b>ЕГЭ близко</b>\n\n"
        f"До ЕГЭ осталось примерно\n"
        f"<b>{weeks_count} недель и {remainder} дней</b> 💗",
        parse_mode="HTML"
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"ID этого чата:\n<code>{update.effective_chat.id}</code>",
        parse_mode="HTML"
    )


async def threadid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_thread_id = update.effective_message.message_thread_id

    if current_thread_id is None:
        await update.message.reply_text(
            "У этого сообщения нет ID темы. Отправьте /threadid внутри нужной темы форума."
        )
        return

    await update.message.reply_text(
        f"ID этой темы:\n<code>{current_thread_id}</code>",
        parse_mode="HTML"
    )


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        await update.message.reply_text("CHAT_ID пока не настроен.")
        return

    target_chat_id = int(chat_id)
    target_thread_id = get_target_thread_id()

    await context.bot.send_message(
        chat_id=target_chat_id,
        message_thread_id=target_thread_id,
        text=(
            "🧪 <b>ТЕСТ ТАЙМЕРА</b>\n\n"
            + get_countdown_text()
        ),
        parse_mode="HTML"
    )

    if update.effective_chat.id != target_chat_id:
        await update.message.reply_text(
            "✅ Тестовое сообщение отправлено в группу курса."
        )


async def daily_countdown(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=get_target_thread_id(),
        text=get_countdown_text(),
        parse_mode="HTML"
    )


async def daily_homework_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=get_target_thread_id(),
        text=get_homework_reminder_text(),
        parse_mode="HTML"
    )


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ege", ege))
    application.add_handler(CommandHandler("weeks", weeks))
    application.add_handler(CommandHandler("chatid", chatid))
    application.add_handler(CommandHandler("threadid", threadid))
    application.add_handler(CommandHandler("test", test))

    # Ежедневное сообщение в 09:00 по Москве
    application.job_queue.run_daily(
        daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(
            tzinfo=TIMEZONE
        ),
    )

    # Напоминание о домашней работе: воскресенье, вторник и суббота в 19:00 по Москве
    # В python-telegram-bot: 0 = воскресенье, 2 = вторник, 6 = суббота
    application.job_queue.run_daily(
        daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(
            tzinfo=TIMEZONE
        ),
        days=(0, 2, 6),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
