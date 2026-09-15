from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import teacher_product_mvp as base
import teacher_product_reminders as reminders


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row)


def delete_teacher_data(uid):
    uid = int(uid)
    deleted = {}
    with base.db() as conn:
        teacher_tables = [
            "teacher_tasks",
            "student_subscription_lesson_usage",
            "student_payment_history",
            "student_payment_plans",
            "lesson_reminder_sent",
            "teacher_reminder_settings",
            "schedule_moves",
            "schedule_slots",
            "group_schedule_moves",
            "group_schedule_slots",
            "teacher_groups",
            "students",
        ]
        for table in teacher_tables:
            if _table_exists(conn, table):
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE teacher_telegram_user_id=?",
                    (uid,),
                )
                deleted[table] = cur.rowcount

        if _table_exists(conn, "teachers"):
            cur = conn.execute(
                "DELETE FROM teachers WHERE telegram_user_id=?",
                (uid,),
            )
            deleted["teachers"] = cur.rowcount
        conn.commit()
    return deleted


async def reset_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delete_teacher_data(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(
        "✅ Твои данные в ПРЕПОДМИН удалены полностью.\n\n"
        "Профиль преподавателя, ученики, группы, расписание, переносы, напоминания, оплаты, абонементы и задачи очищены.\n"
        "Нажми /start — начнём настройку заново."
    )


def build_app():
    app = reminders.build_app()
    app.add_handler(CommandHandler("reset_me", reset_me), group=0)
    return app
