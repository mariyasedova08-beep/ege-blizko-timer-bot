"""Recover student accounts that still show a stale parent-cabinet button.

The parent self-link repair keeps student records and results untouched.  A
Telegram reply keyboard, however, can outlive that repair.  If an affected
student taps the old parent-cabinet button, replace it with the normal student
keyboard instead of silently ignoring the message.
"""

import sqlite3

import parent_cabinet
import parent_home_button
import run_bot_live90 as live90


bot = parent_cabinet.bot
live7 = live90.live7
PERSONAL_CABINET = parent_home_button.PERSONAL_CABINET


def _is_active_student(uid):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM students WHERE active=1 AND telegram_user_id=? LIMIT 1",
                (int(uid),),
            ).fetchone()
        )


def _had_repaired_self_link(uid):
    """Return true only for accounts targeted by the self-link repair."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM parent_links pl
                JOIN students s ON s.id = pl.student_id
                WHERE pl.parent_telegram_user_id = ?
                  AND s.telegram_user_id = ?
                  AND pl.active = 0
                LIMIT 1
                """,
                (int(uid), int(uid)),
            ).fetchone()
        )


_previous_text_router = live7.student_text_router


async def text_router_with_student_recovery(update, context):
    if (
        update.message
        and update.message.text
        and update.effective_chat.type == "private"
        and update.effective_user
        and update.message.text.strip() == PERSONAL_CABINET
    ):
        uid = int(update.effective_user.id)
        if (
            _is_active_student(uid)
            and not parent_cabinet.is_parent(uid)
            and _had_repaired_self_link(uid)
        ):
            await update.message.reply_text(
                "✅ Ученическое меню восстановлено 💗\n"
                "Родительский кабинет больше не привязан к этому аккаунту.",
                reply_markup=live7.STUDENT_KEYBOARD,
            )
            return
    return await _previous_text_router(update, context)


live7.student_text_router = text_router_with_student_recovery


def verify_student_recovery_wiring():
    if live7.student_text_router is not text_router_with_student_recovery:
        raise RuntimeError("Student cabinet recovery wiring check failed")
    if not PERSONAL_CABINET:
        raise RuntimeError("Student cabinet recovery button is empty")
    print("LIVE91: stale student parent-cabinet recovery ready", flush=True)


verify_student_recovery_wiring()
