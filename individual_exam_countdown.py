"""Personal EGE countdown for linked individual students only."""

import sqlite3
from datetime import datetime, time

from telegram import ReplyKeyboardMarkup

import run_bot_live90 as live90

bot = live90.bot
live7 = live90.live79.live7
live67 = live90.live79.live67

TIMER_BUTTON = "⏰ До ЕГЭ"
INDIVIDUAL_KEYBOARD = ReplyKeyboardMarkup(
    [["🧪 Тренажёры", TIMER_BUTTON]], resize_keyboard=True
)
_INSTALLED = False


def countdown_text():
    """The date and daily phrase are shared; course lessons are not."""
    days = bot.days_left()
    header = "🧪 <b>ЕГЭ БЛИЗКО</b>\n\n"
    if days > 1:
        return header + f"До ЕГЭ по химии осталось\n<b>{days} дней</b> 💗\n\n" + bot.get_daily_phrase()
    if days == 1:
        return header + "До ЕГЭ по химии остался\n<b>1 день</b> 💗\n\n" + bot.get_daily_phrase()
    if days == 0:
        return header + "<b>ЕГЭ ПО ХИМИИ — СЕГОДНЯ!</b> 💗\n\nВы уже сделали огромную работу. Теперь спокойно показываем всё, что умеем."
    return header + "ЕГЭ по химии уже позади 💗"


def ensure_delivery_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS individual_exam_countdown_deliveries (
                day_key TEXT NOT NULL,
                student_id INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (day_key, student_id)
            )
        """)


async def daily_tick(context):
    now = datetime.now(bot.TIMEZONE)
    # The shared repeating scheduler runs every 30 seconds. A short window
    # avoids sending a morning countdown late after a restart.
    if not (time(9, 0) <= now.time() < time(9, 10)):
        return
    day_key = now.date().isoformat()
    for student_id, _name, telegram_id, _username in live67._individual_rows():
        if telegram_id is None:
            continue
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            sent = conn.execute("""
                SELECT 1 FROM individual_exam_countdown_deliveries
                WHERE day_key = ? AND student_id = ?
            """, (day_key, student_id)).fetchone()
        if sent:
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id), text=countdown_text(), parse_mode="HTML",
            )
        except Exception as exc:
            print(f"Individual EGE countdown failed student={student_id}: {exc}", flush=True)
            continue
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO individual_exam_countdown_deliveries
                    (day_key, student_id, telegram_user_id, sent_at)
                VALUES (?, ?, ?, ?)
            """, (day_key, student_id, int(telegram_id), now.isoformat()))
        print(f"Individual EGE countdown sent student={student_id}", flush=True)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_delivery_table()
    live67.INDIVIDUAL_KEYBOARD = INDIVIDUAL_KEYBOARD

    previous_tick = live7.friday_trivial_tick

    async def combined_tick(context):
        try:
            await previous_tick(context)
        finally:
            await daily_tick(context)

    live7.friday_trivial_tick = combined_tick

    previous_text_router = live7.student_text_router

    async def text_router(update, context):
        if (update.effective_chat.type == "private" and update.message
                and update.message.text and update.message.text.strip() == TIMER_BUTTON
                and live67._individual_by_telegram(update.effective_user.id)):
            await update.message.reply_text(countdown_text(), parse_mode="HTML")
            return
        return await previous_text_router(update, context)

    live7.student_text_router = text_router

    previous_start_router = live7.start_router

    async def start_router(update, context):
        if (update.effective_chat.type == "private" and not context.args
                and live67._individual_by_telegram(update.effective_user.id)):
            await update.message.reply_text(
                "Тренажёры и таймер до ЕГЭ доступны по кнопкам ниже 💗",
                reply_markup=INDIVIDUAL_KEYBOARD,
            )
            return
        return await previous_start_router(update, context)

    live7.start_router = start_router

    previous_ege = bot.ege

    async def ege(update, context):
        if (update.effective_chat.type == "private"
                and live67._individual_by_telegram(update.effective_user.id)):
            await update.message.reply_text(countdown_text(), parse_mode="HTML")
            return
        return await previous_ege(update, context)

    bot.ege = ege

    previous_progress = bot.progress

    async def progress(update, context):
        if (update.effective_chat.type == "private"
                and live67._individual_by_telegram(update.effective_user.id)):
            await update.message.reply_text(
                "Индивидуальные занятия не привязаны к расписанию группового курса. "
                "Сколько дней до ЕГЭ — по кнопке «⏰ До ЕГЭ»."
            )
            return
        return await previous_progress(update, context)

    bot.progress = progress
    _INSTALLED = True
    print("Individual EGE countdown ready: daily 09:00 Moscow", flush=True)
