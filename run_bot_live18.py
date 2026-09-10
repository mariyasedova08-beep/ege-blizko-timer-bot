import sqlite3
from datetime import date, datetime

import run_bot_live17

live17 = run_bot_live17
live15 = live17.live15
live7 = live17.live7
bot = live17.bot

ACID_REMINDER_END = date(2027, 5, 29)
ACID_REMINDER_TIME = "14:00"


def ensure_acid_reminder_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS acid_saturday_reminder (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                last_sent TEXT
            )
            """
        )
        conn.execute("INSERT OR IGNORE INTO acid_saturday_reminder (id, last_sent) VALUES (1, NULL)")
        conn.commit()


def get_last_acid_reminder_date():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute("SELECT last_sent FROM acid_saturday_reminder WHERE id = 1").fetchone()
    return row[0] if row else None


def set_last_acid_reminder_date(day_text):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("UPDATE acid_saturday_reminder SET last_sent = ? WHERE id = 1", (day_text,))
        conn.commit()


async def send_acid_saturday_reminder(context):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False

    me = await context.bot.get_me()
    keyboard = live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton(
            "🧪 Повторить кислоты",
            url=f"https://t.me/{me.username}?start=acid",
        )]
    ])

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "🧪 <b>Суббота — время повторить кислоты</b> 💗\n\n"
            "10 вопросов займут всего несколько минут.\n"
            "Особое внимание — кислотам и кислотным остаткам <b>хлора и фосфора</b>.\n\n"
            "ЕГЭ близко — лучше повторять понемногу, но регулярно."
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return True


_original_repeating_tick = live7.friday_trivial_tick


async def combined_weekly_trainer_tick(context):
    # Сохраняем уже существующее пятничное напоминание о тривиальных названиях.
    await _original_repeating_tick(context)

    now = datetime.now(bot.TIMEZONE)
    today = now.date()

    # Каждую субботу в 14:00 по Москве, последняя отправка — 29.05.2027.
    if now.weekday() != 5:
        return
    if now.strftime("%H:%M") != ACID_REMINDER_TIME:
        return
    if today > ACID_REMINDER_END:
        return

    day_text = today.isoformat()
    if get_last_acid_reminder_date() == day_text:
        return

    if await send_acid_saturday_reminder(context):
        set_last_acid_reminder_date(day_text)


live7.friday_trivial_tick = combined_weekly_trainer_tick


if __name__ == "__main__":
    live17.ensure_acid_tables()
    ensure_acid_reminder_table()
    live15.main()
