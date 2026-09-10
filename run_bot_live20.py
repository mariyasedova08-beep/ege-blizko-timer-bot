import sqlite3
from datetime import datetime

import run_bot_live19

live19 = run_bot_live19
live18 = live19.live18
live17 = live19.live17
live15 = live19.live15
live10 = live19.live10
live7 = live19.live7
live6 = live19.live6
live4 = live19.live4
live3 = live19.live3
live2 = live19.live2
run_bot = live19.run_bot
bot = live19.bot


# --- Безопасная привязка Telegram ученика к записи CoreApp ---

def _student_row_by_email(email):
    email = bot.normalize_email(email)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name,
                   telegram_user_id
            FROM students
            WHERE active = 1 AND lower(user_email) = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()


def _student_row_by_telegram(telegram_user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name
            FROM students
            WHERE active = 1 AND telegram_user_id = ?
            LIMIT 1
            """,
            (telegram_user_id,),
        ).fetchone()


def _link_existing_student(email, user):
    row = _student_row_by_email(email)
    if not row:
        return False, "Не нашла такую почту среди учеников курса. Проверь e-mail, который используется в CoreApp."

    student_id, shown_name, current_telegram_id = row
    already = _student_row_by_telegram(user.id)
    if already and already[0] != student_id:
        return False, "Этот Telegram уже привязан к другому ученику. Напиши Маше, чтобы она помогла с привязкой."

    if current_telegram_id is not None and int(current_telegram_id) != int(user.id):
        return False, "Эта запись ученика уже привязана к другому Telegram. Напиши Маше, чтобы она помогла с привязкой."

    full_name = " ".join(x for x in [user.first_name, user.last_name] if x).strip()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE students
            SET telegram_user_id = ?, telegram_username = ?, updated_at = ?
            WHERE id = ?
            """,
            (user.id, user.username or "", now, student_id),
        )
        conn.commit()
    return True, f"✅ Готово! Telegram привязан к ученику: {shown_name}. Теперь результаты тренажёров попадут в общую статистику."


async def safe_link_command(update, context):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Привязку нужно делать в личном чате с ботом 💗")
        return

    if context.args:
        ok, text = _link_existing_student(context.args[0], update.effective_user)
        context.user_data.pop("awaiting_student_email", None)
        await update.message.reply_text(text, reply_markup=live7.STUDENT_KEYBOARD if ok else None)
        return

    context.user_data["awaiting_student_email"] = True
    await update.message.reply_text(
        "📩 Напиши e-mail, который ты используешь в CoreApp.\n\n"
        "Он нужен только для того, чтобы связать твои результаты тренажёров с твоей учебной статистикой."
    )


_original_start_router = live7.start_router
_original_text_router = live7.student_text_router


async def linked_start_router(update, context):
    if (
        update.effective_chat.type == "private"
        and context.args
        and context.args[0].lower() in {"link", "connect"}
    ):
        context.user_data["awaiting_student_email"] = True
        await update.message.reply_text(
            "💗 Давай привяжем твой Telegram к курсу.\n\n"
            "Напиши e-mail, который ты используешь в CoreApp."
        )
        return
    await _original_start_router(update, context)


async def linked_text_router(update, context):
    if (
        update.effective_chat.type == "private"
        and context.user_data.get("awaiting_student_email")
        and update.message
        and update.message.text
    ):
        email = bot.normalize_email(update.message.text)
        if "@" not in email:
            await update.message.reply_text("Похоже, это не e-mail. Напиши адрес ещё раз.")
            return
        ok, text = _link_existing_student(email, update.effective_user)
        if ok:
            context.user_data.pop("awaiting_student_email", None)
            await update.message.reply_text(text, reply_markup=live7.STUDENT_KEYBOARD)
        else:
            await update.message.reply_text(text)
        return
    await _original_text_router(update, context)


live7.start_router = linked_start_router
live7.student_text_router = linked_text_router


