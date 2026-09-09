from datetime import datetime
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import run_bot_live2

live2 = run_bot_live2
run_bot = live2.run_bot
bot = live2.bot


def ensure_attendance_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                lesson_number INTEGER PRIMARY KEY,
                lesson_date TEXT NOT NULL,
                finalized INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance_records (
                lesson_number INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present', 'absent')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (lesson_number, student_id)
            )
            """
        )
        conn.commit()


def lesson_date_by_number(lesson_number):
    if 1 <= lesson_number <= len(run_bot.COURSE_LESSON_DATES):
        return run_bot.COURSE_LESSON_DATES[lesson_number - 1]
    return None


def default_lesson_number():
    today = bot.today_moscow()
    dates = run_bot.COURSE_LESSON_DATES
    if today <= dates[0]:
        return 1
    for index, lesson_date in enumerate(dates, start=1):
        if lesson_date == today:
            return index
        if lesson_date > today:
            return max(1, index - 1)
    return len(dates)


def ensure_attendance_session(lesson_number):
    lesson_date = lesson_date_by_number(lesson_number)
    if lesson_date is None:
        return
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO attendance_sessions (lesson_number, lesson_date, finalized, updated_at)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(lesson_number) DO UPDATE SET lesson_date = excluded.lesson_date
            """,
            (lesson_number, lesson_date.isoformat(), now),
        )
        conn.commit()


def get_active_students():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, user_name, user_email
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()
    return rows


def attendance_state(lesson_number):
    ensure_attendance_session(lesson_number)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        finalized_row = conn.execute(
            "SELECT finalized FROM attendance_sessions WHERE lesson_number = ?",
            (lesson_number,),
        ).fetchone()
        records = conn.execute(
            "SELECT student_id, status FROM attendance_records WHERE lesson_number = ?",
            (lesson_number,),
        ).fetchall()
    finalized = bool(finalized_row and finalized_row[0])
    return finalized, {student_id: status for student_id, status in records}


def student_label(name, email):
    return (name or email or "Ученик").strip()


