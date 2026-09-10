import re
import sqlite3
from datetime import datetime

import run_bot_live21

live21 = run_bot_live21
live20 = live21.live20
bot = live20.bot

live19 = live20.live19
live18 = live20.live18
live17 = live20.live17
live15 = live20.live15
live10 = live20.live10
live7 = live20.live7
live6 = live20.live6
live4 = live20.live4
live3 = live20.live3
live2 = live20.live2
run_bot = live20.run_bot


def _norm_name(value):
    value = str(value or "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value)
    return " ".join(value.split())


def _acid_item_label(item_id):
    item = live17.ACID_BY_ID.get(item_id)
    if not item:
        return item_id
    return f"{item['acid_formula']} — {item['acid_names'][0]}"


def _acid_student_metrics(conn, telegram_user_id, year, month):
    prefix = f"{year:04d}-{month:02d}%"
    sessions, questions, correct = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM acid_sessions
        WHERE telegram_user_id = ?
          AND finished_at IS NOT NULL
          AND finished_at LIKE ?
        """,
        (telegram_user_id, prefix),
    ).fetchone()

    attempts, attempt_correct = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(correct), 0)
        FROM acid_attempts
        WHERE telegram_user_id = ? AND created_at LIKE ?
        """,
        (telegram_user_id, prefix),
    ).fetchone()

    weak_rows = conn.execute(
        """
        SELECT item_id,
               SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
               COUNT(*) AS total_count
        FROM acid_attempts
        WHERE telegram_user_id = ? AND created_at LIKE ?
        GROUP BY item_id
        HAVING wrong_count > 0
        ORDER BY wrong_count DESC, (1.0 * wrong_count / total_count) DESC, total_count DESC
        LIMIT 3
        """,
        (telegram_user_id, prefix),
    ).fetchall()

    attempts = int(attempts or 0)
    attempt_correct = int(attempt_correct or 0)
    accuracy = round(attempt_correct * 100 / attempts) if attempts else None

    return {
        "sessions": int(sessions or 0),
        "questions": int(questions or 0),
        "correct": int(correct or 0),
        "attempts": attempts,
        "attempt_correct": attempt_correct,
        "accuracy": accuracy,
        "weak": weak_rows,
    }


def _active_students(conn):
    return conn.execute(
        """
        SELECT id,
               coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name,
               telegram_user_id
        FROM students
        WHERE active = 1
        ORDER BY lower(shown_name)
        """
    ).fetchall()


def _resolve_student(students, query):
    q = _norm_name(query)
    if not q:
        return None
    exact = [s for s in students if _norm_name(s[1]) == q]
    if len(exact) == 1:
        return exact[0]
    partial = [s for s in students if q in _norm_name(s[1]) or _norm_name(s[1]) in q]
    return partial[0] if len(partial) == 1 else None


def _month_title(year, month):
    return f"{live15.MONTH_NAMES[month]} {year}"


def acidstats_text(year, month, query_name=None):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = _active_students(conn)

        if query_name:
            student = _resolve_student(students, query_name)
            if student is None:
                return "Не нашла ученика. Используй имя так, как оно отображается в боте."
            _, name, telegram_user_id = student
            lines = [f"🧪 Кислоты — {_month_title(year, month)}", f"👩‍🎓 {name}", ""]
            if telegram_user_id is None:
                lines.append("🔗 Telegram не привязан")
                return "\n".join(lines)
            m = _acid_student_metrics(conn, telegram_user_id, year, month)
            if not m["sessions"]:
                lines.append("Тренировок за месяц пока нет.")
                return "\n".join(lines)
            lines.extend([
                f"Тренировок: {m['sessions']}",
                f"Ответов: {m['attempt_correct']}/{m['attempts']}",
                f"Точность: {m['accuracy']}%",
            ])
            if m["weak"]:
                lines.extend(["", "⚠️ Чаще всего ошибается:"])
                for item_id, wrong, total in m["weak"]:
                    pct = round(int(wrong) * 100 / int(total)) if total else 0
                    lines.append(f"• {_acid_item_label(item_id)} — ошибок {wrong}/{total} ({pct}%)")
            return "\n".join(lines)

        linked = [s for s in students if s[2] is not None]
        total_sessions = total_attempts = total_correct = 0
        blocks = []
        for _, name, telegram_user_id in students:
            if telegram_user_id is None:
                blocks.append(f"👩‍🎓 {name}\n🔗 Telegram не привязан")
                continue
            m = _acid_student_metrics(conn, telegram_user_id, year, month)
            total_sessions += m["sessions"]
            total_attempts += m["attempts"]
            total_correct += m["attempt_correct"]
            if not m["sessions"]:
                blocks.append(f"👩‍🎓 {name}\n🧪 0 тренировок")
                continue
            line = f"👩‍🎓 {name}\n🧪 {m['sessions']} трен. · {m['accuracy']}%"
            if m["weak"]:
                weak_labels = ", ".join(_acid_item_label(row[0]).split(" — ")[0] for row in m["weak"][:2])
                line += f"\n⚠️ Сложнее: {weak_labels}"
            blocks.append(line)

        group_accuracy = round(total_correct * 100 / total_attempts) if total_attempts else 0
        lines = [
            f"🧪 Кислоты — {_month_title(year, month)}",
            f"🔗 Telegram привязан: {len(linked)} из {len(students)}",
            f"Всего тренировок: {total_sessions} · точность группы: {group_accuracy}%",
            "",
            "\n\n".join(blocks),
        ]
        return "\n".join(lines).rstrip()