async def link_status_command(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name,
                   telegram_user_id
            FROM students
            WHERE active = 1
            ORDER BY lower(shown_name)
            """
        ).fetchall()
    linked = [name for name, tid in rows if tid is not None]
    missing = [name for name, tid in rows if tid is None]
    lines = [f"🔗 Telegram привязан: {len(linked)} из {len(rows)}"]
    if missing:
        lines.extend(["", "Ещё не привязаны:"])
        lines.extend(f"• {name}" for name in missing)
    else:
        lines.extend(["", "✅ Все ученики привязаны."])
    text = "\n".join(lines)
    while text:
        if len(text) <= 3800:
            await update.message.reply_text(text)
            break
        split_at = text.rfind("\n", 0, 3800)
        if split_at < 1:
            split_at = 3800
        await update.message.reply_text(text[:split_at])
        text = text[split_at:].lstrip("\n")


async def link_announce_command(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        await update.message.reply_text("Не удалось отправить: CHAT_ID не настроен.")
        return
    me = await context.bot.get_me()
    keyboard = live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("🔗 Привязать Telegram", url=f"https://t.me/{me.username}?start=link")]
    ])
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "📊 <b>Подключаем статистику тренажёров</b>\n\n"
            "Чтобы результаты ваших тренировок попадали в общую статистику курса, "
            "нужно один раз привязать Telegram к своей записи в CoreApp.\n\n"
            "Нажмите кнопку ниже и отправьте боту e-mail, который используете в CoreApp 💗"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await update.message.reply_text("✅ Сообщение о привязке отправлено ребятам в группу.")


# --- Общая статистика: учитываем и тривиальные названия, и кислоты ---
_original_month_metrics = live15._student_month_metrics


def combined_month_metrics(conn, student, year, month, probnik_names):
    metrics = _original_month_metrics(conn, student, year, month, probnik_names)
    telegram_user_id = student[4]
    trivial_sessions = int(metrics.get("trainer_sessions") or 0)
    trivial_total = int(metrics.get("trainer_total") or 0)
    trivial_correct = int(metrics.get("trainer_correct") or 0)

    acid_sessions = acid_total = acid_correct = 0
    if telegram_user_id is not None:
        row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM acid_sessions
            WHERE telegram_user_id = ?
              AND finished_at IS NOT NULL
              AND finished_at LIKE ?
            """,
            (telegram_user_id, f"{year:04d}-{month:02d}%"),
        ).fetchone()
        acid_sessions, acid_total, acid_correct = [int(x or 0) for x in row]

    metrics["trivial_sessions"] = trivial_sessions
    metrics["acid_sessions"] = acid_sessions
    metrics["trainer_sessions"] = trivial_sessions + acid_sessions
    metrics["trainer_total"] = trivial_total + acid_total
    metrics["trainer_correct"] = trivial_correct + acid_correct
    return metrics


def combined_metrics_lines(metrics, compact=False):
    if metrics["probnik_count"]:
        probnik = f"{metrics['probnik_count']} шт. · ср. {live15._fmt(metrics['probnik_avg'])} · лучший {live15._fmt(metrics['probnik_best'])}"
    else:
        probnik = "не писал"

    if metrics["homework_count"]:
        hw = f"сдано {metrics['homework_count']}"
        if metrics["homework_accuracy"] is not None:
            hw += f" · точность {live15._fmt(metrics['homework_accuracy'])}%"
    else:
        hw = "нет сдач"

    if metrics["attendance_total"]:
        attendance_pct = metrics["attendance_present"] * 100 / metrics["attendance_total"]
        attendance = f"{metrics['attendance_present']}/{metrics['attendance_total']} · {live15._fmt(attendance_pct)}%"
    else:
        attendance = "занятия ещё не отмечены"

    if not metrics["trainer_linked"]:
        trainer = "Telegram не привязан"
    elif metrics["trainer_sessions"]:
        trainer_pct = metrics["trainer_correct"] * 100 / metrics["trainer_total"] if metrics["trainer_total"] else 0
        trainer = (
            f"{metrics['trainer_sessions']} трен. · {live15._fmt(trainer_pct)}% "
            f"(тривиальные {metrics.get('trivial_sessions', 0)}, кислоты {metrics.get('acid_sessions', 0)})"
        )
    else:
        trainer = "0 тренировок"

    return [
        f"📝 Пробники: {probnik}",
        f"🏠 ДЗ: {hw}",
        f"🎓 Посещение: {attendance}",
        f"🧪 Тренажёры: {trainer}",
    ]


live15._student_month_metrics = combined_month_metrics
live15._metrics_lines = combined_metrics_lines


async def test_acid_reminder_command(update, context):
    return await live19.test_acid_reminder_command(update, context)


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
    application.add_handler(bot.CommandHandler("link", safe_link_command))
    application.add_handler(bot.CommandHandler("linkstatus", link_status_command))
    application.add_handler(bot.CommandHandler("linkannounce", link_announce_command))
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

    application.add_handler(bot.CommandHandler("testacidreminder", test_acid_reminder_command))
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
