from datetime import datetime, timedelta
import re
import secrets
import sqlite3

from telegram.ext import CallbackQueryHandler

import run_bot_live5

live5 = run_bot_live5
live4 = live5.live4
live3 = live4.live3
live2 = live4.live2
run_bot = live4.run_bot
bot = live4.bot


DAY_NAMES = {
    0: "пн",
    1: "вт",
    2: "ср",
    3: "чт",
    4: "пт",
    5: "сб",
    6: "вс",
}
DAY_ALIASES = {
    "пн": 0,
    "понедельник": 0,
    "понедельникам": 0,
    "вт": 1,
    "вторник": 1,
    "вторникам": 1,
    "ср": 2,
    "среда": 2,
    "средам": 2,
    "чт": 3,
    "четверг": 3,
    "четвергам": 3,
    "пт": 4,
    "пятница": 4,
    "пятницам": 4,
    "сб": 5,
    "суббота": 5,
    "субботам": 5,
    "вс": 6,
    "воскресенье": 6,
    "воскресеньям": 6,
}


def ensure_tutor_tables():
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tutor_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                telegram_user_id INTEGER,
                telegram_username TEXT,
                telegram_name TEXT,
                invite_code TEXT,
                invite_expires_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO tutor_settings (id, updated_at)
            VALUES (1, ?)
            """,
            (now,),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tutor_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_text TEXT NOT NULL,
                schedule_kind TEXT NOT NULL CHECK(schedule_kind IN ('once', 'daily', 'weekly')),
                run_date TEXT,
                run_time TEXT NOT NULL,
                weekdays TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                last_sent_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def get_tutor_settings():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT telegram_user_id, telegram_username, telegram_name,
                   invite_code, invite_expires_at
            FROM tutor_settings
            WHERE id = 1
            """
        ).fetchone()


def set_tutor_invite(code, expires_at):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE tutor_settings
            SET invite_code = ?, invite_expires_at = ?, updated_at = ?
            WHERE id = 1
            """,
            (code, expires_at.isoformat(), now),
        )
        conn.commit()


def link_tutor(telegram_user_id, username, name):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE tutor_settings
            SET telegram_user_id = ?, telegram_username = ?, telegram_name = ?,
                invite_code = NULL, invite_expires_at = NULL, updated_at = ?
            WHERE id = 1
            """,
            (telegram_user_id, username or "", name or "", now),
        )
        conn.commit()


def get_tutor_id():
    row = get_tutor_settings()
    return row[0] if row and row[0] else None


