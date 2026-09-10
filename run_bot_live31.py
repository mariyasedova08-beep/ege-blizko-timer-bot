import re
import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live30

live30 = run_bot_live30
live28 = live30.live28
live25 = live30.live25
live24 = live30.live24
live7 = live30.live7
run_bot = live30.run_bot
bot = live30.bot

HOMEWORK_PERSONAL_REMINDER_HOUR = 21


def ensure_personal_homework_reminder_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS personal_homework_reminders (
                target_lesson_number INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (target_lesson_number, telegram_user_id)
            )
            """
        )
        conn.commit()


def _norm(value):
    return str(value or "").strip().lower().replace("ё", "е")


def _lesson_number_from_name(value):
    text = _norm(value)
    patterns = (
        r"к\s+уроку\s*(?:№|#)?\s*(\d+)",
        r"урок\s*(?:№|#)?\s*(\d+)",
    )
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


def _date_tokens(d):
    return {
        d.strftime("%d.%m"),
        d.strftime("%d/%m"),
        d.strftime("%d-%m"),
        f"{d.day}.{d.month}",
        f"{d.day}/{d.month}",
        f"{d.day}-{d.month}",
    }


def _submission_explicitly_matches(lesson_id, lesson_name, target_lesson_number, previous_lesson_number, previous_lesson_date):
    lesson_id_text = _norm(lesson_id)
    lesson_name_text = _norm(lesson_name)

    # Если CoreApp называет работу «к уроку №N», ориентируемся на следующий урок.
    m = re.search(r"к\s+уроку\s*(?:№|#)?\s*(\d+)", lesson_name_text)
    if m and int(m.group(1)) == target_lesson_number:
        return True

    # В текущем курсе задания обычно относятся к предыдущему уроку.
    number = _lesson_number_from_name(lesson_name_text)
    if number == previous_lesson_number:
        return True
    if f"monitoring:lesson:{previous_lesson_number}" in lesson_id_text:
        return True

    # В исторической выгрузке номер может отсутствовать, но в названии есть дата урока.
    if any(token in lesson_name_text for token in _date_tokens(previous_lesson_date)):
        return True

    return False


def _target_homework_done_sets(target_lesson_number, previous_lesson_number, previous_lesson_date, now):
    """Return CoreApp ids/emails that have completed the homework relevant to tomorrow's lesson."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT received_at, user_id, lower(user_email), lesson_id, lesson_name
            FROM homework_submissions
            """
        ).fetchall()

    explicit = []
    for row in rows:
        received_at, user_id, email, lesson_id, lesson_name = row
        if _submission_explicitly_matches(
            lesson_id, lesson_name, target_lesson_number, previous_lesson_number, previous_lesson_date
        ):
            explicit.append(row)

    chosen = explicit

    # Fallback для live-webhook CoreApp, если название урока не содержит номер/дату:
    # берём самый свежий lesson_id, который появился после предыдущего занятия.
    if not chosen:
        previous_start = datetime.combine(previous_lesson_date, time.min, tzinfo=bot.TIMEZONE)
        recent = []
        for row in rows:
            received_at, _user_id, _email, lesson_id, _lesson_name = row
            if not lesson_id:
                continue
            try:
                received_dt = datetime.fromisoformat(received_at)
                if received_dt.tzinfo is None:
                    received_dt = received_dt.replace(tzinfo=bot.TIMEZONE)
            except Exception:
                continue
            if previous_start <= received_dt <= now:
                recent.append((received_dt, row))

        if recent:
            recent.sort(key=lambda item: item[0], reverse=True)
            latest_lesson_id = _norm(recent[0][1][3])
            if latest_lesson_id:
                chosen = [row for _dt, row in recent if _norm(row[3]) == latest_lesson_id]

    done_ids = {str(row[1] or "").strip() for row in chosen if row[1]}
    done_emails = {_norm(row[2]) for row in chosen if row[2]}
    return done_ids, done_emails


def _already_sent(conn, target_lesson_number, telegram_user_id):
    return bool(
        conn.execute(
            """
            SELECT 1 FROM personal_homework_reminders
            WHERE target_lesson_number = ? AND telegram_user_id = ?
            LIMIT 1
            """,
            (target_lesson_number, int(telegram_user_id)),
        ).fetchone()
    )


async def personal_homework_reminder_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.hour < HOMEWORK_PERSONAL_REMINDER_HOUR:
        return

    tomorrow = now.date() + bot.timedelta(days=1)
    if tomorrow not in run_bot.COURSE_LESSON_DATE_SET:
        return

    dates = run_bot.COURSE_LESSON_DATES
    target_lesson_number = dates.index(tomorrow) + 1
    if target_lesson_number <= 1:
        return

    previous_lesson_number = target_lesson_number - 1
    previous_lesson_date = dates[previous_lesson_number - 1]
    done_ids, done_emails = _target_homework_done_sets(
        target_lesson_number,
        previous_lesson_number,
        previous_lesson_date,
        now,
    )

    admin_id = bot.get_admin_id()
    reply_markup = None
    if admin_id:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✉️ Написать Марии Александровне",
                url=f"tg://user?id={int(admin_id)}",
            )]
        ])

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT coreapp_user_id, lower(user_email), telegram_user_id
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
            """
        ).fetchall()

        for coreapp_user_id, email, telegram_user_id in students:
            telegram_user_id = int(telegram_user_id)
            is_done = (
                (coreapp_user_id and str(coreapp_user_id).strip() in done_ids)
                or (email and _norm(email) in done_emails)
            )
            if is_done or _already_sent(conn, target_lesson_number, telegram_user_id):
                continue

            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        f"📝 ДЗ к уроку №{target_lesson_number} ещё не сдано 💗\n\n"
                        "Завтра у нас урок, поэтому постарайся закончить домашнюю работу сегодня.\n\n"
                        "Когда планируешь сделать ДЗ? Напиши, пожалуйста, Марии Александровне в личные сообщения 👇"
                    ),
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                print(f"Could not send personal homework reminder to {telegram_user_id}: {exc}")
                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO personal_homework_reminders
                    (target_lesson_number, telegram_user_id, sent_at)
                VALUES (?, ?, ?)
                """,
                (target_lesson_number, telegram_user_id, now.isoformat()),
            )
            conn.commit()


_previous_tick = live7.friday_trivial_tick


async def combined_everything_with_homework_tick(context):
    try:
        await _previous_tick(context)
    finally:
        await personal_homework_reminder_tick(context)


# Этот tick уже запускается каждые 30 секунд в текущем main.
live7.friday_trivial_tick = combined_everything_with_homework_tick


if __name__ == "__main__":
    live25.ensure_lesson_day_before_table()
    live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
    live30.live3.ensure_attendance_tables()
    live30.ensure_auto_attendance_table()
    ensure_personal_homework_reminder_table()
    live24.main()
