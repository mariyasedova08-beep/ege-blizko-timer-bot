import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live76

live76 = run_bot_live76
live75 = live76.live75
live74 = live76.live74
live73 = live76.live73
live72 = live76.live72
live71 = live76.live71
live70 = live76.live70
live69 = live76.live69
live68 = live76.live68
live67 = live76.live67
live66 = live76.live66
live65 = live76.live65
live64 = live76.live64
live63 = live76.live63
live61 = live76.live61
live60 = live76.live60
live59 = live76.live59
live56 = live76.live56
live50 = live76.live50
live51 = live76.live51
live48 = live76.live48
live46 = live76.live46
live44 = live76.live44
live43 = live76.live43
live41 = live76.live41
live39 = live76.live39
live37 = live76.live37
live35 = live76.live35
live34 = live76.live34
live31 = live76.live31
live24 = live76.live24
live17 = live76.live17
live28 = live76.live28
bot = live76.bot
run_bot = live76.run_bot
live23 = live67.live23
live7 = live67.live7

# После обычных уроков: Пн/Ср 20:30, Вс 13:00.
# Субботу тоже поддерживаем в 13:00 на случай переноса воскресного урока.
FEEDBACK_SEND = {
    0: time(20, 30),
    2: time(20, 30),
    5: time(13, 0),
    6: time(13, 0),
}
# Маше сводка приходит спустя 1,5 часа; актуальный результат всегда доступен в кабинете.
FEEDBACK_SUMMARY = {
    0: time(22, 0),
    2: time(22, 0),
    5: time(14, 30),
    6: time(14, 30),
}
CHOICES = {
    "ok": "😊 всё понял",
    "question": "🤔 есть вопросы",
    "hard": "😵 сложно",
}


def ensure_lesson_feedback_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_feedback_rounds (
                lesson_number INTEGER PRIMARY KEY,
                lesson_date TEXT NOT NULL,
                lesson_time TEXT NOT NULL,
                topic TEXT NOT NULL,
                sent_at TEXT,
                message_id INTEGER,
                summary_sent_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_feedback_answers (
                lesson_number INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                choice TEXT NOT NULL,
                answered_at TEXT NOT NULL,
                PRIMARY KEY (lesson_number, telegram_user_id)
            )
            """
        )
        conn.commit()


def _today_lesson(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT lesson_number, event_date, event_time, topic
            FROM course_schedule
            WHERE active = 1
              AND event_type = 'lesson'
              AND event_date = ?
            ORDER BY event_time
            LIMIT 1
            """,
            (now.date().isoformat(),),
        ).fetchone()


def _feedback_markup(lesson_number):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("😊 всё понял", callback_data=f"triv:feedback:{lesson_number}:ok")],
        [InlineKeyboardButton("🤔 есть вопросы", callback_data=f"triv:feedback:{lesson_number}:question")],
        [InlineKeyboardButton("😵 сложно", callback_data=f"triv:feedback:{lesson_number}:hard")],
    ])


def _feedback_test_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("😊 всё понял", callback_data="triv:feedbacktest:ok")],
        [InlineKeyboardButton("🤔 есть вопросы", callback_data="triv:feedbacktest:question")],
        [InlineKeyboardButton("😵 сложно", callback_data="triv:feedbacktest:hard")],
    ])


def _active_course_students_count():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM students WHERE active = 1").fetchone()[0] or 0)


def feedback_summary_text(lesson_number):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        round_row = conn.execute(
            "SELECT lesson_date, topic FROM lesson_feedback_rounds WHERE lesson_number = ? LIMIT 1",
            (int(lesson_number),),
        ).fetchone()
        counts = dict(conn.execute(
            """
            SELECT choice, COUNT(*)
            FROM lesson_feedback_answers
            WHERE lesson_number = ?
            GROUP BY choice
            """,
            (int(lesson_number),),
        ).fetchall())

    if not round_row:
        return "💬 Пока нет сохранённого опроса после урока."

    lesson_date, topic = round_row
    ok = int(counts.get("ok", 0))
    questions = int(counts.get("question", 0))
    hard = int(counts.get("hard", 0))
    total = ok + questions + hard
    expected = _active_course_students_count()

    def pct(value):
        return round(value * 100 / total) if total else 0

    response_line = f"Ответили: {total} из {expected}" if expected else f"Ответили: {total}"
    lines = [
        f"💬 Обратная связь после урока №{lesson_number}",
        f"📅 {lesson_date}",
        f"Тема: {topic}",
        "",
        response_line,
        f"😊 Всё понял: {ok} · {pct(ok)}%",
        f"🤔 Есть вопросы: {questions} · {pct(questions)}%",
        f"😵 Сложно: {hard} · {pct(hard)}%",
    ]
    if total and hard * 2 >= total:
        lines.extend([
            "",
            "🚨 Половина или больше ответивших выбрали «сложно» — тему стоит повторить.",
        ])
    return "\n".join(lines)


def latest_feedback_summary_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT lesson_number
            FROM lesson_feedback_rounds
            WHERE sent_at IS NOT NULL
            ORDER BY lesson_date DESC, lesson_number DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return "💬 Обратная связь\n\nОпросов после уроков пока не было."
    return feedback_summary_text(int(row[0]))


