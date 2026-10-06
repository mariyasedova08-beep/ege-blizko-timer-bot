"""Личная кампания тренажёра «Свойства гидроксидов» 06–12.10.2026.

Каждый день 06–12.10 в 16:00 МСК — личное напоминание всем активным ученикам.
Доставка идемпотентна: одно и то же сообщение после рестартов повторно не уходит.
"""
import sqlite3
from datetime import date, datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import hydroxides_trainer

bot = hydroxides_trainer.bot
live7 = hydroxides_trainer.live7

DM_DATES = {
    date(2026, 10, 6),
    date(2026, 10, 7),
    date(2026, 10, 8),
    date(2026, 10, 9),
    date(2026, 10, 10),
    date(2026, 10, 11),
    date(2026, 10, 12),
}
DM_TIME = time(16, 0)
DM_END = time(17, 0)


def ensure_campaign_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hydroxides_campaign_deliveries (
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
                SELECT 1 FROM hydroxides_campaign_deliveries
                WHERE day_key=? AND telegram_user_id=? LIMIT 1
                """,
                (str(day_key), int(telegram_user_id)),
            ).fetchone()
        )


def _mark_sent(day_key, telegram_user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO hydroxides_campaign_deliveries(
                day_key,telegram_user_id,sent_at
            ) VALUES(?,?,?)
            """,
            (str(day_key), int(telegram_user_id), datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


def _student_recipients():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
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
        first_name = str(name or "").strip().split()[0] if str(name or "").strip() else ""
        result.append((uid, first_name))
    return result


async def _markup(context):
    username = str(getattr(context.bot, "username", "") or "").strip()
    if not username:
        me = await context.bot.get_me()
        username = str(me.username or "").strip()
    if not username:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🌸 Открыть «Свойства гидроксидов»",
                url=f"https://t.me/{username}?start=hydroxides",
            )
        ]]
    )


def _text(day, first_name):
    hello = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    bodies = {
        date(2026, 10, 6): (
            "У нас новый тренажёр — <b>«Свойства гидроксидов»</b> 🌸\n\n"
            "Внутри 100 вопросов. Начни сегодня хотя бы с 10: щёлочи, основания, "
            "амфотерность, осадки и условия реакций."
        ),
        date(2026, 10, 7): (
            "Продолжаем закреплять <b>свойства гидроксидов</b> 🌸\n\n"
            "Сегодня выбери 10–20 вопросов и особенно следи за тем, где амфотерный "
            "гидроксид ведёт себя как основание, а где — как кислота."
        ),
        date(2026, 10, 8): (
            "Короткая практика на сегодня 💗\n\n"
            "Открой <b>«Свойства гидроксидов»</b> и потренируй реакции щелочей "
            "с кислотными оксидами и солями."
        ),
        date(2026, 10, 9): (
            "Сегодня фокус на условиях реакции 🌸\n\n"
            "Раствор или сплав? Кто в избытке? Именно на этих деталях чаще всего "
            "теряются продукты. Сделай ещё один подход."
        ),
        date(2026, 10, 10): (
            "Выходные — хороший момент добить ошибки 💗\n\n"
            "Если уже проходил(а) тренажёр, открой <b>«Мои ошибки»</b>. "
            "Если нет — начни с 10 вопросов."
        ),
        date(2026, 10, 11): (
            "Ещё один короткий подход к гидроксидам 🌸\n\n"
            "Проверь цвета осадков, амфотерные гидроксиды и разложение при нагревании."
        ),
        date(2026, 10, 12): (
            "Финальное напоминание по <b>«Свойствам гидроксидов»</b> 💗\n\n"
            "Сегодня закрой «Мои ошибки» или попробуй большой режим. "
            "Наша цель — не угадать, а начать узнавать реакции автоматически."
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
                f"HYDROXIDES_CAMPAIGN dm_failed day={day_key} "
                f"user={telegram_id} error={type(exc).__name__}",
                flush=True,
            )
            continue
        _mark_sent(day_key, telegram_id)
        sent += 1

    print(
        f"HYDROXIDES_CAMPAIGN dm day={day_key} "
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


async def combined_tick_with_hydroxides_campaign(context):
    try:
        await _previous_tick(context)
    finally:
        await campaign_tick(context)


live7.friday_trivial_tick = combined_tick_with_hydroxides_campaign
ensure_campaign_table()
print(
    "Hydroxides campaign ready: dm=2026-10-06..12 16:00 Moscow",
    flush=True,
)
