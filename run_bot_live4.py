from datetime import datetime
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import run_bot_live3

live3 = run_bot_live3
live2 = live3.live2
run_bot = live3.run_bot
bot = live3.bot


def ensure_display_name_column():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
        if "display_name" not in columns:
            conn.execute("ALTER TABLE students ADD COLUMN display_name TEXT")
            conn.commit()


def get_active_students_with_display_names():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, '')) AS shown_name,
                   user_email
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()
    return rows


# Посещаемость должна использовать вручную заданное имя, если оно есть.
live3.get_active_students = get_active_students_with_display_names


def get_student_for_rename(student_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, display_name, user_name, user_email
            FROM students
            WHERE id = ? AND active = 1
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()


def set_display_name(student_id, new_name):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE students SET display_name = ?, updated_at = ? WHERE id = ?",
            (new_name, now, student_id),
        )
        conn.commit()


def clear_display_name(student_id):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE students SET display_name = NULL, updated_at = ? WHERE id = ?",
            (now, student_id),
        )
        conn.commit()


def rename_keyboard():
    rows = []
    for student_id, shown_name, email in get_active_students_with_display_names():
        label = (shown_name or email or "Ученик").strip()
        if len(label) > 40:
            label = label[:37] + "…"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"ren:pick:{student_id}")
        ])
    return InlineKeyboardMarkup(rows)


async def rename_student_command(update, context):
    if not bot.user_is_admin(update):
        await update.message.reply_text("Эта команда доступна только преподавателю.")
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Переименование учеников доступно только в личном чате со мной.")
        return

    students = get_active_students_with_display_names()
    if not students:
        await update.message.reply_text("В базе пока нет учеников.")
        return

    context.user_data.pop("rename_student_id", None)
    await update.message.reply_text(
        "Кого переименовать? Выбери ученика:",
        reply_markup=rename_keyboard(),
    )


async def rename_callback(update, context):
    query = update.callback_query
    if not query or not bot.user_is_admin(update):
        return
    await query.answer()

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "ren" or parts[1] != "pick":
        return

    student_id = int(parts[2])
    row = get_student_for_rename(student_id)
    if not row:
        await query.edit_message_text("Ученик больше не найден в активном списке.")
        return

    _, display_name, user_name, email = row
    current = display_name or user_name or email or "Ученик"
    context.user_data["rename_student_id"] = student_id
    await query.edit_message_text(
        f"Сейчас: {current}\n\n"
        "Напиши новое имя одним сообщением.\n"
        "Например: Аня\n\n"
        "Если хочешь вернуть имя из CoreApp — отправь один символ: -"
    )


async def rename_text_handler(update, context):
    if not update.message or not update.message.text:
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    student_id = context.user_data.get("rename_student_id")
    if not student_id:
        return

    text = update.message.text.strip()
    if text.startswith("/"):
        return

    row = get_student_for_rename(student_id)
    if not row:
        context.user_data.pop("rename_student_id", None)
        await update.message.reply_text("Ученик больше не найден.")
        return

    if text == "-":
        clear_display_name(student_id)
        updated = get_student_for_rename(student_id)
        restored = (updated[2] or updated[3] or "Ученик").strip()
        context.user_data.pop("rename_student_id", None)
        await update.message.reply_text(f"✅ Вернула имя из CoreApp: {restored}")
        return

    if len(text) > 80:
        await update.message.reply_text("Имя слишком длинное. Напиши до 80 символов.")
        return

    set_display_name(student_id, text)
    context.user_data.pop("rename_student_id", None)
    await update.message.reply_text(f"✅ Готово. Теперь в боте ученик отображается как: {text}")


def get_homework_status_for_lesson_with_display_name(lesson_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT coreapp_user_id, user_email,
                   coalesce(nullif(display_name, ''), nullif(user_name, '')) AS shown_name
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()
        submissions = conn.execute(
            """
            SELECT user_id, lower(user_email)
            FROM homework_submissions
            WHERE lesson_id = ?
            """,
            (lesson_id,),
        ).fetchall()

    submitted_ids = {str(row[0] or "").strip() for row in submissions if row[0]}
    submitted_emails = {bot.normalize_email(row[1]) for row in submissions if row[1]}
    done, missing = [], []
    for coreapp_user_id, email, shown_name in students:
        label = (shown_name or email or coreapp_user_id or "ученик").strip()
        is_done = (
            (coreapp_user_id and str(coreapp_user_id).strip() in submitted_ids)
            or (email and bot.normalize_email(email) in submitted_emails)
        )
        (done if is_done else missing).append(label)
    return done, missing


bot.get_homework_status_for_lesson = get_homework_status_for_lesson_with_display_name


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
            SELECT coalesce(nullif(s.display_name, ''), nullif(s.user_name, '')) AS shown_name,
                   s.user_email,
                   SUM(CASE WHEN ar.status = 'absent' AND sess.finalized = 1 THEN 1 ELSE 0 END) AS absences
            FROM students s
            LEFT JOIN attendance_records ar ON ar.student_id = s.id
            LEFT JOIN attendance_sessions sess ON sess.lesson_number = ar.lesson_number
            WHERE s.active = 1
            GROUP BY s.id, s.display_name, s.user_name, s.user_email
            ORDER BY absences DESC,
                     lower(coalesce(nullif(s.display_name, ''), nullif(s.user_name, ''), s.user_email, ''))
            """
        ).fetchall()

    lines = [
        "📊 Посещаемость курса",
        f"Отмечено занятий: {finalized_count} из {bot.TOTAL_LESSONS}",
        "",
    ]
    if not rows:
        lines.append("Пока нет учеников в базе.")
    else:
        for shown_name, email, absences in rows:
            lines.append(f"• {live3.student_label(shown_name, email)} — {int(absences or 0)} пропуск(а/ов)")

    await update.message.reply_text("\n".join(lines))


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    live3.ensure_attendance_tables()
    ensure_display_name_column()
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
    application.add_handler(bot.CommandHandler("attendance", live3.show_attendance))
    application.add_handler(bot.CommandHandler("attendancestats", attendance_stats))
    application.add_handler(bot.CommandHandler("rename", rename_student_command))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))
    application.add_handler(CallbackQueryHandler(live3.attendance_callback, pattern=r"^att:"))
    application.add_handler(CallbackQueryHandler(rename_callback, pattern=r"^ren:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))
    application.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, rename_text_handler))

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
