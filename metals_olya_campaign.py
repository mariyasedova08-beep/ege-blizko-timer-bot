"""Personal metals reminders for Olya (10–14 October 2026, 17:00 Moscow).

Targets only the active individual student whose first name is Olya/Olga.
Delivery is idempotent per day, runs only in the 17:00–17:10 window, and includes the existing metals trainer link.
"""
import re
import sqlite3
from datetime import date, datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

bot = live90.bot
live7 = live90.live7

DM_DATES = {date(2026, 10, day) for day in range(10, 15)}
DM_TIME = time(17, 0)
DM_END = time(17, 10)


def ensure_campaign_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metals_olya_campaign_deliveries (
                day_key TEXT NOT NULL,
                individual_student_id INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (day_key, individual_student_id)
            )
            """
        )
        conn.commit()


def _recipients():
    try:
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            rows = conn.execute(
                """
                SELECT id, display_name, telegram_user_id
                FROM individual_students
                WHERE active = 1 AND telegram_user_id IS NOT NULL
                ORDER BY id
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return []

    result = []
    for student_id, display_name, telegram_id in rows:
        first = re.split(r"\s+", str(display_name or "").strip(), maxsplit=1)[0].lower()
        first = first.strip(".,!?;:()[]{}")
        if first in {"оля", "ольга"}:
            result.append((int(student_id), str(display_name or "Оля"), int(telegram_id)))
    return result


def _sent(day_key, student_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM metals_olya_campaign_deliveries
                WHERE day_key = ? AND individual_student_id = ?
                LIMIT 1
                """,
                (str(day_key), int(student_id)),
            ).fetchone()
        )


def _mark_sent(day_key, student_id, telegram_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO metals_olya_campaign_deliveries
                (day_key, individual_student_id, telegram_user_id, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(day_key),
                int(student_id),
                int(telegram_id),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


async def _markup(context):
    username = str(getattr(context.bot, "username", "") or "").strip()
    if not username:
        me = await context.bot.get_me()
        username = str(getattr(me, "username", "") or "").strip()
    if not username:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "⚙️ Открыть тренажёр «Металлы»",
                url=f"https://t.me/{username}?start=metals",
            )
        ]]
    )


def _text(display_name, day):
    first = str(display_name or "Оля").strip().split()[0] or "Оля"
    if first.lower() == "ольга":
        first = "Оля"
    hello = f"Привет, {first}! 💗"
    day_number = (day - date(2026, 10, 10)).days + 1
    return (
        f"{hello}\n\n"
        "⚙️ Сегодня тренируем <b>«Металлы»</b>.\n\n"
        f"День {day_number}/5: пройди хотя бы 10 вопросов — свойства металлов, "
        "ряд напряжений и реакции. Ошибки сохранятся для повторения.\n\n"
        "Открывай тренажёр по кнопке и играй в долгую 💗"
    )


async def send_personal_reminders(context, day):
    recipients = _recipients()
    print(
        f"METALS_OLYA_CAMPAIGN recipients={len(recipients)} day={day.isoformat()}",
        flush=True,
    )
    if not recipients:
        return

    markup = await _markup(context)
    sent = failed = skipped = 0
    day_key = day.isoformat()
    for student_id, display_name, telegram_id in recipients:
        if _sent(day_key, student_id):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=_text(display_name, day),
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            failed += 1
            print(
                "METALS_OLYA_CAMPAIGN dm_failed "
                f"day={day_key} student={student_id} error={type(exc).__name__}",
                flush=True,
            )
            continue
        _mark_sent(day_key, student_id, telegram_id)
        sent += 1

    print(
        "METALS_OLYA_CAMPAIGN "
        f"day={day_key} sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


async def campaign_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.date() not in DM_DATES:
        return
    if not (DM_TIME <= now.time().replace(tzinfo=None) < DM_END):
        return
    await send_personal_reminders(context, now.date())


_previous_tick = live7.friday_trivial_tick


async def combined_tick(context):
    try:
        await _previous_tick(context)
    finally:
        await campaign_tick(context)


live7.friday_trivial_tick = combined_tick
ensure_campaign_table()
print(
    "Metals Olya campaign ready: 2026-10-10..14 17:00 Moscow",
    flush=True,
)
