import html
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live72

live72 = run_bot_live72
live71 = live72.live71
live70 = live72.live70
live69 = live72.live69
live68 = live72.live68
live67 = live72.live67
live66 = live72.live66
live65 = live72.live65
live64 = live72.live64
live63 = live72.live63
live61 = live72.live61
live60 = live72.live60
live59 = live72.live59
live56 = live72.live56
live55 = live72.live55
live54 = live72.live54
live52 = live72.live52
live51 = live72.live51
live50 = live72.live50
live49 = live72.live49
live48 = live72.live48
live46 = live72.live46
live44 = live72.live44
live43 = live72.live43
live41 = live72.live41
live39 = live72.live39
live37 = live72.live37
live35 = live72.live35
live34 = live72.live34
live31 = live72.live31
live24 = live72.live24
live17 = live72.live17
live28 = live72.live28
bot = live72.bot
run_bot = live72.run_bot
live23 = live72.live23
live7 = live72.live7


def ensure_admin_task_view_state():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_task_view_state (
                view_key TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _remember_view(view_key, message):
    if not message:
        return
    chat_id = getattr(message, "chat_id", None)
    message_id = getattr(message, "message_id", None)
    if chat_id is None or message_id is None:
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO admin_task_view_state (view_key, chat_id, message_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(view_key) DO UPDATE SET
                chat_id = excluded.chat_id,
                message_id = excluded.message_id,
                updated_at = excluded.updated_at
            """,
            (str(view_key), int(chat_id), int(message_id), datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


def _saved_view(view_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            "SELECT chat_id, message_id FROM admin_task_view_state WHERE view_key = ? LIMIT 1",
            (str(view_key),),
        ).fetchone()


def _active_task_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time
            FROM admin_tasks
            WHERE completed_at IS NULL
            ORDER BY start_date, reminder_time, id
            """
        ).fetchall()


def _task_list_text(tasks):
    if not tasks:
        return "🗒 <b>Активные задачи</b>\n\n✅ Все задачи выполнены."

    lines = ["🗒 <b>Активные задачи</b>", ""]
    for _task_id, task_text, start_date, reminder_time in tasks:
        try:
            date_text = datetime.strptime(str(start_date), "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            date_text = str(start_date or "")
        lines.append(
            f"• {html.escape(str(task_text or 'Задача'))} — с {html.escape(date_text)} в {html.escape(str(reminder_time or '10:00'))}"
        )
    lines.extend([
        "",
        "✅ Нажми на задачу, когда выполнишь её — она сразу исчезнет из списка.",
    ])
    return "\n".join(lines)


def _task_list_markup(tasks):
    rows = []
    for task_id, task_text, _start_date, _reminder_time in tasks:
        label = str(task_text or "Задача")
        if len(label) > 30:
            label = label[:27] + "…"
        rows.append([
            InlineKeyboardButton(
                f"✅ {label}",
                callback_data=f"cab:tasklistdone:{int(task_id)}",
            )
        ])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _complete_task(task_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT task_text, completed_at FROM admin_tasks WHERE id = ? LIMIT 1",
            (int(task_id),),
        ).fetchone()
        if not row:
            return None
        task_text, completed_at = row
        if not completed_at:
            conn.execute(
                "UPDATE admin_tasks SET completed_at = ? WHERE id = ?",
                (datetime.now(bot.TIMEZONE).isoformat(), int(task_id)),
            )
            conn.commit()
        return task_text


async def _refresh_task_list(context, skip=None):
    saved = _saved_view("tasks")
    if not saved:
        return
    chat_id, message_id = saved
    if skip and (int(chat_id), int(message_id)) == skip:
        return
    tasks = _active_task_rows()
    try:
        await context.bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=_task_list_text(tasks),
            parse_mode="HTML",
            reply_markup=_task_list_markup(tasks),
        )
    except Exception:
        pass


async def _refresh_today(context, skip=None):
    saved = _saved_view("today")
    if not saved:
        return
    chat_id, message_id = saved
    if skip and (int(chat_id), int(message_id)) == skip:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=live72.today_text(),
            parse_mode="HTML",
            reply_markup=live72.today_markup(),
        )
    except Exception:
        pass


_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_synced_task_views(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")
    current_key = None
    if query.message:
        current_key = (int(query.message.chat_id), int(query.message.message_id))

    if data == "cab:tasks":
        await query.answer()
        tasks = _active_task_rows()
        await query.edit_message_text(
            _task_list_text(tasks),
            parse_mode="HTML",
            reply_markup=_task_list_markup(tasks),
        )
        _remember_view("tasks", query.message)
        return

    if data.startswith("cab:tasklistdone:"):
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            await query.answer("Не получилось определить задачу")
            return
        task_text = _complete_task(task_id)
        await query.answer("Задача выполнена ✅" if task_text else "Задача не найдена")
        tasks = _active_task_rows()
        await query.edit_message_text(
            _task_list_text(tasks),
            parse_mode="HTML",
            reply_markup=_task_list_markup(tasks),
        )
        _remember_view("tasks", query.message)
        await _refresh_today(context)
        return

    if data == "cab:today":
        await _previous_cabinet_callback(update, context)
        _remember_view("today", query.message)
        return

    if data.startswith("cab:todaytaskdone:"):
        await _previous_cabinet_callback(update, context)
        _remember_view("today", query.message)
        await _refresh_task_list(context)
        return

    if data.startswith("cab:taskdone:"):
        # Реальная кнопка «Выполнено» из ежедневного напоминания.
        await _previous_cabinet_callback(update, context)
        await _refresh_task_list(context, skip=current_key)
        await _refresh_today(context, skip=current_key)
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_synced_task_views


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
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    ensure_admin_task_view_state()
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
    live56.log_probnik_cabinet_audit()
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
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
