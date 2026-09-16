"""Direct transfer entry in the teacher's main reply keyboard."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import CallbackQueryHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups

BUTTON = "↪️ Перенести занятие"


def transfer_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Индивидуальное", callback_data="transfer:individual")],
        [InlineKeyboardButton("👥 Группа", callback_data="transfer:group")],
    ])


async def transfer_menu(update, context):
    teacher = base.teacher(update.effective_user.id)
    if not teacher or not teacher["onboarding_completed_at"]:
        return
    await update.message.reply_text(
        "↪️ Перенести занятие\n\nКакое занятие переносим?",
        reply_markup=transfer_keyboard(),
    )


def install(app):
    rows = [list(row) for row in base.MAIN_KB.keyboard]
    if not any(button.text == BUTTON for row in rows for button in row):
        schedule_row = next(
            (i for i, row in enumerate(rows) if any(button.text == "📅 Расписание" for button in row)),
            len(rows) - 1,
        )
        rows.insert(schedule_row + 1, [BUTTON])
    base.MAIN_KB = ReplyKeyboardMarkup(rows, resize_keyboard=True)

    # Reuse the existing pickers and their date/time conversations. The button
    # adds a shorter route without creating a second transfer implementation.
    app.add_handler(MessageHandler(filters.Regex(r"^↪️ Перенести занятие$"), transfer_menu), group=-12)
    app.add_handler(CallbackQueryHandler(schedule.transfer_picker, pattern=r"^transfer:individual$"), group=-12)
    app.add_handler(CallbackQueryHandler(groups.group_transfer_picker, pattern=r"^transfer:group$"), group=-12)
    print("Direct lesson transfer button ready", flush=True)
