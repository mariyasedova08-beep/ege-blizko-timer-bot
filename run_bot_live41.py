import sqlite3
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live40

live40 = run_bot_live40
live39 = live40.live39
live37 = live40.live37
live35 = live40.live35
live34 = live40.live34
live31 = live40.live31
live24 = live40.live24
live17 = live40.live17
live7 = live34.live7
bot = live40.bot
run_bot = live34.run_bot

WEEKLY_REPORT_WEEKDAY = 6  # воскресенье
WEEKLY_REPORT_TIME = time(18, 0)


def ensure_weekly_report_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_student_reports (
                week_key TEXT NOT NULL,
                student_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (week_key, student_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_trainer_catalog (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                start_param TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 100,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()


def register_weekly_trainer(code, title, start_param, sort_order=100, active=True):
    """Register a trainer once; weekly reports pick up all active entries automatically."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO weekly_trainer_catalog (code, title, start_param, sort_order, active)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                start_param = excluded.start_param,
                sort_order = excluded.sort_order,
                active = excluded.active
            """,
            (code, title, start_param, int(sort_order), 1 if active else 0),
        )
        conn.commit()


def seed_current_trainers():
    register_weekly_trainer("trivial", "🧫 Тривиальные названия", "trivial", 10)
    register_weekly_trainer("acid", "🧪 Кислоты и кислотные остатки", "acid", 20)


def _active_trainers():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT title, start_param
            FROM weekly_trainer_catalog
            WHERE active = 1
            ORDER BY sort_order, title
            """
        ).fetchall()


def _week_start(now):
    return now.date() - timedelta(days=6)


def _week_key(now):
    return now.date().isoformat()


def _already_sent(student_id, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM weekly_student_reports WHERE week_key = ? AND student_id = ? LIMIT 1",
            (_week_key(now), int(student_id)),
        ).fetchone())


def _mark_sent(student_id, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO weekly_student_reports (week_key, student_id, sent_at)
            VALUES (?, ?, ?)
            """,
            (_week_key(now), int(student_id), now.isoformat()),
        )
        conn.commit()


def _weekly_attendance(conn, student_id, now):
    rows = conn.execute(
        """
        SELECT ar.status
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.lesson_number = ar.lesson_number
        WHERE ar.student_id = ?
          AND s.finalized = 1
          AND s.lesson_date >= ?
          AND s.lesson_date <= ?
        ORDER BY s.lesson_date
        """,
        (int(student_id), _week_start(now).isoformat(), now.date().isoformat()),
    ).fetchall()
    total = len(rows)
    present = sum(1 for (status,) in rows if status == "present")
    return present, total


def _weekly_homework(conn, student_row, now):
    _student_id, _display, _user_name, email, coreapp_user_id, _telegram_id = student_row
    dates = run_bot.COURSE_LESSON_DATES
    week_start = _week_start(now)
    expected = []

    # Считаем работы, срок которых пришёлся на текущую неделю:
    # ДЗ после урока N должно быть закрыто к уроку N+1.
    for i in range(len(dates) - 1):
        due_date = dates[i + 1]
        if week_start <= due_date <= now.date():
            expected.append(i + 1)  # номер урока N

    if not expected:
        return 0, 0

    submissions = conn.execute(
        """
        SELECT user_id, lower(user_email), lesson_id, lesson_name
        FROM homework_submissions
        WHERE (coalesce(user_id, '') != '' AND user_id = ?)
           OR (coalesce(user_email, '') != '' AND lower(user_email) = lower(?))
        """,
        (str(coreapp_user_id or ""), str(email or "")),
    ).fetchall()

    done = 0
    for lesson_number in expected:
        previous_date = dates[lesson_number - 1]
        target_number = lesson_number + 1
        matched = any(
            live31._submission_explicitly_matches(
                lesson_id,
                lesson_name,
                target_number,
                lesson_number,
                previous_date,
            )
            for _uid, _mail, lesson_id, lesson_name in submissions
        )
        if matched:
            done += 1
    return done, len(expected)


def _weekly_trainer_stats(conn, telegram_id, now):
    since = datetime.combine(_week_start(now), time.min, tzinfo=bot.TIMEZONE).isoformat()
    until = now.isoformat()

    trivial = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM trivial_sessions
        WHERE telegram_user_id = ?
          AND finished_at IS NOT NULL
          AND finished_at >= ? AND finished_at <= ?
        """,
        (int(telegram_id), since, until),
    ).fetchone()
    acid = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM acid_sessions
        WHERE telegram_user_id = ?
          AND finished_at IS NOT NULL
          AND finished_at >= ? AND finished_at <= ?
        """,
        (int(telegram_id), since, until),
    ).fetchone()

    sessions = int(trivial[0] or 0) + int(acid[0] or 0)
    questions = int(trivial[1] or 0) + int(acid[1] or 0)
    correct = int(trivial[2] or 0) + int(acid[2] or 0)
    return sessions, questions, correct


