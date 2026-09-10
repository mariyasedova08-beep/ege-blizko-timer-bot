import sqlite3
from datetime import date, datetime, time, timedelta

import run_bot_live34

live34 = run_bot_live34
live33 = live34.live33
live31 = live34.live31
live30 = live34.live30
live28 = live34.live28
live25 = live34.live25
live24 = live34.live24
live23 = live34.live23
live17 = live34.live17
live7 = live34.live7
bot = live34.bot

ADMIN_TASK_START_TIME = "10:00"
MONDAY_TASK_KEY = "monday-reminder-2026-09-14"
MONDAY_TASK_START_DATE = date(2026, 9, 14)
MONDAY_TASK_TEXT = "Напоминание на понедельник"


def ensure_admin_tasks_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_key TEXT NOT NULL UNIQUE,
                task_text TEXT NOT NULL,
                start_date TEXT NOT NULL,
                reminder_time TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_sent_date TEXT,
                completed_at TEXT
            )
            """
        )
        conn.commit()


def seed_monday_task():
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO admin_tasks
                (task_key, task_text, start_date, reminder_time, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                MONDAY_TASK_KEY,
                MONDAY_TASK_TEXT,
                MONDAY_TASK_START_DATE.isoformat(),
                ADMIN_TASK_START_TIME,
                now,
            ),
        )
        conn.commit()


def _active_admin_tasks(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time, last_sent_date
            FROM admin_tasks
            WHERE completed_at IS NULL
              AND start_date <= ?
            ORDER BY id
            """,
            (now.date().isoformat(),),
        ).fetchall()


def _task_markup(task_id):
    return live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("✅ Выполнено", callback_data=f"cab:taskdone:{int(task_id)}")]
    ])


async def admin_task_tick(context):
    now = datetime.now(bot.TIMEZONE)
    admin_id = bot.get_admin_id()
    if not admin_id:
        return

    for task_id, task_text, _start_date, reminder_time, last_sent_date in _active_admin_tasks(now):
        try:
            reminder_clock = datetime.strptime(reminder_time, "%H:%M").time()
        except Exception:
            reminder_clock = time(10, 0)
        if now.time() < reminder_clock:
            continue
        if last_sent_date == now.date().isoformat():
            continue

        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=(
                    "⏰ <b>Задача</b>\n\n"
                    f"{task_text}\n\n"
                    "Буду напоминать каждый день в 10:00, пока ты не отметишь её выполненной."
                ),
                parse_mode="HTML",
                reply_markup=_task_markup(task_id),
            )
        except Exception as exc:
            print(f"Could not send admin task {task_id}: {exc}")
            continue

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                "UPDATE admin_tasks SET last_sent_date = ? WHERE id = ?",
                (now.date().isoformat(), int(task_id)),
            )
            conn.commit()


def _attention_demo_markup():
    return live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("🔴 Пример сообщения ученику", callback_data="cab:zonetestchild")],
        [live7.InlineKeyboardButton("👨‍👩‍👧 Пример сообщения родителю", callback_data="cab:zonetestparent")],
        [live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _demo_metrics():
    return [
        {"key": "attendance", "value": 2, "label": "посещаемость: 2 пропуска из 4 последних уроков"},
        {"key": "homework", "value": 2, "label": "ДЗ: не закрыто 2 из 3 последних обязательных работ"},
        {"key": "probnik", "value": 54, "label": "пробник: 54 балла (ниже 60)"},
        {"key": "trainer", "value": 1, "label": "тренажёры: 1 за последние 7 дней"},
    ]


_original_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_tasks_and_tests(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = query.data or ""

    if data.startswith("cab:taskdone:"):
        await query.answer("Готово ✅")
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        now = datetime.now(bot.TIMEZONE)
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            row = conn.execute(
                "SELECT task_text, completed_at FROM admin_tasks WHERE id = ? LIMIT 1",
                (task_id,),
            ).fetchone()
            if not row:
                await query.edit_message_text("Эта задача уже не найдена.")
                return
            task_text, completed_at = row
            if not completed_at:
                conn.execute(
                    "UPDATE admin_tasks SET completed_at = ? WHERE id = ?",
                    (now.isoformat(), task_id),
                )
                conn.commit()
        await query.edit_message_text(f"✅ <b>Выполнено</b>\n\n{task_text}", parse_mode="HTML")
        return

    if data == "cab:zone":
        await query.answer()
        await query.message.reply_text(live34.zone_attention_text(), reply_markup=_attention_demo_markup())
        return

    if data == "cab:zonetestchild":
        await query.answer()
        await query.message.reply_text(
            "🧪 ТЕСТ. Это видишь только ты; ученикам ничего не отправлено.\n\n"
            + live34._child_alert_text("Тестовый ученик", _demo_metrics())
        )
        return

    if data == "cab:zonetestparent":
        await query.answer()
        await query.message.reply_text(
            "🧪 ТЕСТ. Это видишь только ты; родителям ничего не отправлено.\n\n"
            + live34._parent_alert_text("Тестовый ученик", _demo_metrics()),
            parse_mode="HTML",
        )
        return

    await _original_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_tasks_and_tests


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_admin_tasks(context):
    try:
        await _previous_tick(context)
    finally:
        await admin_task_tick(context)


live7.friday_trivial_tick = combined_tick_with_admin_tasks


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    ensure_admin_tasks_table()
    seed_monday_task()
    live24.main()
