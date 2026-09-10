import sqlite3
from datetime import datetime, timedelta

import run_bot_live29

live29 = run_bot_live29
live28 = live29.run_bot_live28
live27 = live28.live27
live25 = live28.live25
live24 = live28.live24
live7 = live28.live7
live3 = live25.live24.live23.live22.live21.live20.live19.live18.live17.live15.live10.live7.live6.live4.live3
run_bot = live28.run_bot
bot = live28.bot

AUTO_ATTENDANCE_AFTER_MINUTES = 120


def ensure_auto_attendance_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_poll_drafts (
                lesson_number INTEGER PRIMARY KEY,
                poll_id TEXT,
                yes_count INTEGER NOT NULL DEFAULT 0,
                no_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _draft_exists(lesson_number):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM attendance_poll_drafts WHERE lesson_number = ? LIMIT 1",
            (lesson_number,),
        ).fetchone()
    return bool(row)


def _lesson_event_dt(lesson_date):
    info = live25._lesson_info_for_date(lesson_date)
    if not info:
        return None, None, None
    lesson_number, lesson_time = info
    hour, minute = (int(x) for x in lesson_time.split(":", 1))
    dt = datetime(
        lesson_date.year,
        lesson_date.month,
        lesson_date.day,
        hour,
        minute,
        tzinfo=bot.TIMEZONE,
    )
    return lesson_number, lesson_time, dt


def _create_attendance_draft(lesson_number):
    """Prefill attendance from the latest lesson poll without finalizing it."""
    live3.ensure_attendance_session(lesson_number)
    now = datetime.now(bot.TIMEZONE).isoformat()

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
            return None

        poll_id = poll_row[0]
        answers = conn.execute(
            """
            SELECT lpa.telegram_user_id, lpa.option_id, s.id
            FROM lesson_poll_answers lpa
            LEFT JOIN students s
              ON s.telegram_user_id = lpa.telegram_user_id AND s.active = 1
            WHERE lpa.poll_id = ?
            """,
            (poll_id,),
        ).fetchall()

        yes_count = 0
        no_count = 0
        for telegram_user_id, option_id, student_id in answers:
            if student_id is None:
                continue
            option_id = int(option_id)
            if option_id == 0:
                status = "present"
                yes_count += 1
            elif option_id == 1:
                status = "absent"
                no_count += 1
            else:
                continue
            conn.execute(
                """
                INSERT INTO attendance_records
                    (lesson_number, student_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lesson_number, student_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (lesson_number, int(student_id), status, now),
            )

        conn.execute(
            """
            UPDATE attendance_sessions
            SET finalized = 0, updated_at = ?
            WHERE lesson_number = ?
            """,
            (now, lesson_number),
        )
        conn.execute(
            """
            INSERT INTO attendance_poll_drafts
                (lesson_number, poll_id, yes_count, no_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(lesson_number) DO NOTHING
            """,
            (lesson_number, poll_id, yes_count, no_count, now),
        )
        conn.commit()

    return yes_count, no_count


async def auto_attendance_tick(context):
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    if today not in run_bot.COURSE_LESSON_DATE_SET:
        return

    lesson_number, lesson_time, event_dt = _lesson_event_dt(today)
    if not lesson_number or not event_dt:
        return

    draft_at = event_dt + timedelta(minutes=AUTO_ATTENDANCE_AFTER_MINUTES)
    # Tick идёт каждые 30 секунд; после наступления времени создаём только один черновик.
    if now < draft_at or _draft_exists(lesson_number):
        return

    result = _create_attendance_draft(lesson_number)
    if result is None:
        return

    yes_count, no_count = result
    admin_id = bot.get_admin_id()
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=(
                    f"🎓 Черновик посещаемости урока №{lesson_number} готов.\n\n"
                    f"По опросу: ✅ будут — {yes_count}, ❌ не будут — {no_count}.\n"
                    "Открой «Кабинет Маши» → «Посещение», поправь тех, кто фактически не пришёл, и нажми «💾 Сохранить»."
                ),
            )
        except Exception as exc:
            print(f"Could not notify admin about attendance draft: {exc}")


_original_attendance_text = live3.attendance_text


def attendance_text_with_draft(lesson_number, finalized, records, student_count):
    text = _original_attendance_text(lesson_number, finalized, records, student_count)
    if not finalized and _draft_exists(lesson_number):
        text += "\n\n🤖 Черновик создан автоматически из опроса. Проверь фактическое присутствие и нажми «💾 Сохранить»."
    return text


live3.attendance_text = attendance_text_with_draft


_previous_tick = live7.friday_trivial_tick


async def combined_everything_with_attendance_tick(context):
    try:
        await _previous_tick(context)
    finally:
        await auto_attendance_tick(context)


live7.friday_trivial_tick = combined_everything_with_attendance_tick


if __name__ == "__main__":
    live25.ensure_lesson_day_before_table()
    live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
    live3.ensure_attendance_tables()
    ensure_auto_attendance_table()
    live24.main()
