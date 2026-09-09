import sqlite3
from datetime import datetime

import run_bot_live7

live7 = run_bot_live7
bot = live7.bot


# Ошибка считается «закрытой» только правильным ответом ПОСЛЕ ошибки.
# Предыдущие правильные ответы не должны скрывать новую ошибку.
def record_attempt(user_id, item_id, direction, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO trivial_attempts (telegram_user_id, item_id, direction, correct, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, item_id, direction, 1 if is_correct else 0, now),
        )
        row = conn.execute(
            """
            SELECT error_count, correct_count
            FROM trivial_errors
            WHERE telegram_user_id = ? AND item_id = ?
            """,
            (user_id, item_id),
        ).fetchone()

        if row is None:
            error_count = 0 if is_correct else 1
            correct_count = 0
            conn.execute(
                """
                INSERT INTO trivial_errors (
                    telegram_user_id, item_id, error_count, correct_count, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, item_id, error_count, correct_count, now),
            )
        elif is_correct:
            error_count, correct_count = row
            if error_count > correct_count:
                conn.execute(
                    """
                    UPDATE trivial_errors
                    SET correct_count = correct_count + 1, updated_at = ?
                    WHERE telegram_user_id = ? AND item_id = ?
                    """,
                    (now, user_id, item_id),
                )
            else:
                conn.execute(
                    "UPDATE trivial_errors SET updated_at = ? WHERE telegram_user_id = ? AND item_id = ?",
                    (now, user_id, item_id),
                )
        else:
            conn.execute(
                """
                UPDATE trivial_errors
                SET error_count = error_count + 1, updated_at = ?
                WHERE telegram_user_id = ? AND item_id = ?
                """,
                (now, user_id, item_id),
            )
        conn.commit()


live7.record_attempt = record_attempt


_original_trivial_command = live7.trivial_command


async def routed_trivial_command(update, context):
    command = (update.message.text or "").split()[0].split("@")[0].lower()
    if update.effective_chat.type != "private":
        await _original_trivial_command(update, context)
        return

    if command == "/trivial10":
        if live7.start_session_context(context, update.effective_user, "mixed"):
            await live7.send_current_question(update, context)
        return

    if command == "/trivialmistakes":
        if live7.start_session_context(context, update.effective_user, "mistakes"):
            await live7.send_current_question(update, context)
        else:
            await update.message.reply_text("❌ Ошибок для повторения пока нет. Отличная работа 💗")
        return

    await _original_trivial_command(update, context)


live7.trivial_command = routed_trivial_command


if __name__ == "__main__":
    live7.main()