async def acidstats_command(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    year, month, name_parts = live15._month_from_args(context.args)
    if not (2025 <= year <= 2030 and 1 <= month <= 12):
        await update.message.reply_text("Формат: /acidstats 09.2026 или /acidstats ИМЯ 09.2026")
        return
    query_name = " ".join(name_parts).strip() or None
    text = acidstats_text(year, month, query_name)
    while text:
        if len(text) <= 3800:
            await update.message.reply_text(text)
            break
        split_at = text.rfind("\n\n", 0, 3800)
        if split_at < 1:
            split_at = text.rfind("\n", 0, 3800)
        if split_at < 1:
            split_at = 3800
        await update.message.reply_text(text[:split_at])
        text = text[split_at:].lstrip("\n")


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    live3.ensure_attendance_tables()
    live4.ensure_display_name_column()
    live6.ensure_tutor_tables()
    live7.ensure_trivial_tables()
    live10.ensure_probnik_tables()
    live17.ensure_acid_tables()
    live18.ensure_acid_reminder_table()

    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", live7.start_router))
    application.add_handler(bot.CommandHandler("ege", bot.ege))
    application.add_handler(bot.CommandHandler("weeks", bot.weeks))
    application.add_handler(bot.CommandHandler("progress", bot.progress))
    application.add_handler(bot.CommandHandler("chatid", bot.chatid))
    application.add_handler(bot.CommandHandler("threadid", bot.threadid))
    application.add_handler(bot.CommandHandler("myid", bot.myid))
    application.add_handler(bot.CommandHandler("link", live20.safe_link_command))
    application.add_handler(bot.CommandHandler("linkstatus", live20.link_status_command))
    application.add_handler(bot.CommandHandler("linkannounce", live20.link_announce_command))
    application.add_handler(bot.CommandHandler("corestatus", bot.corestatus))
    application.add_handler(bot.CommandHandler("homeworkstatus", bot.homeworkstatus))
    application.add_handler(bot.CommandHandler("attendance", live3.show_attendance))
    application.add_handler(bot.CommandHandler("attendancestats", live4.attendance_stats))
    application.add_handler(bot.CommandHandler("rename", live6.rename_command_wrapper))

    application.add_handler(bot.CommandHandler("tutorinvite", live6.tutor_invite))
    application.add_handler(bot.CommandHandler("tutorlink", live6.tutor_link))
    application.add_handler(bot.CommandHandler("tutorstatus", live6.tutor_status))
    application.add_handler(bot.CommandHandler("tutorreminder", live6.tutor_reminder_command))
    application.add_handler(bot.CommandHandler("tutorreminders", live6.tutor_reminders_list))
    application.add_handler(bot.CommandHandler("tutordel", live6.tutor_delete))
    application.add_handler(bot.CommandHandler("tutortest", live6.tutor_test))
    application.add_handler(bot.CommandHandler("tutorcancel", live6.tutor_cancel))

    application.add_handler(bot.CommandHandler("trivial", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivial10", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivialmistakes", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivialstats", live7.trivial_stats_command))
    application.add_handler(bot.CommandHandler("trivialtop", live7.trivial_top_command))
    application.add_handler(bot.CommandHandler("trivialannounce", live7.trivial_announce_command))
    application.add_handler(bot.CommandHandler("trivialtime", live7.set_trivial_time))
    application.add_handler(bot.CommandHandler("trivialfriday", live7.trivial_friday_status))

    application.add_handler(bot.CommandHandler("probnikstats", live10.probnikstats_command))
    application.add_handler(bot.CommandHandler("student", live10.student_command))
    application.add_handler(bot.CommandHandler("weak", live10.weak_command))
    application.add_handler(bot.CommandHandler("sheetsstatus", live10.sheetsstatus_command))
    application.add_handler(bot.CommandHandler("monthstats", live15.monthstats_command))
    application.add_handler(bot.CommandHandler("monthly", live15.monthstats_command))
    application.add_handler(bot.CommandHandler("acidstats", acidstats_command))

    application.add_handler(bot.CommandHandler("testacidreminder", live20.test_acid_reminder_command))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))

    application.add_handler(live7.CallbackQueryHandler(live7.trivial_callback, pattern=r"^triv:"))
    application.add_handler(live7.CallbackQueryHandler(live3.attendance_callback, pattern=r"^att:"))
    application.add_handler(live7.CallbackQueryHandler(live4.rename_callback, pattern=r"^ren:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))
    application.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, live7.student_text_router))

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
    application.job_queue.run_repeating(live6.tutor_reminder_tick, interval=30, first=10)
    application.job_queue.run_repeating(live7.friday_trivial_tick, interval=30, first=15)

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
