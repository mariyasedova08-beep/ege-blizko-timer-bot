"""Личная кампания тренажёра «Свойства оксидов» 01–07.10.2026.

Каждый день 01–07.10 в 16:00 МСК — личное напоминание активным ученикам.
Доставка идемпотентна: после рестарта одно и то же сообщение повторно не уйдёт.
"""
import sqlite3
from datetime import date, datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import oxide_properties_trainer

bot = oxide_properties_trainer.bot
live7 = oxide_properties_trainer.live7

DM_DATES = {
    date(2026, 10, 1),
    date(2026, 10, 2),
    date(2026, 10, 3),
    date(2026, 10, 4),
    date(2026, 10, 5),
    date(2026, 10, 6),
    date(2026, 10, 7),
}
DM_TIME = time(16, 0)
DM_END = time(17, 0)


def ensure_campaign_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oxide_properties_campaign_deliveries (
                day_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(day_key,telegram_user_id)
            )
            """
        )
        conn.commit()


def _sent(day_key, telegram_user_id):
    ensure_campaign_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM oxide_properties_campaign_deliveries
                WHERE day_key=? AND telegram_user_id=?
                LIMIT 1
                """,
                (str(day_key), int(telegram_user_id)),
            ).fetchone()
        )


def _mark_sent(day_key, telegram_user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO oxide_properties_campaign_deliveries(
                day_key,telegram_user_id,sent_at
            ) VALUES(?,?,?)
            """,
            (
                str(day_key),
                int(telegram_user_id),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


def _student_recipients():
    """Активные ученики с привязанным Telegram, без дублей аккаунтов."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                coalesce(
                    nullif(display_name,''),
                    nullif(user_name,''),
                    user_email,
                    'Ученик'
                ),
                telegram_user_id
            FROM students
            WHERE active=1 AND telegram_user_id IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    result = []
    seen = set()
    for name, telegram_id in rows:
        uid = int(telegram_id)
        if uid in seen:
            continue
        seen.add(uid)
        first_name = (
            str(name or "").strip().split()[0]
            if str(name or "").strip()
            else ""
        )
        result.append((uid, first_name))
    return result


async def _markup(context):
    me = await context.bot.get_me()
    if not me.username:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🧪 Открыть «Свойства оксидов»",
                url=f"https://t.me/{me.username}?start=oxideproperties",
            )
        ]]
    )


def _text(day, first_name):
    hello = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    bodies = {
        date(2026, 10, 1): (
            "Сегодня открываем тренажёр <b>«Свойства оксидов»</b> 🧪\n\n"
            "Внутри 80 вопросов. В каждом задании — один оксид и варианты по три вещества. "
            "Начни с 10 вопросов."
        ),
        date(2026, 10, 2): (
            "Повторяем свойства оксидов 🧪\n\n"
            "Сегодня пройди ещё 10–20 вопросов. Один и тот же оксид встречается несколько раз "
            "с разными реагентами — так реакции запоминаются намного лучше."
        ),
        date(2026, 10, 3): (
            "Мини-тренировка на сегодня 💗\n\n"
            "Открой <b>«Свойства оксидов»</b> и проверь себя ещё на одном подходе. "
            "Не угадывай: мысленно проверяй реакцию каждого из трёх веществ."
        ),
        date(2026, 10, 4): (
            "Сегодня можно сделать короткое повторение 🧪\n\n"
            "Если уже проходил(а) тренажёр, зайди в <b>«Мои ошибки»</b>. "
            "Если ещё не начинал(а) — хватит даже 10 вопросов."
        ),
        date(2026, 10, 5): (
            "Новая неделя — ещё один подход к оксидам 💗\n\n"
            "Выбери 20 вопросов и обрати внимание на амфотерные и кислотные оксиды."
        ),
        date(2026, 10, 6): (
            "Закрепляем реакции оксидов 🧪\n\n"
            "Сегодня попробуй режим на 40 вопросов или закрой накопившиеся ошибки."
        ),
        date(2026, 10, 7): (
            "Финальное напоминание по тренажёру на этой неделе 💗\n\n"
            "Проверь <b>«Мои ошибки»</b> и добей те оксиды, на которых ещё путаются реагенты."
        ),
    }
    return hello + "\n\n" + bodies[day]


async def send_personal_reminders(context, day):
    markup = await _markup(context)
    sent = failed = skipped = 0
    day_key = day.isoformat()

    for telegram_id, first_name in _student_recipients():
        if _sent(day_key, telegram_id):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=_text(day, first_name),
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            failed += 1
            print(
                f"OXIDE_PROPERTIES_CAMPAIGN dm_failed "
                f"day={day_key} user={telegram_id} "
                f"error={type(exc).__name__}",
                flush=True,
            )
            continue

        _mark_sent(day_key, telegram_id)
        sent += 1

    print(
        f"OXIDE_PROPERTIES_CAMPAIGN dm day={day_key} "
        f"sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


async def campaign_tick(context):
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    current = now.time().replace(tzinfo=None)

    if today in DM_DATES and DM_TIME <= current < DM_END:
        await send_personal_reminders(context, today)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_oxide_properties_campaign(context):
    try:
        await _previous_tick(context)
    finally:
        await campaign_tick(context)


live7.friday_trivial_tick = combined_tick_with_oxide_properties_campaign
ensure_campaign_table()
print(
    "Oxide properties campaign ready: dm=2026-10-01..07 16:00 Moscow",
    flush=True,
)
