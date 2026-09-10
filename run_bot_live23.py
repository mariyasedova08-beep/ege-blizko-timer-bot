import sqlite3
from datetime import datetime

import run_bot_live22

live22 = run_bot_live22
live21 = live22.live21
live20 = live22.live20
live19 = live22.live19
live18 = live22.live18
live17 = live22.live17
live15 = live22.live15
live10 = live22.live10
live7 = live22.live7
live6 = live22.live6
live4 = live22.live4
live3 = live22.live3
live2 = live22.live2
run_bot = live22.run_bot
bot = live22.bot


ADMIN_KEYBOARD = live7.ReplyKeyboardMarkup(
    [["👩‍🏫 Кабинет Маши"]],
    resize_keyboard=True,
)


def _admin_private(update):
    return update.effective_chat.type == "private" and bot.user_is_admin(update)


def cabinet_markup():
    return live7.InlineKeyboardMarkup([
        [
            live7.InlineKeyboardButton("📊 Статистика месяца", callback_data="cab:month"),
            live7.InlineKeyboardButton("🎓 Посещение", callback_data="cab:attendance"),
        ],
        [
            live7.InlineKeyboardButton("📝 Пробники", callback_data="cab:probmenu"),
            live7.InlineKeyboardButton("🏠 ДЗ / CoreApp", callback_data="cab:homework"),
        ],
        [
            live7.InlineKeyboardButton("🧪 Тренажёры", callback_data="cab:trainmenu"),
            live7.InlineKeyboardButton("🔗 Ученики", callback_data="cab:linkmenu"),
        ],
        [
            live7.InlineKeyboardButton("🔄 Синхронизация", callback_data="cab:sync"),
            live7.InlineKeyboardButton("⏰ Таймер курса", callback_data="cab:timer"),
        ],
    ])


def cabinet_text():
    now = datetime.now(bot.TIMEZONE)
    return (
        "👩‍🏫 <b>Кабинет Маши</b>\n\n"
        f"Сегодня {now.strftime('%d.%m.%Y')}\n"
        "Выбирай нужный раздел — команды помнить больше не нужно 💗"
    )


async def show_cabinet(update, context):
    if not _admin_private(update):
        return
    await update.effective_message.reply_text(
        cabinet_text(),
        parse_mode="HTML",
        reply_markup=cabinet_markup(),
    )


async def cabinet_command(update, context):
    if not _admin_private(update):
        return
    await update.message.reply_text("Кабинет закреплён на нижней клавиатуре 👇", reply_markup=ADMIN_KEYBOARD)
    await show_cabinet(update, context)


async def _send_chunks(message, text, parse_mode=None):
    text = str(text or "")
    while text:
        if len(text) <= 3800:
            await message.reply_text(text, parse_mode=parse_mode)
            break
        split_at = text.rfind("\n\n", 0, 3800)
        if split_at < 1:
            split_at = text.rfind("\n", 0, 3800)
        if split_at < 1:
            split_at = 3800
        await message.reply_text(text[:split_at], parse_mode=parse_mode)
        text = text[split_at:].lstrip("\n")


def _current_month():
    now = datetime.now(bot.TIMEZONE)
    return now.year, now.month


def homework_summary_text():
    lesson = bot.get_latest_lesson()
    if not lesson:
        return (
            "🏠 ДЗ / CoreApp\n\n"
            "Пока в базе нет ни одной завершённой работы.\n"
            "Новые завершённые уроки будут приходить через webhook, а старые можно загрузить XLSX-файлом мониторинга CoreApp."
        )
    lesson_id, lesson_name = lesson
    done, missing = bot.get_homework_status_for_lesson(lesson_id)
    lines = [
        "🏠 ДЗ / CoreApp",
        "",
        f"Последний урок: {lesson_name or 'урок'}",
        f"✅ Сдали: {len(done)}",
        f"⏳ Не сдали: {len(missing)}",
    ]
    if missing:
        lines.extend(["", "Пока не сдали:"])
        lines.extend(f"• {name}" for name in missing)
    return "\n".join(lines)


