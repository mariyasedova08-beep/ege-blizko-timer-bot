import sqlite3
from datetime import datetime, timedelta

from telegram.ext import PollAnswerHandler

import run_bot_live23

live23 = run_bot_live23
live22 = live23.live22
live21 = live23.live21
live20 = live23.live20
live19 = live23.live19
live18 = live23.live18
live17 = live23.live17
live15 = live23.live15
live10 = live23.live10
live7 = live23.live7
live6 = live23.live6
live4 = live23.live4
live3 = live23.live3
live2 = live23.live2
run_bot = live23.run_bot
bot = live23.bot

POLL_OPTIONS = ("✅ Буду", "❌ Не буду")
PROBNIK_POLL_SUMMARY_TIME = "20:00"


def ensure_probnik_poll_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id TEXT NOT NULL UNIQUE,
                probnik_date TEXT NOT NULL,
                probnik_number INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER,
                created_at TEXT NOT NULL,
                summary_sent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_poll_answers (
                poll_id TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                option_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (poll_id, telegram_user_id)
            )
            """
        )
        conn.commit()


def _student_display_name(conn, telegram_user_id, fallback="Ученик"):
    row = conn.execute(
        """
        SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, '')
        FROM students
        WHERE active = 1 AND telegram_user_id = ?
        LIMIT 1
        """,
        (telegram_user_id,),
    ).fetchone()
    if row and row[0]:
        return row[0]
    return fallback or "Ученик"


def _poll_already_sent_today(probnik_date):
    today = bot.today_moscow().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT poll_id
            FROM probnik_polls
            WHERE probnik_date = ? AND substr(created_at, 1, 10) = ?
            ORDER BY id DESC LIMIT 1
            """,
            (probnik_date.isoformat(), today),
        ).fetchone()
    return row[0] if row else None


async def send_probnik_attendance_poll(context, probnik_date, force=False):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False

    if not force and _poll_already_sent_today(probnik_date):
        return True

    number = run_bot.probnik_number(probnik_date)
    sent = await context.bot.send_poll(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        question=f"📝 Будешь писать пробник №{number} завтра в 10:00?",
        options=list(POLL_OPTIONS),
        is_anonymous=False,
        allows_multiple_answers=False,
        is_closed=False,
    )
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO probnik_polls
                (poll_id, probnik_date, probnik_number, chat_id, message_id, created_at, summary_sent)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                sent.poll.id,
                probnik_date.isoformat(),
                number,
                int(chat_id),
                sent.message_id,
                now,
            ),
        )
        conn.commit()
    return True


_original_send_probnik_bundle = run_bot.send_probnik_bundle


async def send_probnik_bundle_with_poll(context, probnik_date, weekday_kind):
    ok, error = await _original_send_probnik_bundle(context, probnik_date, weekday_kind)
    if ok and weekday_kind == "friday":
        await send_probnik_attendance_poll(context, probnik_date)
    return ok, error


run_bot.send_probnik_bundle = send_probnik_bundle_with_poll


async def probnik_poll_answer(update, context):
    answer = update.poll_answer
    if not answer:
        return

    poll_id = answer.poll_id
    user = answer.user
    if not user:
        return

    now = datetime.now(bot.TIMEZONE).isoformat()
    full_name = " ".join(x for x in [user.first_name, user.last_name] if x).strip() or user.username or "Ученик"

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll_row = conn.execute(
            "SELECT probnik_number, summary_sent FROM probnik_polls WHERE poll_id = ? LIMIT 1",
            (poll_id,),
        ).fetchone()
        if not poll_row:
            return

        previous = conn.execute(
            """
            SELECT option_id FROM probnik_poll_answers
            WHERE poll_id = ? AND telegram_user_id = ?
            """,
            (poll_id, user.id),
        ).fetchone()
        previous_option = previous[0] if previous else None

        if not answer.option_ids:
            conn.execute(
                "DELETE FROM probnik_poll_answers WHERE poll_id = ? AND telegram_user_id = ?",
                (poll_id, user.id),
            )
            new_option = None
        else:
            new_option = int(answer.option_ids[0])
            conn.execute(
                """
                INSERT INTO probnik_poll_answers
                    (poll_id, telegram_user_id, telegram_username, telegram_name, option_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(poll_id, telegram_user_id) DO UPDATE SET
                    telegram_username = excluded.telegram_username,
                    telegram_name = excluded.telegram_name,
                    option_id = excluded.option_id,
                    updated_at = excluded.updated_at
                """,
                (poll_id, user.id, user.username or "", full_name, new_option, now),
            )
        conn.commit()

        student_name = _student_display_name(conn, user.id, full_name)
        number, summary_sent = poll_row

    # После вечерней сводки сообщаем Маше о поздних изменениях ответа.
    if summary_sent and previous_option != new_option:
        admin_id = bot.get_admin_id()
        if admin_id:
            if new_option is None:
                status = "убрал(а) ответ"
            else:
                status = POLL_OPTIONS[new_option] if 0 <= new_option < len(POLL_OPTIONS) else "изменил(а) ответ"
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=f"🔄 Пробник №{number}: {student_name} — {status}",
            )


