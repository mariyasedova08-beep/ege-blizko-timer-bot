import os
from datetime import datetime, date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Дата ЕГЭ по химии
EXAM_DATE = date(2027, 6, 1)

# Часовой пояс
TIMEZONE = ZoneInfo("Europe/Moscow")


def days_left():
    today = datetime.now(TIMEZONE).date()
    return (EXAM_DATE - today).days


def get_countdown_text():
    days = days_left()

    if days > 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            f"До ЕГЭ по химии осталось\n"
            f"<b>{days} дней</b> 💗\n\n"
            "Каждый день — ещё один маленький шаг к сотке."
        )

    if days == 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "До ЕГЭ по химии остался\n"
            "<b>1 день</b> 💗\n\n"
            "Сегодня ничего не пытаемся выучить заново. "
            "Повторяем главное и бережём себя."
        )

    if days == 0:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "<b>ЕГЭ ПО ХИМИИ — СЕГОДНЯ!</b> 💗\n\n"
            "Вы уже сделали огромную работу. "
            "Теперь спокойно показываем всё, что умеем."
        )

    return (
        "🧪 <b>ЕГЭ близко</b>\n\n"
        "ЕГЭ по химии уже позади 💗"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я таймер курса «ЕГЭ близко» 🧪\n\n"
        "Мои команды:\n"
        "/ege — сколько дней до ЕГЭ\n"
        "/weeks — сколько недель до ЕГЭ\n"
        "/chatid — показать ID этого чата"
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


async def daily_countdown(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        text=get_countdown_text(),
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

    # Ежедневное сообщение в 09:00 по Москве
    application.job_queue.run_daily(
        daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(
            tzinfo=TIMEZONE
        ),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
