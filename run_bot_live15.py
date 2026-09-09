import re
import sqlite3
from datetime import datetime

import run_bot_live14

live14 = run_bot_live14
live10 = live14.live10
live9 = live10.live9
live7 = live10.live7
live6 = live10.live6
live4 = live10.live4
live3 = live10.live3
live2 = live10.live2
run_bot = live10.run_bot
bot = live10.bot

MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}
MONTH_ALIASES = {
    "январь": 1, "января": 1,
    "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3,
    "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7,
    "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9,
    "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11,
    "декабрь": 12, "декабря": 12,
}


def _admin_private(update):
    return update.effective_chat.type == "private" and bot.user_is_admin(update)


def _norm_name(value):
    value = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _fmt(value, digits=1):
    if value is None:
        return "—"
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return str(round(value, digits)).replace(".", ",")


def _parse_month_token(token, default_year=None):
    token = str(token or "").strip().lower()
    if not token:
        return None
    now = datetime.now(bot.TIMEZONE)
    year_default = default_year or now.year

    m = re.fullmatch(r"(0?[1-9]|1[0-2])[.\-/](20\d{2})", token)
    if m:
        return int(m.group(2)), int(m.group(1))

    m = re.fullmatch(r"(20\d{2})[.\-/](0?[1-9]|1[0-2])", token)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.fullmatch(r"(0?[1-9]|1[0-2])", token)
    if m:
        return year_default, int(m.group(1))

    if token in MONTH_ALIASES:
        return year_default, MONTH_ALIASES[token]
    return None


def _month_from_args(args):
    now = datetime.now(bot.TIMEZONE)
    if not args:
        return now.year, now.month, []

    args = list(args)
    parsed = _parse_month_token(args[-1])
    if parsed:
        return parsed[0], parsed[1], args[:-1]

    if len(args) >= 2 and str(args[-1]).isdigit() and len(str(args[-1])) == 4:
        year = int(args[-1])
        parsed = _parse_month_token(args[-2], default_year=year)
        if parsed:
            return year, parsed[1], args[:-2]

    return now.year, now.month, args


def _active_students(conn):
    return conn.execute(
        """
        SELECT id,
               coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name,
               coreapp_user_id, user_email, telegram_user_id
        FROM students
        WHERE active = 1
        ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
        """
    ).fetchall()


def _probnik_names_for_month(conn, year, month):
    suffix = f"{month:02d}.{year:04d}"
    return [r[0] for r in conn.execute(
        """
        SELECT DISTINCT student_name
        FROM probnik_results
        WHERE substr(event_date, 4, 7) = ?
        ORDER BY lower(student_name)
        """,
        (suffix,),
    ).fetchall()]


def _best_probnik_name(student_name, available_names):
    target = _norm_name(student_name)
    exact = [n for n in available_names if _norm_name(n) == target]
    if len(exact) == 1:
        return exact[0]
    partial = [n for n in available_names if target and (_norm_name(n) in target or target in _norm_name(n))]
    if len(partial) == 1:
        return partial[0]
    return None


def _student_month_metrics(conn, student, year, month, probnik_names):
    student_id, shown_name, coreapp_user_id, email, telegram_user_id = student
    iso_prefix = f"{year:04d}-{month:02d}"
    probnik_suffix = f"{month:02d}.{year:04d}"

    probnik_name = _best_probnik_name(shown_name, probnik_names)
    probnik_rows = []
    if probnik_name:
        probnik_rows = conn.execute(
            """
            SELECT event_name, secondary_score
            FROM probnik_results
            WHERE student_name = ?
              AND substr(event_date, 4, 7) = ?
              AND secondary_score IS NOT NULL
            ORDER BY substr(event_date, 1, 2)
            """,
            (probnik_name, probnik_suffix),
        ).fetchall()
    probnik_scores = [float(r[1]) for r in probnik_rows]

    hw_rows = conn.execute(
        """
        SELECT id, lesson_id, correct_count, total_count, received_at
        FROM homework_submissions
        WHERE received_at LIKE ?
          AND (
                (? != '' AND user_id = ?)
                OR (? != '' AND lower(user_email) = lower(?))
              )
        ORDER BY received_at, id
        """,
        (
            iso_prefix + "%",
            str(coreapp_user_id or ""), str(coreapp_user_id or ""),
            str(email or ""), str(email or ""),
        ),
    ).fetchall()
    latest_by_lesson = {}
    for row in hw_rows:
        row_id, lesson_id, correct_count, total_count, received_at = row
        key = str(lesson_id or "").strip() or f"row:{row_id}"
        latest_by_lesson[key] = row
    homework = list(latest_by_lesson.values())
    hw_ratios = []
    for _, _, correct_count, total_count, _ in homework:
        correct = _num(correct_count)
        total = _num(total_count)
        if correct is not None and total and total > 0:
            hw_ratios.append(correct * 100 / total)

    attendance_total = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance_sessions
        WHERE finalized = 1 AND lesson_date LIKE ?
        """,
        (iso_prefix + "%",),
    ).fetchone()[0]
    attendance_present = conn.execute(
        """
        SELECT COUNT(*)
        FROM attendance_records ar
        JOIN attendance_sessions sess ON sess.lesson_number = ar.lesson_number
        WHERE ar.student_id = ?
          AND sess.finalized = 1
          AND sess.lesson_date LIKE ?
          AND ar.status = 'present'
        """,
        (student_id, iso_prefix + "%"),
    ).fetchone()[0]

    trainer_sessions = 0
    trainer_total = 0
    trainer_correct = 0
    if telegram_user_id is not None:
        trainer_sessions, trainer_total, trainer_correct = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM trivial_sessions
            WHERE telegram_user_id = ?
              AND finished_at IS NOT NULL
              AND finished_at LIKE ?
            """,
            (telegram_user_id, iso_prefix + "%"),
        ).fetchone()

    return {
        "name": shown_name,
        "probnik_count": len(probnik_scores),
        "probnik_avg": (sum(probnik_scores) / len(probnik_scores)) if probnik_scores else None,
        "probnik_best": max(probnik_scores) if probnik_scores else None,
        "homework_count": len(homework),
        "homework_accuracy": (sum(hw_ratios) / len(hw_ratios)) if hw_ratios else None,
        "attendance_present": int(attendance_present or 0),
        "attendance_total": int(attendance_total or 0),
        "trainer_linked": telegram_user_id is not None,
        "trainer_sessions": int(trainer_sessions or 0),
        "trainer_total": int(trainer_total or 0),
        "trainer_correct": int(trainer_correct or 0),
    }


