"""Tomorrow dashboard for PREPODMIN.

Shows the teacher's next-day schedule with individual/group moves applied and
all unfinished dated tasks that will already be due by tomorrow.
"""
from datetime import date, datetime, timedelta

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_today as today

WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def _tomorrow(uid):
    return datetime.now(schedule.tz(uid)).date() + timedelta(days=1)


def _tasks_due_by(uid, day):
    with base.db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='teacher_tasks'"
        ).fetchone()
        if not exists:
            return []
        return conn.execute(
            """
            SELECT id,title,due_date,due_time,task_kind
            FROM teacher_tasks
            WHERE teacher_telegram_user_id=?
              AND completed=0
              AND due_date<>''
              AND due_date<=?
            ORDER BY due_date,
                     CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,
                     due_time,id
            """,
            (int(uid), day.isoformat()),
        ).fetchall()


def _task_line(task, day):
    when = task["due_time"] or "без времени"
    try:
        due = date.fromisoformat(task["due_date"])
    except Exception:
        due = day

    if due == day:
        tail = ""
    else:
        tail = f" ↩️ с {due.strftime('%d.%m')}"
    return f"• {when} — {task['title']}{tail}"


def _main_keyboard_with_tomorrow():
    return ReplyKeyboardMarkup(
        [
            ["➕ Быстрая задача"],
            ["📍 Сегодня", "🌅 Завтра"],
            ["✅ Задачи"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )


async def tomorrow_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    day = _tomorrow(uid)
    events = today._individual_today(uid, day) + today._group_today(uid, day)
    events.sort(key=lambda e: (e["time"], e["kind"], e["name"].lower()))
    tasks = _tasks_due_by(uid, day)

    header = f"🌅 Завтра • {day.strftime('%d.%m.%Y')} • {WEEKDAYS[day.weekday()]}"
    lines = [header]

    if events:
        lines.append(f"Занятий: {len(events)}")
        summary = today._summary(uid, events, day)
        if summary:
            lines.append(summary)

        for event in events:
            moved = " ↪️" if event["moved"] else ""
            if event["kind"] == "individual":
                lines.append(
                    f"\n🕒 {event['time']} • 👤 {event['name']}{moved}\n"
                    f"{today._payment_line(uid, event['student_id'], day)}"
                )
            else:
                lines.append(
                    f"\n🕒 {event['time']} • 👥 {event['name']}{moved}\n"
                    "💳 оплата участников появится после подключения состава группы"
                )

        if any(e["moved"] for e in events):
            lines.append("\n↪️ — занятие было перенесено")
    else:
        lines.append("Занятий завтра нет")

    lines.append("\n✅ Задачи к завтрашнему дню")
    if tasks:
        lines.extend(_task_line(task, day) for task in tasks)
        if any(str(task["due_date"]) != day.isoformat() for task in tasks):
            lines.append("\n↩️ — незакрытая задача с предыдущей даты")
    else:
        lines.append("Задач на завтра и незакрытых хвостов нет 🎉")

    await update.message.reply_text("\n".join(lines), reply_markup=base.MAIN_KB)
    raise ApplicationHandlerStop


def install(app):
    base.MAIN_KB = _main_keyboard_with_tomorrow()
    app.add_handler(
        MessageHandler(filters.Regex(r"^🌅 Завтра$"), tomorrow_dashboard),
        group=-12,
    )
    print("PREPODMIN tomorrow dashboard ready: schedule + tasks", flush=True)
    return app
