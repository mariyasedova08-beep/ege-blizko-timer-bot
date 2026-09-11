import html
import sqlite3
from datetime import datetime

import run_bot_live63

live63 = run_bot_live63
live61 = live63.live61
live60 = live63.live60
live59 = live63.live59
live56 = live63.live56
live55 = live63.live55
live54 = live63.live54
live52 = live63.live52
live51 = live63.live51
live50 = live63.live50
live49 = live63.live49
live48 = live63.live48
live46 = live63.live46
live44 = live63.live44
live43 = live63.live43
live41 = live63.live41
live39 = live63.live39
live37 = live63.live37
live36 = live37.live36
live35 = live63.live35
live34 = live63.live34
live31 = live63.live31
live24 = live63.live24
live17 = live63.live17
bot = live63.bot
live23 = live63.live23
live7 = live34.live7


def _active_task_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time
            FROM admin_tasks
            WHERE completed_at IS NULL
            ORDER BY start_date, id
            """
        ).fetchall()


def _task_list_markup_actionable():
    tasks = _active_task_rows()
    rows = []
    for task_id, task_text, _start_date, _reminder_time in tasks:
        label = str(task_text or "Задача")
        if len(label) > 30:
            label = label[:27] + "…"
        rows.append([
            live7.InlineKeyboardButton(
                f"✅ {label}",
                callback_data=f"cab:tasklistdone:{int(task_id)}",
            )
        ])
    rows.append([live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return live7.InlineKeyboardMarkup(rows), tasks


def _task_list_text(tasks):
    if not tasks:
        return "🗒 <b>Активные задачи</b>\n\n✅ Все задачи выполнены."

    lines = ["🗒 <b>Активные задачи</b>", ""]
    for _task_id, task_text, start_date, reminder_time in tasks:
        try:
            date_text = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d.%m.%Y")
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


# В списке задач больше нет тестовых кнопок: только реальное завершение задачи.
live36._task_list_markup = _task_list_markup_actionable

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_actionable_tasks(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:tasks":
        await query.answer()
        markup, tasks = _task_list_markup_actionable()
        await query.edit_message_text(
            _task_list_text(tasks),
            parse_mode="HTML",
            reply_markup=markup,
        )
        return

    if data.startswith("cab:tasklistdone:"):
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            await query.answer("Не смогла определить задачу")
            return

        now = datetime.now(bot.TIMEZONE)
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            row = conn.execute(
                "SELECT completed_at FROM admin_tasks WHERE id = ? LIMIT 1",
                (task_id,),
            ).fetchone()
            if row and not row[0]:
                conn.execute(
                    "UPDATE admin_tasks SET completed_at = ? WHERE id = ?",
                    (now.isoformat(), task_id),
                )
                conn.commit()

        await query.answer("Задача выполнена ✅")
        markup, tasks = _task_list_markup_actionable()
        await query.edit_message_text(
            _task_list_text(tasks),
            parse_mode="HTML",
            reply_markup=markup,
        )
        return

    # Старые сообщения с тестовыми кнопками могут ещё оставаться в истории чата.
    # Они больше ничего не тестируют и не меняют задачи.
    if data.startswith("cab:taskpreview:") or data == "cab:taskpreviewdone":
        await query.answer("Тестовые кнопки отключены. Открой «🗒 Задачи» заново.", show_alert=True)
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_actionable_tasks


if __name__ == "__main__":
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
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
    live56.log_probnik_cabinet_audit()
    print("Admin task list without test buttons ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