def link_status_text():
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
    return "\n".join(lines)


def trivial_month_text(year, month):
    prefix = f"{year:04d}-{month:02d}%"
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик') AS shown_name,
                   telegram_user_id
            FROM students
            WHERE active = 1
            ORDER BY lower(shown_name)
            """
        ).fetchall()
        blocks = []
        total_sessions = total_q = total_correct = 0
        for name, telegram_user_id in students:
            if telegram_user_id is None:
                blocks.append(f"👩‍🎓 {name}\n🔗 Telegram не привязан")
                continue
            sessions, questions, correct = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
                FROM trivial_sessions
                WHERE telegram_user_id = ?
                  AND finished_at IS NOT NULL
                  AND finished_at LIKE ?
                """,
                (telegram_user_id, prefix),
            ).fetchone()
            sessions = int(sessions or 0)
            questions = int(questions or 0)
            correct = int(correct or 0)
            total_sessions += sessions
            total_q += questions
            total_correct += correct
            if sessions:
                pct = round(correct * 100 / questions) if questions else 0
                blocks.append(f"👩‍🎓 {name}\n🧪 {sessions} трен. · {pct}%")
            else:
                blocks.append(f"👩‍🎓 {name}\n🧪 0 тренировок")
    group_pct = round(total_correct * 100 / total_q) if total_q else 0
    month_name = live15.MONTH_NAMES[month].lower()
    return (
        f"🧪 Тривиальные названия — {month_name} {year}\n"
        f"Всего тренировок: {total_sessions} · точность группы: {group_pct}%\n\n"
        + "\n\n".join(blocks)
    )


def sync_status_text():
    total, linked = bot.get_student_counts()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT last_synced_at, last_rows, last_students, source_title FROM probnik_sync_status WHERE id = 1"
        ).fetchone()
        hw_count = conn.execute("SELECT COUNT(*) FROM homework_submissions").fetchone()[0]
    if row:
        synced_at, rows_count, students_count, _ = row
    else:
        synced_at, rows_count, students_count = None, 0, 0
    if synced_at:
        try:
            dt = datetime.fromisoformat(synced_at)
            synced_text = dt.astimezone(bot.TIMEZONE).strftime("%d.%m.%Y %H:%M")
        except Exception:
            synced_text = str(synced_at)
    else:
        synced_text = "ещё не было"
    return (
        "🔄 Синхронизация\n\n"
        f"🏠 CoreApp: {total} учеников · {hw_count} записей по урокам/ДЗ\n"
        f"🔗 Telegram: {linked} из {total} привязано\n\n"
        f"📝 Google-таблица пробников:\n"
        f"последняя синхронизация — {synced_text}\n"
        f"результатов — {rows_count} · учеников — {students_count}"
    )


async def send_link_announcement_from_cabinet(context):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False
    me = await context.bot.get_me()
    keyboard = live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("🔗 Привязать Telegram", url=f"https://t.me/{me.username}?start=link")]
    ])
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "📊 <b>Подключаем статистику тренажёров</b>\n\n"
            "Чтобы результаты тренировок попадали в общую статистику курса, "
            "нужно один раз привязать Telegram к своей записи в CoreApp.\n\n"
            "Нажмите кнопку ниже и отправьте боту e-mail, который используете в CoreApp 💗"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return True