def _recommendation(att_present, att_total, hw_done, hw_total, sessions, accuracy):
    if hw_total and hw_done < hw_total:
        missing = hw_total - hw_done
        return f"Главный фокус сейчас — закрыть несданные ДЗ ({missing}). Сначала ДЗ, потом тренажёры 💗"
    if sessions == 0:
        return "На следующей неделе добавь хотя бы пару коротких тренировок. Выбирай любой тренажёр ниже 👇"
    if accuracy is not None and accuracy < 70:
        return "Тренировки есть — супер. Теперь лучше повторить темы, где было больше ошибок, и поднять точность."
    if att_total and att_present < att_total:
        return "На следующей неделе постарайся не пропускать занятия и продолжай закреплять материал тренажёрами."
    return "Хороший темп 💗 Продолжай так же и выбери тренажёр для короткого повторения на следующей неделе."


def weekly_report_text(student_row, now):
    student_id, display_name, _user_name, _email, _coreapp_id, telegram_id = student_row
    first_name = str(display_name or "").strip().split()[0] if str(display_name or "").strip() else ""
    greeting = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        att_present, att_total = _weekly_attendance(conn, student_id, now)
        hw_done, hw_total = _weekly_homework(conn, student_row, now)
        sessions, questions, correct = _weekly_trainer_stats(conn, telegram_id, now)

    accuracy = round(correct * 100 / questions) if questions else None
    attendance_text = f"{att_present} из {att_total} уроков" if att_total else "пока нет сохранённых уроков за неделю"
    homework_text = f"{hw_done} из {hw_total} закрыто" if hw_total else "на этой неделе ещё не было ДЗ со сроком сдачи"
    result_text = f"{correct} из {questions} верно · {accuracy}%" if questions else "пока нет результатов за неделю"

    recommendation = _recommendation(
        att_present, att_total, hw_done, hw_total, sessions, accuracy
    )

    return "\n".join([
        greeting,
        "",
        "📊 Твои итоги недели",
        "",
        f"🎓 Посещаемость: {attendance_text}",
        f"🏠 ДЗ: {homework_text}",
        f"🧪 Тренажёры: {sessions} тренировок",
        f"📈 Результат: {result_text}",
        "",
        f"💡 {recommendation}",
        "",
        "Все доступные тренажёры — кнопками ниже. Выбирай любой 👇",
    ])


async def _weekly_report_markup(context):
    me = await context.bot.get_me()
    username = me.username
    rows = []
    if username:
        for title, start_param in _active_trainers():
            rows.append([
                InlineKeyboardButton(
                    title,
                    url=f"https://t.me/{username}?start={start_param}",
                )
            ])
    admin_id = bot.get_admin_id()
    if admin_id:
        rows.append([
            InlineKeyboardButton(
                "✉️ Написать Марии Александровне",
                url=f"tg://user?id={int(admin_id)}",
            )
        ])
    return InlineKeyboardMarkup(rows) if rows else None


async def weekly_student_report_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.weekday() != WEEKLY_REPORT_WEEKDAY or now.time() < WEEKLY_REPORT_TIME:
        return

    markup = await _weekly_report_markup(context)
    for student_row in live34._student_rows():
        student_id = int(student_row[0])
        telegram_id = student_row[5]
        if telegram_id is None or _already_sent(student_id, now):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=weekly_report_text(student_row, now),
                reply_markup=markup,
            )
        except Exception as exc:
            print(f"Could not send weekly report to student {telegram_id}: {exc}")
            continue
        _mark_sent(student_id, now)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_weekly_reports(context):
    try:
        await _previous_tick(context)
    finally:
        await weekly_student_report_tick(context)


live7.friday_trivial_tick = combined_tick_with_weekly_reports


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    ensure_weekly_report_tables()
    seed_current_trainers()
    live24.main()