def _metrics_lines(metrics, compact=False):
    if metrics["probnik_count"]:
        probnik = f"{metrics['probnik_count']} шт. · ср. {_fmt(metrics['probnik_avg'])} · лучший {_fmt(metrics['probnik_best'])}"
    else:
        probnik = "не писал"

    if metrics["homework_count"]:
        hw = f"сдано {metrics['homework_count']}"
        if metrics["homework_accuracy"] is not None:
            hw += f" · точность {_fmt(metrics['homework_accuracy'])}%"
    else:
        hw = "нет сдач"

    if metrics["attendance_total"]:
        attendance_pct = metrics["attendance_present"] * 100 / metrics["attendance_total"]
        attendance = f"{metrics['attendance_present']}/{metrics['attendance_total']} · {_fmt(attendance_pct)}%"
    else:
        attendance = "занятия ещё не отмечены"

    if not metrics["trainer_linked"]:
        trainer = "Telegram не привязан"
    elif metrics["trainer_sessions"]:
        trainer_pct = metrics["trainer_correct"] * 100 / metrics["trainer_total"] if metrics["trainer_total"] else 0
        trainer = f"{metrics['trainer_sessions']} трен. · {_fmt(trainer_pct)}%"
    else:
        trainer = "0 тренировок"

    return [
        f"📝 Пробники: {probnik}",
        f"🏠 ДЗ: {hw}",
        f"🎓 Посещение: {attendance}",
        f"🧪 Тренажёры: {trainer}",
    ]


def _resolve_one_student(students, query):
    query_norm = _norm_name(query)
    if not query_norm:
        return None
    exact = [s for s in students if _norm_name(s[1]) == query_norm]
    if len(exact) == 1:
        return exact[0]
    partial = [s for s in students if query_norm in _norm_name(s[1]) or _norm_name(s[1]) in query_norm]
    if len(partial) == 1:
        return partial[0]
    return None


def monthly_report_text(year, month, query_name=None):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = _active_students(conn)
        probnik_names = _probnik_names_for_month(conn, year, month)

        if query_name:
            student = _resolve_one_student(students, query_name)
            if student is None:
                return "Не нашла ученика. Используй имя так, как оно отображается в боте."
            metrics = _student_month_metrics(conn, student, year, month, probnik_names)
            lines = [
                f"📊 {MONTH_NAMES[month]} {year}",
                f"👩‍🎓 {metrics['name']}",
                "",
            ]
            lines.extend(_metrics_lines(metrics))
            return "\n".join(lines)

        lines = [
            f"📊 Статистика за {MONTH_NAMES[month].lower()} {year}",
            "",
        ]
        if not students:
            lines.append("В базе пока нет активных учеников.")
            return "\n".join(lines)

        for student in students:
            metrics = _student_month_metrics(conn, student, year, month, probnik_names)
            lines.append(f"👩‍🎓 {metrics['name']}")
            lines.extend(_metrics_lines(metrics, compact=True))
            lines.append("")
        return "\n".join(lines).rstrip()


async def monthstats_command(update, context):
    if not _admin_private(update):
        return
    year, month, name_parts = _month_from_args(context.args)
    if not (2025 <= year <= 2030 and 1 <= month <= 12):
        await update.message.reply_text("Формат месяца: /monthstats 09.2026")
        return
    query_name = " ".join(name_parts).strip() or None
    text = monthly_report_text(year, month, query_name=query_name)
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
    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", live7.start_router))
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
    application.add_handler(bot.CommandHandler("monthstats", monthstats_command))
    application.add_handler(bot.CommandHandler("monthly", monthstats_command))

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