async def cabinet_callback(update, context):
    query = update.callback_query
    if not query or not _admin_private(update):
        return
    await query.answer()
    action = query.data.split(":", 1)[1] if ":" in query.data else ""

    if action == "back":
        await query.edit_message_text(cabinet_text(), parse_mode="HTML", reply_markup=cabinet_markup())
        return

    if action == "month":
        year, month = _current_month()
        await _send_chunks(query.message, live15.monthly_report_text(year, month))
        return

    if action == "attendance":
        lesson_number = live3.default_lesson_number()
        keyboard, finalized, records, student_count = live3.build_attendance_keyboard(lesson_number)
        await query.message.reply_text(
            live3.attendance_text(lesson_number, finalized, records, student_count),
            reply_markup=keyboard,
        )
        return

    if action == "probmenu":
        await query.edit_message_text(
            "📝 <b>Пробники</b>\n\nЧто показать?",
            parse_mode="HTML",
            reply_markup=live7.InlineKeyboardMarkup([
                [live7.InlineKeyboardButton("📊 Последний пробник", callback_data="cab:problast")],
                [live7.InlineKeyboardButton("🧪 Слабые задания", callback_data="cab:probweak")],
                [live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
            ]),
        )
        return

    if action == "problast":
        await _send_chunks(query.message, live10.probnik_stats_text())
        return

    if action == "probweak":
        await _send_chunks(query.message, live10.weak_group_text())
        return

    if action == "homework":
        await _send_chunks(query.message, homework_summary_text())
        return

    if action == "trainmenu":
        await query.edit_message_text(
            "🧪 <b>Тренажёры</b>\n\nВыбирай статистику:",
            parse_mode="HTML",
            reply_markup=live7.InlineKeyboardMarkup([
                [
                    live7.InlineKeyboardButton("🧪 Кислоты", callback_data="cab:acid"),
                    live7.InlineKeyboardButton("🧫 Тривиальные", callback_data="cab:trivial"),
                ],
                [live7.InlineKeyboardButton("🏆 Рейтинг тривиальных", callback_data="cab:trivtop")],
                [live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
            ]),
        )
        return

    if action == "acid":
        year, month = _current_month()
        await _send_chunks(query.message, live22.acidstats_text(year, month))
        return

    if action == "trivial":
        year, month = _current_month()
        await _send_chunks(query.message, trivial_month_text(year, month))
        return

    if action == "trivtop":
        await _send_chunks(query.message, live7.top_text())
        return

    if action == "linkmenu":
        await query.edit_message_text(
            "🔗 <b>Ученики и Telegram</b>",
            parse_mode="HTML",
            reply_markup=live7.InlineKeyboardMarkup([
                [live7.InlineKeyboardButton("📋 Кто привязан", callback_data="cab:linkstatus")],
                [live7.InlineKeyboardButton("📢 Отправить приглашение", callback_data="cab:linkannounce")],
                [live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
            ]),
        )
        return

    if action == "linkstatus":
        await _send_chunks(query.message, link_status_text())
        return

    if action == "linkannounce":
        ok = await send_link_announcement_from_cabinet(context)
        await query.message.reply_text(
            "✅ Приглашение на привязку отправлено ребятам в группу."
            if ok else "Не удалось отправить: CHAT_ID не настроен."
        )
        return

    if action == "sync":
        await _send_chunks(query.message, sync_status_text())
        return

    if action == "timer":
        await query.message.reply_text(bot.get_countdown_text(), parse_mode="HTML")
        return


_original_start_router = live7.start_router
_original_text_router = live7.student_text_router


async def cabinet_start_router(update, context):
    if _admin_private(update) and not context.args:
        await update.message.reply_text(
            "Привет, Маша 💗 Кабинет преподавателя открыт.",
            reply_markup=ADMIN_KEYBOARD,
        )
        await show_cabinet(update, context)
        return
    await _original_start_router(update, context)


async def cabinet_text_router(update, context):
    if (
        update.effective_chat.type == "private"
        and bot.user_is_admin(update)
        and update.message
        and update.message.text == "👩‍🏫 Кабинет Маши"
    ):
        await show_cabinet(update, context)
        return
    await _original_text_router(update, context)


live7.start_router = cabinet_start_router
live7.student_text_router = cabinet_text_router


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
    application.add_handler(bot.CommandHandler("cabinet", cabinet_command))
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
    application.add_handler(bot.CommandHandler("acidstats", live22.acidstats_command))

    application.add_handler(bot.CommandHandler("testacidreminder", live20.test_acid_reminder_command))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))

    application.add_handler(live7.CallbackQueryHandler(cabinet_callback, pattern=r"^cab:"))
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

    print("Бот запущен — кабинет Маши активен")
    application.run_polling()


if __name__ == "__main__":
    main()