async def lesson_feedback_tick(context):
    now = datetime.now(bot.TIMEZONE)
    send_at = FEEDBACK_SEND.get(now.weekday())
    summary_at = FEEDBACK_SUMMARY.get(now.weekday())
    if send_at is None:
        return

    lesson = _today_lesson(now)
    if not lesson:
        return

    lesson_number, lesson_date, lesson_time, topic = lesson
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO lesson_feedback_rounds
                (lesson_number, lesson_date, lesson_time, topic)
            VALUES (?, ?, ?, ?)
            """,
            (int(lesson_number), lesson_date, lesson_time, topic),
        )
        sent_at, summary_sent_at = conn.execute(
            "SELECT sent_at, summary_sent_at FROM lesson_feedback_rounds WHERE lesson_number = ?",
            (int(lesson_number),),
        ).fetchone()
        conn.commit()

    if now.time() >= send_at and not sent_at:
        chat_id = bot.os.getenv("CHAT_ID")
        if chat_id:
            kwargs = {
                "chat_id": int(chat_id),
                "text": (
                    f"💬 <b>Ребята, быстрая обратная связь после урока №{lesson_number}</b>\n\n"
                    f"Тема: {topic}\n\n"
                    "Как вам сегодня? Нажмите один вариант — это займёт буквально секунду 💗"
                ),
                "parse_mode": "HTML",
                "reply_markup": _feedback_markup(lesson_number),
            }
            thread_id = bot.get_target_thread_id()
            if thread_id:
                kwargs["message_thread_id"] = thread_id
            try:
                message = await context.bot.send_message(**kwargs)
            except Exception as exc:
                print(f"Lesson feedback send error: {exc}", flush=True)
            else:
                sent_at = now.isoformat()
                with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                    conn.execute(
                        """
                        UPDATE lesson_feedback_rounds
                        SET sent_at = ?, message_id = ?
                        WHERE lesson_number = ?
                        """,
                        (sent_at, int(message.message_id), int(lesson_number)),
                    )
                    conn.commit()

    if summary_at is not None and now.time() >= summary_at and sent_at and not summary_sent_at:
        admin_id = bot.get_admin_id()
        if admin_id:
            try:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=feedback_summary_text(lesson_number),
                )
            except Exception as exc:
                print(f"Lesson feedback summary error: {exc}", flush=True)
            else:
                with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                    conn.execute(
                        "UPDATE lesson_feedback_rounds SET summary_sent_at = ? WHERE lesson_number = ?",
                        (now.isoformat(), int(lesson_number)),
                    )
                    conn.commit()


_previous_trivial_callback = live7.trivial_callback


async def trivial_callback_with_feedback(update, context):
    query = update.callback_query
    data = str(query.data or "") if query else ""

    if data.startswith("triv:feedbacktest:"):
        choice = data.rsplit(":", 1)[-1]
        await query.answer(f"Тест: {CHOICES.get(choice, 'ответ')} ✅")
        return

    if data.startswith("triv:feedback:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        try:
            lesson_number = int(parts[2])
        except ValueError:
            return
        choice = parts[3]
        if choice not in CHOICES:
            return

        # Ответ Маши не должен искажать детскую статистику.
        if bot.user_is_admin(update):
            await query.answer("Твой ответ в статистику ребят не считаю 🙂")
            return

        now = datetime.now(bot.TIMEZONE).isoformat()
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            exists = conn.execute(
                "SELECT 1 FROM lesson_feedback_rounds WHERE lesson_number = ? AND sent_at IS NOT NULL",
                (lesson_number,),
            ).fetchone()
            if not exists:
                await query.answer("Этот опрос уже не активен")
                return
            previous = conn.execute(
                """
                SELECT choice FROM lesson_feedback_answers
                WHERE lesson_number = ? AND telegram_user_id = ?
                """,
                (lesson_number, int(update.effective_user.id)),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO lesson_feedback_answers
                    (lesson_number, telegram_user_id, choice, answered_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lesson_number, telegram_user_id) DO UPDATE SET
                    choice = excluded.choice,
                    answered_at = excluded.answered_at
                """,
                (lesson_number, int(update.effective_user.id), choice, now),
            )
            conn.commit()
        await query.answer("Ответ изменён 💗" if previous else "Ответ сохранён 💗")
        return

    await _previous_trivial_callback(update, context)


live7.trivial_callback = trivial_callback_with_feedback

_previous_tick = live7.friday_trivial_tick


async def tick_with_lesson_feedback(context):
    try:
        await _previous_tick(context)
    finally:
        await lesson_feedback_tick(context)


live7.friday_trivial_tick = tick_with_lesson_feedback

# Актуальная сводка доступна Маше в кабинете в любой момент.
_original_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_feedback():
    base = _original_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:feedback"
        for row in rows for button in row
    ):
        rows.insert(max(0, len(rows) - 1), [
            InlineKeyboardButton("💬 Обратная связь", callback_data="cab:feedback")
        ])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_feedback

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_feedback(update, context):
    query = update.callback_query
    if query and str(query.data or "") == "cab:feedback" and live23._admin_private(update):
        await query.answer()
        await query.message.reply_text(latest_feedback_summary_text())
        return
    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_feedback

# Безопасный предпросмотр только для Маши: /test feedback
_previous_test = bot.test


async def test_with_feedback_preview(update, context):
    arg = str(context.args[0]).lower().strip() if context.args else ""
    if arg not in {"feedback", "lessonfeedback", "отзыв", "опрос"}:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    await update.message.reply_text(
        "🧪 ТЕСТ — это видишь только ты. В группу ничего не отправлено.\n\n"
        "💬 Ребята, быстрая обратная связь после урока\n\n"
        "Как вам сегодня? Нажмите один вариант — это займёт буквально секунду 💗",
        reply_markup=_feedback_test_markup(),
    )


bot.test = test_with_feedback_preview


if __name__ == "__main__":
    live71.ensure_molar_access_tables()
    live70.ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live24.live18.ensure_acid_reminder_table()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live73.ensure_admin_task_view_state()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live66.seed_zlata_accounting_task()
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
    live76.restore_zlata_accounting_task()
    live74.ensure_notification_catchup_tables()
    ensure_lesson_feedback_tables()
    live56.log_probnik_cabinet_audit()
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
