"""Daily 11:00 reminder for Maria's 90-day Instagram return plan."""
import sqlite3
from datetime import datetime, time, timedelta

import run_bot_live90 as live90
import instagram_return_system as instagram

live7 = live90.live79.live7
bot = live90.bot

REMINDER_TIME = time(11, 0)
REMINDER_END = time(11, 10)
_INSTALLED = False


def ensure_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instagram_daily_reminders (
                day_key TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _already_sent(day_key):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM instagram_daily_reminders WHERE day_key = ? LIMIT 1",
                (str(day_key),),
            ).fetchone()
        )


def _mark_sent(day_key, now):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO instagram_daily_reminders (day_key, sent_at) VALUES (?, ?)",
            (str(day_key), now.isoformat()),
        )
        conn.commit()


async def instagram_daily_tick(context):
    now = datetime.now(bot.TIMEZONE)
    campaign_end = instagram.START_DATE + timedelta(days=instagram.TOTAL_DAYS)
    if now.date() < instagram.START_DATE or now.date() >= campaign_end:
        return
    if not (REMINDER_TIME <= now.time() < REMINDER_END):
        return

    day_key = now.date().isoformat()
    if _already_sent(day_key):
        return

    admin_id = bot.get_admin_id()
    if not admin_id:
        return

    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "⏰ <b>Instagram — задача на сегодня</b>\n\n"
                + instagram._main_text()
            ),
            parse_mode="HTML",
            reply_markup=instagram._main_markup(),
        )
    except Exception as exc:
        print(f"Instagram daily reminder failed: {exc}", flush=True)
        return

    _mark_sent(day_key, now)
    print(f"Instagram daily reminder sent: {day_key}", flush=True)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_table()
    previous_tick = live7.friday_trivial_tick

    async def combined_tick(context):
        try:
            await previous_tick(context)
        finally:
            await instagram_daily_tick(context)

    live7.friday_trivial_tick = combined_tick
    _INSTALLED = True
    print("Instagram daily reminder ready: every day 11:00", flush=True)
