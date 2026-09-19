"""Collapse the student persistent keyboard to one cabinet button.

The full student navigation lives inside the inline cabinet. Telegram may keep an
old reply keyboard on a user's phone, so stale former buttons are intercepted
and replaced on the next tap instead of continuing to expose duplicate menus.
"""
import sqlite3

from telegram import ReplyKeyboardMarkup

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

_INSTALLED = False


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
    global _INSTALLED
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

    print(
        "Student keyboard compact mode ready: cabinet-only; stale buttons redirect to cabinet",
        flush=True,
    )
