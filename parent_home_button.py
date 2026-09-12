"""Add a persistent Personal cabinet button to real and test parent keyboards."""
from telegram import ReplyKeyboardMarkup

import parent_cabinet
import parent_test_ui

bot = parent_cabinet.bot
live7 = parent_cabinet.live7
live23 = parent_test_ui.live23

PERSONAL_CABINET = "👨‍👩‍👧 Личный кабинет"
parent_cabinet.PERSONAL_CABINET = PERSONAL_CABINET


def _real_parent_keyboard(uid):
    rows = [
        [PERSONAL_CABINET],
        [parent_cabinet.STATUS],
        [parent_cabinet.PROGRESS, parent_cabinet.PROBNIK],
        [parent_cabinet.HOMEWORK, parent_cabinet.ATTENDANCE],
        [parent_cabinet.PAYMENT],
        [parent_cabinet.CONTACT],
    ]
    if len(parent_cabinet.link_ids(uid)) > 1:
        rows.append([parent_cabinet.CHILD])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _test_keyboard():
    return ReplyKeyboardMarkup(
        [
            [PERSONAL_CABINET],
            [parent_cabinet.STATUS],
            [parent_cabinet.PROGRESS, parent_cabinet.PROBNIK],
            [parent_cabinet.HOMEWORK, parent_cabinet.ATTENDANCE],
            [parent_cabinet.PAYMENT],
            [parent_cabinet.CONTACT],
            [parent_test_ui.TEST_EXIT],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


parent_cabinet.keyboard = _real_parent_keyboard
parent_test_ui.test_keyboard = _test_keyboard

_previous_text_router = live7.student_text_router


async def text_router_with_parent_home(update, context):
    if not update.message or not update.message.text or update.effective_chat.type != "private":
        return await _previous_text_router(update, context)

    text = update.message.text.strip()

    # Make the test exit button recover the admin keyboard even if the test state was already cleared.
    if text == parent_test_ui.TEST_EXIT and bot.user_is_admin(update):
        context.user_data.pop(parent_test_ui.TEST_STATE, None)
        await update.message.reply_text(
            "✅ Тест родительского кабинета завершён.",
            reply_markup=live23.ADMIN_KEYBOARD,
        )
        await live23.show_cabinet(update, context)
        return

    if text == PERSONAL_CABINET:
        if bot.user_is_admin(update) and parent_test_ui.TEST_STATE in context.user_data:
            student = parent_cabinet.student_by_id(context.user_data.get(parent_test_ui.TEST_STATE))
            if not student:
                context.user_data.pop(parent_test_ui.TEST_STATE, None)
                await update.message.reply_text(
                    "Тест завершён: ученик больше недоступен.",
                    reply_markup=live23.ADMIN_KEYBOARD,
                )
                return
            await update.message.reply_text(
                "👨‍👩‍👧 Кабинет родителя — ТЕСТ\n\n"
                f"Ребёнок: {parent_cabinet.student_name(student)}\n\n"
                "Здесь можно посмотреть текущую динамику, пробники, домашние работы, посещаемость и оплату.",
                reply_markup=_test_keyboard(),
            )
            return

        if parent_cabinet.is_parent(update.effective_user.id):
            return await parent_cabinet.home(update, context)

    return await _previous_text_router(update, context)


live7.student_text_router = text_router_with_parent_home
print("Parent personal cabinet button ready", flush=True)