def save_tutor_reminder(text, schedule):
    now = datetime.now(bot.TIMEZONE).isoformat()
    weekdays = None
    if schedule["kind"] == "weekly":
        weekdays = ",".join(str(day) for day in schedule["weekdays"])
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tutor_reminders (
                reminder_text, schedule_kind, run_date, run_time, weekdays,
                active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                text,
                schedule["kind"],
                schedule.get("run_date"),
                schedule["run_time"],
                weekdays,
                now,
                now,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def parse_time(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_tutor_schedule(text):
    raw = " ".join(text.strip().lower().split())

    # Один раз: 15.09.2026 10:30
    one_time = re.fullmatch(r"(\d{1,2}\.\d{1,2}\.\d{4})\s+(\d{1,2}:\d{2})", raw)
    if one_time:
        try:
            run_date = datetime.strptime(one_time.group(1), "%d.%m.%Y").date()
        except ValueError:
            return None, "Не получилось прочитать дату. Например: 15.09.2026 10:30"
        run_time = parse_time(one_time.group(2))
        if not run_time:
            return None, "Не получилось прочитать время. Например: 15.09.2026 10:30"
        scheduled_dt = datetime.combine(
            run_date,
            datetime.strptime(run_time, "%H:%M").time(),
            tzinfo=bot.TIMEZONE,
        )
        if scheduled_dt <= datetime.now(bot.TIMEZONE):
            return None, "Это время уже прошло. Укажи будущую дату и время."
        return {
            "kind": "once",
            "run_date": run_date.isoformat(),
            "run_time": run_time,
        }, None

    # Каждый день: каждый день 10:30 / ежедневно 10:30
    daily = re.fullmatch(r"(?:каждый день|ежедневно)\s+(\d{1,2}:\d{2})", raw)
    if daily:
        run_time = parse_time(daily.group(1))
        if not run_time:
            return None, "Не получилось прочитать время. Например: каждый день 10:30"
        return {"kind": "daily", "run_time": run_time}, None

    # По дням недели: пн, ср, вс 18:00
    time_match = re.search(r"(\d{1,2}:\d{2})$", raw)
    if time_match:
        run_time = parse_time(time_match.group(1))
        if not run_time:
            return None, "Не получилось прочитать время. Например: пн, ср, вс 18:00"
        prefix = raw[:time_match.start()].strip(" ,")
        tokens = re.findall(r"[а-яё]+", prefix)
        weekdays = sorted({DAY_ALIASES[token] for token in tokens if token in DAY_ALIASES})
        if weekdays:
            return {
                "kind": "weekly",
                "run_time": run_time,
                "weekdays": weekdays,
            }, None

    return None, (
        "Не поняла расписание. Напиши одним из способов:\n"
        "• 15.09.2026 10:30 — один раз\n"
        "• каждый день 10:30\n"
        "• пн, ср, вс 18:00"
    )


def schedule_description(schedule):
    if schedule["kind"] == "once":
        date_text = datetime.strptime(schedule["run_date"], "%Y-%m-%d").strftime("%d.%m.%Y")
        return f"{date_text} в {schedule['run_time']}"
    if schedule["kind"] == "daily":
        return f"каждый день в {schedule['run_time']}"
    days = ", ".join(DAY_NAMES[day] for day in schedule["weekdays"])
    return f"{days} в {schedule['run_time']}"


async def tutor_invite(update, context):
    if not bot.user_is_admin(update):
        return
    if update.effective_chat.type != "private":
        return

    code = f"{secrets.randbelow(1000000):06d}"
    expires_at = datetime.now(bot.TIMEZONE) + timedelta(hours=24)
    set_tutor_invite(code, expires_at)
    me = await context.bot.get_me()
    await update.message.reply_text(
        "✅ Код для подключения тьютора создан.\n\n"
        "Перешли тьютору:\n"
        f"1. Открыть @{me.username}\n"
        f"2. Отправить команду /tutorlink {code}\n\n"
        "Код действует 24 часа."
    )


async def tutor_link(update, context):
    if update.effective_chat.type != "private":
        return
    if not context.args:
        await update.message.reply_text("Нужен код подключения от преподавателя.")
        return

    row = get_tutor_settings()
    stored_code = row[3] if row else None
    expires_text = row[4] if row else None
    code = context.args[0].strip()

    if not stored_code or code != stored_code:
        await update.message.reply_text("Код не подходит. Попроси преподавателя создать новый.")
        return

    try:
        expires_at = datetime.fromisoformat(expires_text)
    except (TypeError, ValueError):
        expires_at = datetime.now(bot.TIMEZONE) - timedelta(seconds=1)

    if datetime.now(bot.TIMEZONE) > expires_at:
        await update.message.reply_text("Срок действия кода закончился. Попроси преподавателя создать новый.")
        return

    user = update.effective_user
    link_tutor(user.id, user.username, user.full_name)
    await update.message.reply_text(
        "✅ Готово! Ты подключён(а) как тьютор курса.\n"
        "Теперь сюда будут приходить рабочие напоминания."
    )


async def tutor_status(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    row = get_tutor_settings()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        active_count = conn.execute(
            "SELECT COUNT(*) FROM tutor_reminders WHERE active = 1"
        ).fetchone()[0]

    if row and row[0]:
        username = f"@{row[1]}" if row[1] else "без username"
        name = row[2] or "Тьютор"
        await update.message.reply_text(
            f"✅ Тьютор подключён: {name} ({username})\n"
            f"Активных напоминаний: {active_count}"
        )
    else:
        await update.message.reply_text(
            "Тьютор пока не подключён.\n"
            "Создай приглашение командой /tutorinvite"
        )


async def tutor_reminder_command(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    context.user_data.pop("rename_student_id", None)
    context.user_data["tutor_reminder_state"] = "text"
    context.user_data["tutor_reminder_draft"] = {}
    await update.message.reply_text(
        "🔔 Создаём напоминание для тьютора.\n\n"
        "Сначала напиши текст напоминания одним сообщением."
    )


async def tutor_cancel(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    context.user_data.pop("tutor_reminder_state", None)
    context.user_data.pop("tutor_reminder_draft", None)
    await update.message.reply_text("Создание напоминания отменено.")


async def combined_private_text_handler(update, context):
    if not update.message or not update.message.text:
        return

    state = context.user_data.get("tutor_reminder_state")
    if state and update.effective_chat.type == "private" and bot.user_is_admin(update):
        text = update.message.text.strip()
        if text.startswith("/"):
            return

        if state == "text":
            if not text:
                await update.message.reply_text("Напиши текст напоминания.")
                return
            if len(text) > 1500:
                await update.message.reply_text("Текст слишком длинный. Сделай его до 1500 символов.")
                return
            context.user_data["tutor_reminder_draft"] = {"text": text}
            context.user_data["tutor_reminder_state"] = "schedule"
            await update.message.reply_text(
                "Теперь напиши, когда отправлять. Например:\n\n"
                "15.09.2026 10:30\n"
                "каждый день 10:30\n"
                "пн, ср, вс 18:00"
            )
            return

        if state == "schedule":
            schedule, error = parse_tutor_schedule(text)
            if error:
                await update.message.reply_text(error)
                return
            draft = context.user_data.get("tutor_reminder_draft", {})
            reminder_text = draft.get("text")
            if not reminder_text:
                context.user_data.pop("tutor_reminder_state", None)
                context.user_data.pop("tutor_reminder_draft", None)
                await update.message.reply_text("Черновик потерялся. Начни заново: /tutorreminder")
                return

            reminder_id = save_tutor_reminder(reminder_text, schedule)
            context.user_data.pop("tutor_reminder_state", None)
            context.user_data.pop("tutor_reminder_draft", None)
            await update.message.reply_text(
                f"✅ Напоминание №{reminder_id} сохранено.\n\n"
                f"Когда: {schedule_description(schedule)}\n"
                f"Текст: {reminder_text}"
            )
            return

    # Если сейчас не создаём напоминание, сохраняем прежнее поведение переименования учеников.
    await live4.rename_text_handler(update, context)


async def rename_command_wrapper(update, context):
    context.user_data.pop("tutor_reminder_state", None)
    context.user_data.pop("tutor_reminder_draft", None)
    await live4.rename_student_command(update, context)


async def tutor_reminders_list(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, reminder_text, schedule_kind, run_date, run_time, weekdays
            FROM tutor_reminders
            WHERE active = 1
            ORDER BY id
            """
        ).fetchall()

    if not rows:
        await update.message.reply_text("Активных напоминаний для тьютора пока нет.")
        return

    lines = ["🔔 Напоминания тьютора", ""]
    for reminder_id, text, kind, run_date, run_time, weekdays in rows:
        if kind == "once":
            desc = datetime.strptime(run_date, "%Y-%m-%d").strftime("%d.%m.%Y") + f" в {run_time}"
        elif kind == "daily":
            desc = f"каждый день в {run_time}"
        else:
            day_nums = [int(x) for x in (weekdays or "").split(",") if x != ""]
            desc = ", ".join(DAY_NAMES[d] for d in day_nums) + f" в {run_time}"
        short_text = text if len(text) <= 90 else text[:87] + "…"
        lines.append(f"№{reminder_id} — {desc}\n{short_text}\n")

    lines.append("Удалить: /tutordel НОМЕР")
    await update.message.reply_text("\n".join(lines))


async def tutor_delete(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Например: /tutordel 3")
        return
    reminder_id = int(context.args[0])
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cursor = conn.execute(
            "UPDATE tutor_reminders SET active = 0, updated_at = ? WHERE id = ? AND active = 1",
            (now, reminder_id),
        )
        conn.commit()
    if cursor.rowcount:
        await update.message.reply_text(f"✅ Напоминание №{reminder_id} удалено.")
    else:
        await update.message.reply_text("Активное напоминание с таким номером не найдено.")


async def tutor_test(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    tutor_id = get_tutor_id()
    if not tutor_id:
        await update.message.reply_text("Сначала подключи тьютора через /tutorinvite")
        return
    await context.bot.send_message(
        chat_id=tutor_id,
        text="🔔 Тестовое напоминание\n\nВсё работает 💗",
    )
    await update.message.reply_text("✅ Тест отправлен тьютору.")


def reminder_is_due(row, now):
    reminder_id, _, kind, run_date, run_time, weekdays, last_sent_key = row
    current_time = now.strftime("%H:%M")
    today = now.date().isoformat()
    key = f"{today} {run_time}"

    if current_time != run_time or last_sent_key == key:
        return False, key

    if kind == "once":
        return run_date == today, key
    if kind == "daily":
        return True, key
    if kind == "weekly":
        day_nums = {int(x) for x in (weekdays or "").split(",") if x != ""}
        return now.weekday() in day_nums, key
    return False, key


async def tutor_reminder_tick(context):
    tutor_id = get_tutor_id()
    if not tutor_id:
        return

    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id, reminder_text, schedule_kind, run_date, run_time, weekdays, last_sent_key
            FROM tutor_reminders
            WHERE active = 1
            ORDER BY id
            """
        ).fetchall()

    for row in rows:
        reminder_id, reminder_text, kind, _, _, _, _ = row
        due, key = reminder_is_due(row, now)
        if not due:
            continue
        try:
            await context.bot.send_message(
                chat_id=tutor_id,
                text=f"🔔 Напоминание\n\n{reminder_text}",
            )
        except Exception as exc:
            print(f"Ошибка отправки напоминания тьютору #{reminder_id}: {exc}")
            continue

        updated_at = datetime.now(bot.TIMEZONE).isoformat()
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            if kind == "once":
                conn.execute(
                    """
                    UPDATE tutor_reminders
                    SET last_sent_key = ?, active = 0, updated_at = ?
                    WHERE id = ?
                    """,
                    (key, updated_at, reminder_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE tutor_reminders
                    SET last_sent_key = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (key, updated_at, reminder_id),
                )
            conn.commit()


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    live3.ensure_attendance_tables()
    live4.ensure_display_name_column()
    ensure_tutor_tables()
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
    application.add_handler(bot.CommandHandler("attendancestats", live4.attendance_stats))
    application.add_handler(bot.CommandHandler("rename", rename_command_wrapper))

    application.add_handler(bot.CommandHandler("tutorinvite", tutor_invite))
    application.add_handler(bot.CommandHandler("tutorlink", tutor_link))
    application.add_handler(bot.CommandHandler("tutorstatus", tutor_status))
    application.add_handler(bot.CommandHandler("tutorreminder", tutor_reminder_command))
    application.add_handler(bot.CommandHandler("tutorreminders", tutor_reminders_list))
    application.add_handler(bot.CommandHandler("tutordel", tutor_delete))
    application.add_handler(bot.CommandHandler("tutortest", tutor_test))
    application.add_handler(bot.CommandHandler("tutorcancel", tutor_cancel))

    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))
    application.add_handler(CallbackQueryHandler(live3.attendance_callback, pattern=r"^att:"))
    application.add_handler(CallbackQueryHandler(live4.rename_callback, pattern=r"^ren:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))
    application.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, combined_private_text_handler))

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
    application.job_queue.run_repeating(
        tutor_reminder_tick,
        interval=30,
        first=10,
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
