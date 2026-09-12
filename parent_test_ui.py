"""Safe admin preview of the parent cabinet without creating a parent link."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import parent_admin_ui
import parent_cabinet

bot = parent_cabinet.bot
live7 = parent_cabinet.live7
live23 = parent_admin_ui.live23

TEST_EXIT = "↩️ Выйти из теста"
TEST_STATE = "parent_test_student_id"


def test_keyboard():
    return ReplyKeyboardMarkup(
        [
            [parent_cabinet.STATUS],
            [parent_cabinet.PROGRESS, parent_cabinet.PROBNIK],
            [parent_cabinet.HOMEWORK, parent_cabinet.ATTENDANCE],
            [parent_cabinet.PAYMENT],
            [parent_cabinet.CONTACT],
            [TEST_EXIT],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def test_picker_markup():
    rows = []
    for student in parent_admin_ui._active_students():
        rows.append([
            InlineKeyboardButton(
                parent_cabinet.student_name(student),
                callback_data=f"cab:parents:test:{int(student[0])}",
            )
        ])
    rows.append([InlineKeyboardButton("← Родители", callback_data="cab:parents")])
    return InlineKeyboardMarkup(rows)


_previous_parents_markup = parent_admin_ui.parents_markup


def parents_markup_with_test():
    base = _previous_parents_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:parents:test"
        for row in rows for button in row
    ):
        rows.insert(2, [
            InlineKeyboardButton("🧪 Тест родительского кабинета", callback_data="cab:parents:test")
        ])
    return InlineKeyboardMarkup(rows)


parent_admin_ui.parents_markup = parents_markup_with_test

_previous_admin_parent_callback = parent_admin_ui.admin_parent_callback


async def admin_parent_callback_with_test(update, context):
    query = update.callback_query
    if not query or not parent_admin_ui._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:parents:test":
        await query.answer()
        await query.edit_message_text(
            "🧪 <b>Тест родительского кабинета</b>\n\n"
            "Выбери ученика. Тестовый режим покажет тебе кабинет так, как его видит родитель, "
            "но не создаст настоящую родительскую привязку.",
            parse_mode="HTML",
            reply_markup=test_picker_markup(),
        )
        return

    if data.startswith("cab:parents:test:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await query.answer("Не удалось определить ученика", show_alert=True)
            return
        student = parent_cabinet.student_by_id(student_id)
        if not student:
            await query.answer("Ученик сейчас недоступен", show_alert=True)
            return
        context.user_data[TEST_STATE] = student_id
        await query.answer("Тестовый кабинет открыт")
        await query.edit_message_text(
            "✅ Тестовый режим запущен. Используй нижние кнопки так же, как это будет делать родитель."
        )
        await query.message.reply_text(
            "👨‍👩‍👧 <b>Кабинет родителя — ТЕСТ</b>\n\n"
            f"Ребёнок: <b>{parent_cabinet.student_name(student)}</b>\n\n"
            "Здесь можно посмотреть текущую динамику, пробники, домашние работы, посещаемость и оплату.",
            parse_mode="HTML",
            reply_markup=test_keyboard(),
        )
        await query.message.reply_text(parent_cabinet.status_text(student), reply_markup=test_keyboard())
        return

    await _previous_admin_parent_callback(update, context)


parent_admin_ui.admin_parent_callback = admin_parent_callback_with_test

_previous_text_router = live7.student_text_router


async def text_router_with_parent_test(update, context):
    if (
        update.effective_chat.type == "private"
        and bot.user_is_admin(update)
        and TEST_STATE in context.user_data
        and update.message
        and update.message.text
    ):
        text = update.message.text.strip()
        if text == TEST_EXIT:
            context.user_data.pop(TEST_STATE, None)
            await update.message.reply_text(
                "✅ Тест родительского кабинета завершён.",
                reply_markup=live23.ADMIN_KEYBOARD,
            )
            await live23.show_cabinet(update, context)
            return

        student = parent_cabinet.student_by_id(context.user_data.get(TEST_STATE))
        if not student:
            context.user_data.pop(TEST_STATE, None)
            await update.message.reply_text(
                "Тест завершён: ученик больше недоступен.",
                reply_markup=live23.ADMIN_KEYBOARD,
            )
            return

        if text == parent_cabinet.STATUS:
            message = parent_cabinet.status_text(student)
        elif text == parent_cabinet.PROGRESS:
            message = parent_cabinet.progress_text(student)
        elif text == parent_cabinet.PROBNIK:
            message = parent_cabinet.probnik_text(student)
        elif text == parent_cabinet.HOMEWORK:
            message = parent_cabinet.homework_text(student)
        elif text == parent_cabinet.ATTENDANCE:
            message = parent_cabinet.attendance_text(student)
        elif text == parent_cabinet.PAYMENT:
            message = parent_cabinet.payment_text(student)
        elif text == parent_cabinet.CONTACT:
            message = (
                "💬 Связаться с Марией Александровной\n\n"
                "В настоящем родительском кабинете эта кнопка позволяет перейти к личному сообщению "
                "Марии Александровне по вопросу обучения или оплаты."
            )
        else:
            message = "Используй кнопки тестового родительского кабинета ниже 👇"
        await update.message.reply_text(message, reply_markup=test_keyboard())
        return

    await _previous_text_router(update, context)


live7.student_text_router = text_router_with_parent_test
print("Parent cabinet admin test mode ready", flush=True)