def probnik_poll_summary_text(probnik_date):
    date_text = probnik_date.isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll = conn.execute(
            """
            SELECT poll_id, probnik_number
            FROM probnik_polls
            WHERE probnik_date = ?
            ORDER BY id DESC LIMIT 1
            """,
            (date_text,),
        ).fetchone()
        if not poll:
            return None, None

        poll_id, number = poll
        answers = conn.execute(
            """
            SELECT telegram_user_id, telegram_name, option_id
            FROM probnik_poll_answers
            WHERE poll_id = ?
            ORDER BY updated_at
            """,
            (poll_id,),
        ).fetchall()

        yes_names = []
        no_names = []
        answered_ids = set()
        for telegram_user_id, telegram_name, option_id in answers:
            answered_ids.add(int(telegram_user_id))
            name = _student_display_name(conn, telegram_user_id, telegram_name)
            if int(option_id) == 0:
                yes_names.append(name)
            elif int(option_id) == 1:
                no_names.append(name)

        students = conn.execute(
            """
            SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   telegram_user_id
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()
        no_answer = [name for name, tid in students if tid is not None and int(tid) not in answered_ids]
        unlinked = [name for name, tid in students if tid is None]

    lines = [
        f"📝 Опрос на пробник №{number}",
        f"📅 Завтра, {probnik_date.strftime('%d.%m.%Y')} в 10:00",
        "",
        f"✅ Будут: {len(yes_names)}",
    ]
    lines.extend(f"• {name}" for name in yes_names)
    lines.extend(["", f"❌ Не будут: {len(no_names)}"])
    lines.extend(f"• {name}" for name in no_names)
    if no_answer:
        lines.extend(["", f"⏳ Не ответили: {len(no_answer)}"])
        lines.extend(f"• {name}" for name in no_answer)
    if unlinked:
        lines.extend(["", f"🔗 Telegram не привязан: {len(unlinked)}"])
        lines.extend(f"• {name}" for name in unlinked)
    return "\n".join(lines), poll_id


async def probnik_poll_evening_summary(context):
    today = bot.today_moscow()
    probnik_date = next((d for d in run_bot.PROBNIK_DATES if today == d - timedelta(days=1)), None)
    if not probnik_date:
        return

    text, poll_id = probnik_poll_summary_text(probnik_date)
    if not text or not poll_id:
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT summary_sent FROM probnik_polls WHERE poll_id = ?",
            (poll_id,),
        ).fetchone()
        if row and row[0]:
            return

    admin_id = bot.get_admin_id()
    if not admin_id:
        return

    await context.bot.send_message(chat_id=int(admin_id), text=text)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("UPDATE probnik_polls SET summary_sent = 1 WHERE poll_id = ?", (poll_id,))
        conn.commit()


async def test_probnik_poll(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    ok = await send_probnik_attendance_poll(context, target, force=True)
    await update.message.reply_text(
        "✅ Тестовый опрос отправлен в группу." if ok else "Не удалось отправить: CHAT_ID не настроен."
    )


async def pollstatus_command(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    text, _ = probnik_poll_summary_text(target)
    await update.message.reply_text(text or "Опроса на ближайший пробник пока нет.")


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
    ensure_probnik_poll_tables()

    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", live7.start_router))
    application.add_handler(bot.CommandHandler("cabinet", live23.cabinet_command))
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
    application.add_handler(bot.CommandHandler("pollstatus", pollstatus_command))
    application.add_handler(bot.CommandHandler("testprobnikpoll", test_probnik_poll))

    application.add_handler(bot.CommandHandler("testacidreminder", live20.test_acid_reminder_command))
    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))

    application.add_handler(PollAnswerHandler(probnik_poll_answer))
    application.add_handler(live7.CallbackQueryHandler(live23.cabinet_callback, pattern=r"^cab:"))
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
        probnik_poll_evening_summary,
        time=datetime.strptime(PROBNIK_POLL_SUMMARY_TIME, "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
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
