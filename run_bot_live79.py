import html
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live78

live78 = run_bot_live78
live77 = live78.live77
live76 = live78.live76
live75 = live78.live75
live74 = live78.live74
live73 = live78.live73
live72 = live78.live72
live71 = live78.live71
live70 = live78.live70
live69 = live78.live69
live68 = live78.live68
live67 = live78.live67
live66 = live78.live66
live65 = live78.live65
live64 = live78.live64
live63 = live78.live63
live61 = live78.live61
live60 = live78.live60
live59 = live78.live59
live56 = live78.live56
live50 = live78.live50
live51 = live78.live51
live48 = live78.live48
live46 = live78.live46
live44 = live78.live44
live43 = live78.live43
live41 = live78.live41
live39 = live78.live39
live37 = live78.live37
live35 = live78.live35
live34 = live78.live34
live31 = live78.live31
live24 = live78.live24
live17 = live78.live17
live28 = live78.live28
bot = live78.bot
run_bot = live78.run_bot
live23 = live77.live23
live7 = live77.live7

TASK_PAGE_SIZE = 7


def ensure_task_sections():
    """Adds a section marker without disturbing existing task data."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(admin_tasks)").fetchall()}
        if "task_kind" not in columns:
            conn.execute("ALTER TABLE admin_tasks ADD COLUMN task_kind TEXT NOT NULL DEFAULT 'task'")
        conn.execute("UPDATE admin_tasks SET task_kind = 'task' WHERE coalesce(task_kind, '') = ''")
        conn.commit()


def _task_rows(kind="task", completed=False, limit=None):
    ensure_task_sections()
    completed_clause = "IS NOT NULL" if completed else "IS NULL"
    order_clause = "completed_at DESC, id DESC" if completed else "start_date, reminder_time, id"
    sql = f"""
        SELECT id, task_text, start_date, reminder_time, completed_at
        FROM admin_tasks
        WHERE task_kind = ? AND completed_at {completed_clause}
        ORDER BY {order_clause}
    """
    params = [str(kind)]
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(sql, params).fetchall()


def _tasks_menu_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Текущие", callback_data="cab:tasks:active"),
            InlineKeyboardButton("✅ Выполненные", callback_data="cab:tasks:done"),
        ],
        [
            InlineKeyboardButton("💡 Идеи контента", callback_data="cab:tasks:content"),
            InlineKeyboardButton("🛠 Технические", callback_data="cab:tasks:tech"),
        ],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _tasks_menu_text():
    return (
        "🗒 <b>Задачи</b>\n\n"
        f"📋 Текущие: <b>{len(_task_rows('task'))}</b>\n"
        f"✅ Выполненные: <b>{len(_task_rows('task', completed=True))}</b>\n"
        f"💡 Идеи контента: <b>{len(_task_rows('content'))}</b>\n"
        f"🛠 Технические: <b>{len(_task_rows('tech'))}</b>\n\n"
        "Выполненные задачи теперь хранятся отдельно и не мешают в основном списке."
    )


def _short(text, width=24):
    value = str(text or "Задача").replace("\n", " ").strip()
    return value if len(value) <= width else value[: width - 1] + "…"


def _date_short(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d.%m")
    except Exception:
        return str(value or "—")[:5]


def _table_text(kind, title):
    all_rows = _task_rows(kind)
    rows = all_rows[:TASK_PAGE_SIZE]
    if not rows:
        return f"<b>{title}</b>\n\n✅ Здесь пока пусто.", rows

    table = ["№ | Задача                   | Дата  | Время", "--+--------------------------+-------+------"]
    for idx, (_task_id, task_text, start_date, reminder_time, _completed_at) in enumerate(rows, 1):
        task_col = _short(task_text, 24).ljust(24)
        table.append(f"{idx} | {task_col} | {_date_short(start_date):5} | {str(reminder_time or '10:00')[:5]}")

    extra = len(all_rows) - len(rows)
    text = f"<b>{title}</b>\n\n<pre>{html.escape(chr(10).join(table))}</pre>"
    if extra > 0:
        text += f"\nЕщё задач: {extra}. Сейчас показываю первые {TASK_PAGE_SIZE}."
    text += "\n\nНажми кнопку с номером выполненной задачи — она сразу перейдёт в «✅ Выполненные»."
    return text, rows


def _active_markup(rows, kind):
    buttons = []
    for idx, (task_id, task_text, _start_date, _reminder_time, _completed_at) in enumerate(rows, 1):
        buttons.append([
            InlineKeyboardButton(
                f"✅ {idx}. {_short(task_text, 26)}",
                callback_data=f"cab:taskfinish:{kind}:{int(task_id)}",
            )
        ])
    buttons.append([InlineKeyboardButton("← К разделам", callback_data="cab:tasks")])
    return InlineKeyboardMarkup(buttons)


def _done_text():
    rows = _task_rows("task", completed=True, limit=30)
    lines = ["✅ <b>Выполненные задачи</b>", ""]
    if not rows:
        lines.append("Пока здесь пусто.")
    else:
        for _task_id, task_text, _start_date, _reminder_time, completed_at in rows:
            try:
                done_at = datetime.fromisoformat(str(completed_at)).astimezone(bot.TIMEZONE).strftime("%d.%m.%Y %H:%M")
            except Exception:
                done_at = str(completed_at or "")
            lines.append(f"• {html.escape(str(task_text or 'Задача'))} — {html.escape(done_at)}")
    return "\n".join(lines)


def _back_to_sections():
    return InlineKeyboardMarkup([[InlineKeyboardButton("← К разделам", callback_data="cab:tasks")]])


_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_task_sections(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:tasks":
        await query.answer()
        await query.edit_message_text(_tasks_menu_text(), parse_mode="HTML", reply_markup=_tasks_menu_markup())
        return

    if data == "cab:tasks:active":
        await query.answer()
        text, rows = _table_text("task", "📋 Текущие задачи — первые 7")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=_active_markup(rows, "task"))
        return

    if data == "cab:tasks:done":
        await query.answer()
        await query.edit_message_text(_done_text(), parse_mode="HTML", reply_markup=_back_to_sections())
        return

    if data == "cab:tasks:content":
        await query.answer()
        text, rows = _table_text("content", "💡 Идеи контента")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=_active_markup(rows, "content"))
        return

    if data == "cab:tasks:tech":
        await query.answer()
        text, rows = _table_text("tech", "🛠 Технические задачи")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=_active_markup(rows, "tech"))
        return

    if data.startswith("cab:taskfinish:"):
        parts = data.split(":")
        if len(parts) != 4:
            await query.answer("Не получилось определить задачу")
            return
        kind = parts[2]
        try:
            task_id = int(parts[3])
        except Exception:
            await query.answer("Не получилось определить задачу")
            return

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                "UPDATE admin_tasks SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
                (datetime.now(bot.TIMEZONE).isoformat(), task_id),
            )
            conn.commit()

        await query.answer("Готово ✅ Перенесла в выполненные")
        if kind == "content":
            text, rows = _table_text("content", "💡 Идеи контента")
        elif kind == "tech":
            text, rows = _table_text("tech", "🛠 Технические задачи")
        else:
            kind = "task"
            text, rows = _table_text("task", "📋 Текущие задачи — первые 7")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=_active_markup(rows, kind))
        # Синхронизируем экран «Сегодня», если он был открыт.
        try:
            await live73._refresh_today(context)
        except Exception:
            pass
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_task_sections


if __name__ == "__main__":
    live71.ensure_molar_access_tables()
    live70.ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live24.live18.ensure_acid_reminder_table()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    ensure_task_sections()
    live73.ensure_admin_task_view_state()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live66.seed_zlata_accounting_task()
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
    live74.ensure_notification_catchup_tables()
    live77.ensure_lesson_feedback_tables()
    live78.seed_priority_tasks()
    live56.log_probnik_cabinet_audit()
    print("Admin tasks separated: active / completed / content / technical", flush=True)
    print("Admin current-task table shows first seven tasks", flush=True)
    print("Completed admin tasks stay completed after restart", flush=True)
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