def build_attendance_keyboard(lesson_number):
    students = get_active_students()
    finalized, records = attendance_state(lesson_number)
    rows = []

    for student_id, name, email in students:
        status = records.get(student_id, "present")
        icon = "❌" if status == "absent" else "✅"
        label = student_label(name, email)
        if len(label) > 36:
            label = label[:33] + "…"
        rows.append([
            InlineKeyboardButton(
                f"{icon} {label}",
                callback_data=f"att:toggle:{lesson_number}:{student_id}",
            )
        ])

    nav_row = []
    if lesson_number > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"att:nav:{lesson_number - 1}"))
    nav_row.append(InlineKeyboardButton("💾 Сохранить", callback_data=f"att:save:{lesson_number}"))
    if lesson_number < bot.TOTAL_LESSONS:
        nav_row.append(InlineKeyboardButton("Следующий ➡️", callback_data=f"att:nav:{lesson_number + 1}"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(rows), finalized, records, len(students)


def attendance_text(lesson_number, finalized, records, student_count):
    lesson_date = lesson_date_by_number(lesson_number)
    absent_count = sum(1 for status in records.values() if status == "absent")
    date_text = lesson_date.strftime("%d.%m.%Y") if lesson_date else ""
    status_text = "✅ Сохранено" if finalized else "📝 Не сохранено"
    return (
        f"🧪 Посещаемость — урок №{lesson_number}\n"
        f"📅 {date_text}\n\n"
        "Нажми на тех, кто отсутствует.\n"
        "✅ — присутствует   ❌ — отсутствует\n\n"
        f"Отсутствуют: {absent_count} из {student_count}\n"
        f"{status_text}"
    )


async def show_attendance(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Посещаемость открывается только в личном чате со мной.")
        return

    lesson_number = default_lesson_number()
    if context.args:
        try:
            requested = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Напишите номер урока от 1 до 108, например: /attendance 12")
            return
        if not 1 <= requested <= bot.TOTAL_LESSONS:
            await update.message.reply_text("Номер урока должен быть от 1 до 108.")
            return
        lesson_number = requested

    keyboard, finalized, records, student_count = build_attendance_keyboard(lesson_number)
    await update.message.reply_text(
        attendance_text(lesson_number, finalized, records, student_count),
        reply_markup=keyboard,
    )


def set_attendance_status(lesson_number, student_id, status):
    ensure_attendance_session(lesson_number)
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO attendance_records (lesson_number, student_id, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(lesson_number, student_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (lesson_number, student_id, status, now),
        )
        conn.commit()


def finalize_attendance(lesson_number):
    ensure_attendance_session(lesson_number)
    students = get_active_students()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for student_id, _, _ in students:
            conn.execute(
                """
                INSERT OR IGNORE INTO attendance_records
                    (lesson_number, student_id, status, updated_at)
                VALUES (?, ?, 'present', ?)
                """,
                (lesson_number, student_id, now),
            )
        conn.execute(
            """
            UPDATE attendance_sessions
            SET finalized = 1, updated_at = ?
            WHERE lesson_number = ?
            """,
            (now, lesson_number),
        )
        conn.commit()


async def attendance_callback(update, context):
    query = update.callback_query
    if not query or not bot.user_is_admin(update):
        return

    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 3 or parts[0] != "att":
        return

    action = parts[1]
    lesson_number = int(parts[2])

    if action == "toggle" and len(parts) == 4:
        student_id = int(parts[3])
        _, records = attendance_state(lesson_number)
        current = records.get(student_id, "present")
        new_status = "present" if current == "absent" else "absent"
        set_attendance_status(lesson_number, student_id, new_status)

    elif action == "save":
        finalize_attendance(lesson_number)
        await query.answer("Посещаемость сохранена ✅", show_alert=False)

    elif action == "nav":
        pass
    else:
        return

    keyboard, finalized, records, student_count = build_attendance_keyboard(lesson_number)
    await query.edit_message_text(
        attendance_text(lesson_number, finalized, records, student_count),
        reply_markup=keyboard,
    )


async def attendance_stats(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Статистика посещаемости доступна только в личном чате.")
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        finalized_count = conn.execute(
            "SELECT COUNT(*) FROM attendance_sessions WHERE finalized = 1"
        ).fetchone()[0]
        rows = conn.execute(
            """
            SELECT s.user_name, s.user_email,
                   SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) AS absences
            FROM students s
            LEFT JOIN attendance_records ar ON ar.student_id = s.id
            LEFT JOIN attendance_sessions sess
                ON sess.lesson_number = ar.lesson_number AND sess.finalized = 1
            WHERE s.active = 1
            GROUP BY s.id, s.user_name, s.user_email
            ORDER BY absences DESC, lower(coalesce(nullif(s.user_name, ''), s.user_email, ''))
            """
        ).fetchall()

    lines = [
        "📊 Посещаемость курса",
        f"Отмечено занятий: {finalized_count} из {bot.TOTAL_LESSONS}",
    ]
    if not rows:
        lines.append("\nПока нет учеников в базе.")
    else:
        lines.append("")
        for name, email, absences in rows:
            lines.append(f"• {student_label(name, email)} — {int(absences or 0)} пропуск(а/ов)")

    await update.message.reply_text("\n".join(lines))


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    ensure_attendance_tables()
    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", bot.start))
    application.add_handler(bot.CommandHandler("ege", bot.ege))
    application.add_handler(bot.CommandHandler("weeks", bot.weeks))
    application.add_handler(bot.CommandHandler("progress", bot.progress))
    application.add_handler(bot.CommandHandler("chatid", bot.chatid))
    application.add_handler(bot.CommandHandler("threadid", bot.threadid))
    application.add_handler(bot.CommandHandler("myid", bot.myid))
    application.add_handler(bot.CommandHandler("link", bot.link))
    application.add_handler(bot.CommandHandler("corestatus", bot.corestatus))
    application.add_handler(bot.CommandHandler("homeworkstatus", bot.homeworkstatus))
    application.add_handler(bot.CommandHandler("attendance", show_attendance))
    application.add_handler(bot.CommandHandler("attendancestats", attendance_stats))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))
    application.add_handler(CallbackQueryHandler(attendance_callback, pattern=r"^att:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))

    application.job_queue.run_daily(
        bot.daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        bot.daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 2, 6),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(1, 3),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 6),
    )
    application.job_queue.run_daily(
        run_bot.probnik_daily_reminder,
        time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        live2.probnik_saturday_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(6,),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
