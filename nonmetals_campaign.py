"""Анонс и личная кампания тренажёра «Неметаллы» 24–27.09.2026.

24.09 в 10:00 МСК — один анонс в общий чат.
24–27.09 в 17:00 МСК — личные напоминания активным ученикам.
Доставки идемпотентны и не повторяются после рестартов.
"""
import sqlite3
from datetime import date, datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import nonmetals_trainer

bot = nonmetals_trainer.bot
live7 = nonmetals_trainer.live7

GROUP_DATE = date(2026, 9, 24)
GROUP_TIME = time(10, 0)
DM_DATES = {
    date(2026, 9, 24),
    date(2026, 9, 25),
    date(2026, 9, 26),
    date(2026, 9, 27),
}
DM_TIME = time(17, 0)


def ensure_campaign_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nonmetals_campaign_deliveries (
                kind TEXT NOT NULL,
                day_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL DEFAULT 0,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (kind, day_key, telegram_user_id)
            )
            """
        )
        conn.commit()


def _sent(kind, day_key, telegram_user_id=0):
    ensure_campaign_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1 FROM nonmetals_campaign_deliveries
                WHERE kind = ? AND day_key = ? AND telegram_user_id = ?
                LIMIT 1
                """,
                (str(kind), str(day_key), int(telegram_user_id)),
            ).fetchone()
        )


def _mark_sent(kind, day_key, telegram_user_id=0):
    ensure_campaign_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO nonmetals_campaign_deliveries
                (kind, day_key, telegram_user_id, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(kind),
                str(day_key),
                int(telegram_user_id),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


def _student_recipients():
    """Только активные ученики с привязанным Telegram, без дублей по аккаунту."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                telegram_user_id
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
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


async def _trainer_markup(context):
    me = await context.bot.get_me()
    if not me.username:
        return None
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "⚛️ Открыть тренажёр",
                url=f"https://t.me/{me.username}?start=nonmetals",
            )
        ]]
    )


async def send_group_announcement(context):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False
    markup = await _trainer_markup(context)
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "⚛️ <b>Новый тренажёр — «Неметаллы»</b> 💗\n\n"
            "Внутри <b>50 вопросов</b> по теме: строение и свойства неметаллов, "
            "степени окисления, ОВР, реакции с H₂, O₂, галогенами, водой, "
            "кислотами, солями и щёлочами, а также способы получения.\n\n"
            "Можно пройти 10, 20 или сразу все 50 вопросов. "
            "Ошибки сохраняются — их можно потом отдельно повторить.\n\n"
            "Тренажёр уже открыт 👇"
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
    return True


def _dm_text(day, first_name):
    hello = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    texts = {
        date(2026, 9, 24): (
            "Сегодня открылся новый тренажёр <b>«Неметаллы»</b> ⚛️\n\n"
            "Начни хотя бы с 10 вопросов — это займёт совсем немного времени, "
            "а ошибки сохранятся для повторения."
        ),
        date(2026, 9, 25): (
            "Небольшое повторение на сегодня ⚛️\n\n"
            "Зайди в тренажёр <b>«Неметаллы»</b> и пройди ещё один короткий подход. "
            "Можно выбрать 10 или 20 вопросов."
        ),
        date(2026, 9, 26): (
            "Выходной — хороший момент спокойно добить неметаллы ⚛️\n\n"
            "Если уже проходил(а) тренажёр, загляни в <b>«Мои ошибки»</b>. "
            "Если ещё нет — начни с 10 вопросов."
        ),
        date(2026, 9, 27): (
            "Последнее напоминание перед понедельником ⚛️\n\n"
            "Проверь себя по <b>неметаллам</b>: пройди тренировку или повтори сохранённые ошибки. "
            "Лучше 10 вопросов сегодня, чем откладывать тему на потом 💗"
        ),
    }
    return hello + "\n\n" + texts[day]


async def send_personal_reminders(context, day):
    markup = await _trainer_markup(context)
    sent = failed = skipped = 0
    day_key = day.isoformat()
    for telegram_id, first_name in _student_recipients():
        if _sent("dm", day_key, telegram_id):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=_dm_text(day, first_name),
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception as exc:
            failed += 1
            print(
                f"NONMETALS_CAMPAIGN dm_failed day={day_key} user={telegram_id} error={type(exc).__name__}",
                flush=True,
            )
            continue
        _mark_sent("dm", day_key, telegram_id)
        sent += 1
    print(
        f"NONMETALS_CAMPAIGN dm day={day_key} sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


async def campaign_tick(context):
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    current_time = now.time().replace(tzinfo=None)
    day_key = today.isoformat()

    if today == GROUP_DATE and current_time >= GROUP_TIME and not _sent("group", day_key, 0):
        try:
            if await send_group_announcement(context):
                _mark_sent("group", day_key, 0)
                print("NONMETALS_CAMPAIGN group sent=1", flush=True)
        except Exception as exc:
            print(
                f"NONMETALS_CAMPAIGN group_failed error={type(exc).__name__}",
                flush=True,
            )

    if today in DM_DATES and current_time >= DM_TIME:
        await send_personal_reminders(context, today)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_nonmetals_campaign(context):
    try:
        await _previous_tick(context)
    finally:
        await campaign_tick(context)


live7.friday_trivial_tick = combined_tick_with_nonmetals_campaign
ensure_campaign_table()
print(
    "Nonmetals campaign ready: group=2026-09-24 10:00; dm=2026-09-24..27 17:00",
    flush=True,
)
