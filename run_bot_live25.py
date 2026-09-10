import html
import os
import sqlite3
from datetime import datetime, timedelta

import run_bot_live24

live24 = run_bot_live24
bot = live24.bot
run_bot = live24.run_bot
live7 = live24.live7

LESSON_REMINDER_NOT_BEFORE = "18:00"
LESSON_POLL_OPTIONS = ("✅ Буду", "❌ Не буду")

WEEKDAYS_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среду",
    3: "четверг",
    4: "пятницу",
    5: "субботу",
    6: "воскресенье",
}


def ensure_lesson_day_before_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_day_before_reminders (
                lesson_number INTEGER PRIMARY KEY,
                lesson_date TEXT NOT NULL,
                message_id INTEGER,
                poll_id TEXT,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _lesson_time(lesson_date):
    # Понедельник/среда — 18:30; воскресенье и специальная суббота — 10:00.
    return "18:30" if lesson_date.weekday() in {0, 2} else "10:00"


def _lesson_info_for_date(lesson_date):
    if lesson_date not in run_bot.COURSE_LESSON_DATE_SET:
        return None
    lesson_number = run_bot.COURSE_LESSON_DATES.index(lesson_date) + 1
    return lesson_number, _lesson_time(lesson_date)


def _existing_reminder(lesson_number):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT message_id, poll_id
            FROM lesson_day_before_reminders
            WHERE lesson_number = ?
            LIMIT 1
            """,
            (lesson_number,),
        ).fetchone()


def _lesson_message(lesson_number, lesson_date, lesson_time):
    zoom_url = os.getenv("LESSON_ZOOM_URL", "").strip()
    zoom_id = os.getenv("LESSON_ZOOM_ID", "").strip()
    zoom_passcode = os.getenv("LESSON_ZOOM_PASSCODE", "").strip()

    if not zoom_url:
        return None

    weekday = WEEKDAYS_RU[lesson_date.weekday()]
    date_text = lesson_date.strftime("%d.%m")
    safe_url = html.escape(zoom_url, quote=True)
    safe_id = html.escape(zoom_id)
    safe_passcode = html.escape(zoom_passcode)

    zoom_lines = [
        "💣💣💣",
        "<b>Приглашение в ZOOM</b>",
        "",
        f'<a href="{safe_url}">Войти в Zoom-конференцию</a>',
    ]
    if safe_id:
        zoom_lines.append(f"Идентификатор конференции: <b>{safe_id}</b>")
    if safe_passcode:
        zoom_lines.append(f"Код доступа: <b>{safe_passcode}</b>")

    return (
        "💁‍♀️💁‍♀️💁‍♀️\n"
        f"В <b>{weekday} {date_text}</b> в <b>{lesson_time}</b> будет проходить ❤️ "
        f"<b>урок №{lesson_number} на платформе ZOOM!</b>\n\n"
        "📌 <b>На уроке у вас должны присутствовать:</b>\n"
        "<b>1. Таблица Менделеева</b>\n"
        "<b>2. Таблица растворимости</b>\n"
        "3. Тетрадь в клетку / планшет с конспектом / распечатанный конспект\n"
        "4. Цветные ручки или карандаши\n"
        "5. Чаек / кофеек / водичка\n"
        "6. Хорошее настроение\n\n"
        + "\n".join(zoom_lines)
    )


async def send_day_before_lesson_reminder(context, lesson_date):
    info = _lesson_info_for_date(lesson_date)
    if not info:
        return False
    lesson_number, lesson_time = info

    chat_id = os.getenv("CHAT_ID", "").strip()
    if not chat_id:
        return False

    existing = _existing_reminder(lesson_number)
    message_id = existing[0] if existing else None
    poll_id = existing[1] if existing else None
    target_chat_id = int(chat_id)
    thread_id = bot.get_target_thread_id()
    now = datetime.now(bot.TIMEZONE).isoformat()

    if message_id is None:
        text = _lesson_message(lesson_number, lesson_date, lesson_time)
        if text is None:
            print("LESSON_ZOOM_URL is not configured; lesson reminder skipped")
            return False
        sent_message = await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        message_id = sent_message.message_id
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO lesson_day_before_reminders
                    (lesson_number, lesson_date, message_id, poll_id, sent_at)
                VALUES (?, ?, ?, NULL, ?)
                ON CONFLICT(lesson_number) DO UPDATE SET
                    lesson_date = excluded.lesson_date,
                    message_id = excluded.message_id,
                    sent_at = excluded.sent_at
                """,
                (lesson_number, lesson_date.isoformat(), message_id, now),
            )
            conn.commit()

    if not poll_id:
        poll = await context.bot.send_poll(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            question=(
                f"🎓 Будешь на уроке №{lesson_number} "
                f"{lesson_date.strftime('%d.%m')} в {lesson_time}?"
            ),
            options=list(LESSON_POLL_OPTIONS),
            is_anonymous=False,
            allows_multiple_answers=False,
            is_closed=False,
        )
        poll_id = poll.poll.id
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                UPDATE lesson_day_before_reminders
                SET poll_id = ?, sent_at = ?
                WHERE lesson_number = ?
                """,
                (poll_id, now, lesson_number),
            )
            conn.commit()

    return True


_original_weekly_trainer_tick = live7.friday_trivial_tick


async def combined_trainer_and_lesson_tick(context):
    # Сохраняем пятничный тренажёр тривиальных названий и субботнее напоминание по кислотам.
    await _original_weekly_trainer_tick(context)

    now = datetime.now(bot.TIMEZONE)
    if now.strftime("%H:%M") < LESSON_REMINDER_NOT_BEFORE:
        return

    tomorrow = now.date() + timedelta(days=1)
    if tomorrow not in run_bot.COURSE_LESSON_DATE_SET:
        return

    await send_day_before_lesson_reminder(context, tomorrow)


# live24.main уже запускает этот tick каждые 30 секунд, поэтому новая логика
# подключается без изменения остальных напоминаний и обработчиков.
live7.friday_trivial_tick = combined_trainer_and_lesson_tick


if __name__ == "__main__":
    ensure_lesson_day_before_table()
    live24.main()
