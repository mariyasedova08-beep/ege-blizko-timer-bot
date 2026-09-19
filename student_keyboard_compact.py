"""Collapse the student persistent keyboard to one cabinet button.

The full student navigation lives inside the inline cabinet. Telegram may keep an
old reply keyboard on a user's phone, so stale former buttons are intercepted
and replaced on the next tap instead of continuing to expose duplicate menus.
"""
import sqlite3

from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet

bot = live90.bot
live7 = live90.live7

CABINET_BUTTON = "👤 Мой кабинет"
COMPACT_KEYBOARD = ReplyKeyboardMarkup(
    [[CABINET_BUTTON]],
    resize_keyboard=True,
    is_persistent=True,
)

STALE_BUTTONS = {
    CABINET_BUTTON,
    "🧪 Тривиальные названия",
    "❌ Мои ошибки",
    "📊 Моя статистика",
    "💳 Оплата",
    "⚛️ Неметаллы",
    "🧪 Свойства оксидов",
    "🧪 Оксиды",
    "🧪 Кислоты",
    "⚗️ Металлы",
}

PUSH_BATCH = "student-compact-keyboard-v1"
_INSTALLED = False
_ORIGINAL_BUILD = None


def _ensure_push_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_compact_keyboard_push (
                batch_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(batch_key, telegram_user_id)
            )
            """
        )
        conn.commit()


def _push_recipients():
    admin_id = bot.get_admin_id()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT telegram_user_id
            FROM students
            WHERE active=1 AND telegram_user_id IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
    result = []
    for (uid,) in rows:
        uid = int(uid)
        if admin_id and uid == int(admin_id):
            continue
        result.append(uid)
    return result


def _already_pushed(uid):
    _ensure_push_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            """
            SELECT 1
            FROM student_compact_keyboard_push
            WHERE batch_key=? AND telegram_user_id=?
            LIMIT 1
            """,
            (PUSH_BATCH, int(uid)),
        ).fetchone())


def _mark_pushed(uid):
    from datetime import datetime
    _ensure_push_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO student_compact_keyboard_push(
                batch_key,telegram_user_id,sent_at
            ) VALUES(?,?,?)
            """,
            (PUSH_BATCH, int(uid), datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


async def _force_compact_keyboard(context):
    sent = skipped = failed = 0
    for uid in _push_recipients():
        if _already_pushed(uid):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "💗 Меню обновлено.\n\n"
                    "Теперь всё находится внутри «👤 Мой кабинет», "
                    "а снизу остаётся только одна кнопка."
                ),
                reply_markup=COMPACT_KEYBOARD,
            )
            _mark_pushed(uid)
            sent += 1
        except Exception as exc:
            failed += 1
            print(
                f"Student compact keyboard push failed uid={uid} error={type(exc).__name__}",
                flush=True,
            )
    print(
        f"Student compact keyboard push: sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


def _is_active_student(uid):
    if uid is None:
        return False
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM students
                WHERE active=1 AND telegram_user_id=?
                LIMIT 1
                """,
                (int(uid),),
            ).fetchone()
        )


def install():
    global _INSTALLED, _ORIGINAL_BUILD
    if _INSTALLED:
        return
    _INSTALLED = True

    # Any future /start or menu restore uses the compact keyboard.
    live7.STUDENT_KEYBOARD = COMPACT_KEYBOARD

    previous_text_router = live7.student_text_router

    async def student_text_router_compact(update, context):
        if (
            update.effective_chat.type == "private"
            and update.effective_user
            and not bot.user_is_admin(update)
            and _is_active_student(update.effective_user.id)
            and update.message
            and update.message.text
        ):
            text = update.message.text.strip()
            if text in STALE_BUTTONS:
                await update.effective_message.reply_text(
                    "Меню ученика обновлено 💗\n"
                    "Теперь всё находится в одном месте — в «Мой кабинет».",
                    reply_markup=COMPACT_KEYBOARD,
                )
                student = student_cabinet._student_by_telegram(
                    update.effective_user.id
                )
                if student:
                    await student_cabinet.show_student_cabinet(
                        update,
                        context,
                        student=student,
                    )
                return
        return await previous_text_router(update, context)

    live7.student_text_router = student_text_router_compact

    # Force Telegram to replace already-cached reply keyboards for every active student.
    _ORIGINAL_BUILD = ApplicationBuilder.build

    def build_with_compact_push(self):
        application = _ORIGINAL_BUILD(self)
        application.job_queue.run_once(
            _force_compact_keyboard,
            when=3,
            name="student_compact_keyboard_push_v1",
        )
        return application

    ApplicationBuilder.build = build_with_compact_push

    print(
        "Student keyboard compact mode ready: cabinet-only; stale buttons redirect to cabinet",
        flush=True,
    )
