"""Connect homework/attendance to the existing PREPODMIN Today flow without replacing package deductions."""

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes, MessageHandler, filters

import teacher_product_today_actions as today_actions
import teacher_product_homework_attendance as homework_attendance


async def today_with_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    lesson_date = __import__("datetime").datetime.now(today_actions.schedule.tz(uid)).date()

    # Reuse the existing Today + package-deduction flow exactly as-is.
    try:
        await today_actions.today_with_package_actions(update, context)
    except ApplicationHandlerStop:
        pass

    # Then add attendance for all today's individual/group lessons.
    await homework_attendance.send_today_attendance_prompt(update.message, uid, lesson_date)
    raise ApplicationHandlerStop


def install(app):
    app.add_handler(
        MessageHandler(filters.Regex(r"^📍 Сегодня$"), today_with_attendance),
        group=-19,
    )
    print("PREPODMIN Today connected to attendance without changing package deductions", flush=True)
    return app
