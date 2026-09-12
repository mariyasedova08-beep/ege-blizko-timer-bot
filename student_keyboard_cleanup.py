"""Remove stale persistent parent reply keyboards from student accounts.

Telegram keeps persistent reply keyboards until the bot explicitly replaces or
removes them. This module cleans up former accidental self-parent links and also
makes /start clear a stale parent keyboard for any active student who is not a
current parent.
"""
import sqlite3

from telegram import ReplyKeyboardRemove

import parent_cabinet

bot = parent_cabinet.bot
live7 = parent_cabinet.live7
_INSTALLED = False


def ensure_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_keyboard_cleanup_log (
                telegram_user_id INTEGER PRIMARY KEY,
                cleaned_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _is_active_student(uid):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM students WHERE active=1 AND telegram_user_id=? LIMIT 1",
            (int(uid),),
        ).fetchone())


def _needs_one_time_cleanup(uid):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        already = conn.execute(
            "SELECT 1 FROM student_keyboard_cleanup_log WHERE telegram_user_id=? LIMIT 1",
            (int(uid),),
        ).fetchone()
        if already:
            return False
        # Only target accounts that had an accidental self-parent link in the past.
        row = conn.execute(
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
        return bool(row)


def _mark_clean(uid):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO student_keyboard_cleanup_log (telegram_user_id, cleaned_at) VALUES (?, ?)",
            (int(uid), parent_cabinet.now().isoformat()),
        )
        conn.commit()


async def cleanup_tick(context):
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT s.telegram_user_id
            FROM students s
            JOIN parent_links pl ON pl.student_id = s.id
            WHERE s.active = 1
              AND s.telegram_user_id IS NOT NULL
              AND pl.parent_telegram_user_id = s.telegram_user_id
              AND pl.active = 0
            """
        ).fetchall()
    for (uid,) in rows:
        uid = int(uid)
        if parent_cabinet.is_parent(uid) or not _needs_one_time_cleanup(uid):
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text="✅ Меню обновлено. Родительские кнопки убраны — у тебя снова обычный ученический режим.",
                reply_markup=ReplyKeyboardRemove(),
            )
            _mark_clean(uid)
            print(f"Student stale parent keyboard removed uid={uid}", flush=True)
        except Exception as exc:
            print(f"Student keyboard cleanup failed uid={uid}: {exc}", flush=True)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_table()

    # Clear stale parent keyboard on /start for any real student who is not a parent.
    previous_start = live7.start_router

    async def start_router_with_cleanup(update, context):
        if (
            update.effective_chat.type == "private"
            and update.effective_user
            and _is_active_student(update.effective_user.id)
            and not parent_cabinet.is_parent(update.effective_user.id)
        ):
            await update.message.reply_text(
                "Обновляю ученическое меню 💗",
                reply_markup=ReplyKeyboardRemove(),
            )
        return await previous_start(update, context)

    live7.start_router = start_router_with_cleanup

    previous_tick = live7.friday_trivial_tick

    async def combined_tick(context):
        try:
            await previous_tick(context)
        finally:
            await cleanup_tick(context)

    live7.friday_trivial_tick = combined_tick
    _INSTALLED = True
    print("Student stale parent keyboard cleanup ready", flush=True)
