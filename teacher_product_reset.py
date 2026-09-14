from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import teacher_product_mvp as base
import teacher_product_multiday as multiday


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
        # Delete dependent rows first. Every table below belongs directly to one teacher.
        teacher_tables = [
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
        "Профиль преподавателя, индивидуальные ученики, группы, расписание и переносы очищены.\n"
        "Нажми /start — начнём настройку заново."
    )


def build_app():
    multiday.apply()
    app = multiday.groups.build_app()
    # group=0 means the reset command is handled before conversation text handlers.
    app.add_handler(CommandHandler("reset_me", reset_me), group=0)
    return app
