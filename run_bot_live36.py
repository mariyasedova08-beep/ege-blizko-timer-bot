import sqlite3
from datetime import datetime

import run_bot_live35

live35 = run_bot_live35
live34 = live35.live34
live31 = live35.live31
live24 = live35.live24
live23 = live35.live23
live17 = live35.live17
live7 = live35.live7
bot = live35.bot


_original_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_tasks():
    base = _original_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    rows.insert(-1, [live7.InlineKeyboardButton("🗒 Задачи", callback_data="cab:tasks")])
    return live7.InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_tasks


def _task_list_markup():
    rows = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        tasks = conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time
            FROM admin_tasks
            WHERE completed_at IS NULL
            ORDER BY start_date, id
            """
        ).fetchall()
    for task_id, task_text, start_date, reminder_time in tasks:
        label = task_text if len(task_text) <= 28 else task_text[:25] + "…"
        rows.append([
            live7.InlineKeyboardButton(
                f"▶️ Тест: {label}",
                callback_data=f"cab:taskpreview:{int(task_id)}",
            )
        ])
    rows.append([live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return live7.InlineKeyboardMarkup(rows), tasks


def _preview_done_markup():
    return live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("✅ Выполнено", callback_data="cab:taskpreviewdone")]
    ])


_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_task_preview(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = query.data or ""

    if data == "cab:tasks":
        await query.answer()
        markup, tasks = _task_list_markup()
        if tasks:
            lines = ["🗒 <b>Активные задачи</b>", ""]
            for _task_id, task_text, start_date, reminder_time in tasks:
                try:
                    date_text = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d.%m.%Y")
                except Exception:
                    date_text = start_date
                lines.append(f"• {task_text} — с {date_text} в {reminder_time}")
            lines.extend(["", "Нажми «▶️ Тест», чтобы увидеть напоминание прямо сейчас. Настоящая задача от теста не закроется."])
            text = "\n".join(lines)
        else:
            text = "🗒 <b>Активные задачи</b>\n\n✅ Все задачи выполнены."
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        return

    if data.startswith("cab:taskpreview:"):
        await query.answer()
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            row = conn.execute(
                "SELECT task_text FROM admin_tasks WHERE id = ? LIMIT 1",
                (task_id,),
            ).fetchone()
        if not row:
            await query.message.reply_text("Задачу не нашла.")
            return
        await query.message.reply_text(
            "🧪 <b>ТЕСТ напоминания</b>\n\n"
            "⏰ <b>Задача</b>\n\n"
            f"{row[0]}\n\n"
            "Буду напоминать каждый день в 10:00, пока ты не отметишь её выполненной.\n\n"
            "Кнопка ниже тестовая — настоящую задачу она не закроет.",
            parse_mode="HTML",
            reply_markup=_preview_done_markup(),
        )
        return

    if data == "cab:taskpreviewdone":
        await query.answer("Кнопка работает ✅")
        await query.edit_message_text(
            "✅ <b>Тест кнопки «Выполнено» пройден.</b>\n\n"
            "Настоящая задача осталась активной и начнёт напоминать в понедельник.",
            parse_mode="HTML",
        )
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_task_preview


if __name__ == "__main__":
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
    live24.main()
