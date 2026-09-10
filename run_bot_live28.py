import sqlite3
from datetime import datetime, timedelta

import run_bot_live27

live27 = run_bot_live27
live26 = live27.live26
live25 = live27.live25
live24 = live27.live24
run_bot = live25.run_bot
bot = live25.bot
live7 = live25.live7

REMIND_BEFORE_HOURS = 3


def ensure_unanswered_reminder_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_poll_answers (
                poll_id TEXT NOT NULL,
                lesson_number INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (poll_id, telegram_user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unanswered_poll_reminders (
                event_type TEXT NOT NULL,
                event_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (event_type, event_key, telegram_user_id)
            )
            """
        )
        conn.commit()


def _active_linked_students(conn):
    return conn.execute(
        """
        SELECT telegram_user_id,
               coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик')
        FROM students
        WHERE active = 1 AND telegram_user_id IS NOT NULL
        ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
        """
    ).fetchall()


_original_poll_answer = live24.probnik_poll_answer


async def combined_poll_answer(update, context):
    """Save lesson-poll votes; leave mock-exam polls to the existing handler."""
    answer = update.poll_answer
    if not answer or not answer.user:
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        lesson_row = conn.execute(
            """
            SELECT lesson_number
            FROM lesson_day_before_reminders
            WHERE poll_id = ?
            LIMIT 1
            """,
            (answer.poll_id,),
        ).fetchone()

        if lesson_row:
            lesson_number = int(lesson_row[0])
            if answer.option_ids:
                conn.execute(
                    """
                    INSERT INTO lesson_poll_answers
                        (poll_id, lesson_number, telegram_user_id, option_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(poll_id, telegram_user_id) DO UPDATE SET
                        option_id = excluded.option_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        answer.poll_id,
                        lesson_number,
                        int(answer.user.id),
                        int(answer.option_ids[0]),
                        datetime.now(bot.TIMEZONE).isoformat(),
                    ),
                )
            else:
                conn.execute(
                    """
                    DELETE FROM lesson_poll_answers
                    WHERE poll_id = ? AND telegram_user_id = ?
                    """,
                    (answer.poll_id, int(answer.user.id)),
                )
            conn.commit()
            return

    await _original_poll_answer(update, context)


# live24.main resolves this global when registering PollAnswerHandler.
live24.probnik_poll_answer = combined_poll_answer


def _event_datetime(event_date, time_text):
    hour, minute = (int(x) for x in time_text.split(":", 1))
    return datetime(
        event_date.year,
        event_date.month,
        event_date.day,
        hour,
        minute,
        tzinfo=bot.TIMEZONE,
    )


def _within_reminder_window(now, event_dt):
    reminder_at = event_dt - timedelta(hours=REMIND_BEFORE_HOURS)
    return reminder_at <= now < event_dt


def _already_reminded(conn, event_type, event_key, telegram_user_id):
    row = conn.execute(
        """
        SELECT 1 FROM unanswered_poll_reminders
        WHERE event_type = ? AND event_key = ? AND telegram_user_id = ?
        LIMIT 1
        """,
        (event_type, event_key, int(telegram_user_id)),
    ).fetchone()
    return bool(row)


def _mark_reminded(conn, event_type, event_key, telegram_user_id):
    conn.execute(
        """
        INSERT OR IGNORE INTO unanswered_poll_reminders
            (event_type, event_key, telegram_user_id, sent_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            event_type,
            event_key,
            int(telegram_user_id),
            datetime.now(bot.TIMEZONE).isoformat(),
        ),
    )


async def _remind_lesson_nonresponders(context, now):
    lesson_date = now.date()
    info = live25._lesson_info_for_date(lesson_date)
    if not info:
        return

    lesson_number, lesson_time = info
    event_dt = _event_datetime(lesson_date, lesson_time)
    if not _within_reminder_window(now, event_dt):
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll_row = conn.execute(
            """
            SELECT poll_id
            FROM lesson_day_before_reminders
            WHERE lesson_number = ? AND poll_id IS NOT NULL
            LIMIT 1
            """,
            (lesson_number,),
        ).fetchone()
        if not poll_row:
            return
        poll_id = poll_row[0]
        answered_ids = {
            int(row[0])
            for row in conn.execute(
                "SELECT telegram_user_id FROM lesson_poll_answers WHERE poll_id = ?",
                (poll_id,),
            ).fetchall()
        }
        students = _active_linked_students(conn)

        for telegram_user_id, _name in students:
            telegram_user_id = int(telegram_user_id)
            if telegram_user_id in answered_ids:
                continue
            event_key = str(lesson_number)
            if _already_reminded(conn, "lesson", event_key, telegram_user_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        f"💗 Ты ещё не отметился(ась) на урок №{lesson_number} сегодня в {lesson_time}.\n\n"
                        "Зайди, пожалуйста, в группу курса и выбери в опросе «✅ Буду» или «❌ Не буду»."
                    ),
                )
            except Exception as exc:
                print(f"Could not send lesson poll reminder to {telegram_user_id}: {exc}")
                continue
            _mark_reminded(conn, "lesson", event_key, telegram_user_id)
            conn.commit()


async def _remind_probnik_nonresponders(context, now):
    probnik_date = now.date()
    if probnik_date not in run_bot.PROBNIK_DATES:
        return

    event_dt = _event_datetime(probnik_date, "10:00")
    if not _within_reminder_window(now, event_dt):
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll_row = conn.execute(
            """
            SELECT poll_id, probnik_number
            FROM probnik_polls
            WHERE probnik_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (probnik_date.isoformat(),),
        ).fetchone()
        if not poll_row:
            return

        poll_id, probnik_number = poll_row
        answered_ids = {
            int(row[0])
            for row in conn.execute(
                "SELECT telegram_user_id FROM probnik_poll_answers WHERE poll_id = ?",
                (poll_id,),
            ).fetchall()
        }
        students = _active_linked_students(conn)

        for telegram_user_id, _name in students:
            telegram_user_id = int(telegram_user_id)
            if telegram_user_id in answered_ids:
                continue
            event_key = probnik_date.isoformat()
            if _already_reminded(conn, "probnik", event_key, telegram_user_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        f"📝 Ты ещё не отметился(ась) на пробник №{probnik_number} сегодня в 10:00.\n\n"
                        "Зайди, пожалуйста, в группу курса и выбери в опросе «✅ Буду» или «❌ Не буду»."
                    ),
                )
            except Exception as exc:
                print(f"Could not send mock-exam poll reminder to {telegram_user_id}: {exc}")
                continue
            _mark_reminded(conn, "probnik", event_key, telegram_user_id)
            conn.commit()


async def unanswered_poll_reminder_tick(context):
    now = datetime.now(bot.TIMEZONE)
    await _remind_lesson_nonresponders(context, now)
    await _remind_probnik_nonresponders(context, now)


_previous_tick = live7.friday_trivial_tick


async def combined_everything_tick(context):
    try:
        await _previous_tick(context)
    finally:
        await unanswered_poll_reminder_tick(context)


# live24.main schedules live7.friday_trivial_tick every 30 seconds.
live7.friday_trivial_tick = combined_everything_tick


if __name__ == "__main__":
    live25.ensure_lesson_day_before_table()
    live24.ensure_probnik_poll_tables()
    ensure_unanswered_reminder_tables()
    live24.main()
