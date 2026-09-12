"""Update the payment admin UI after automatic delivery is enabled."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def patch(payment_schedule):
    if getattr(payment_schedule, "_delivery_ui_patched", False):
        return

    original_summary = payment_schedule.summary_text
    original_student = payment_schedule.student_text
    original_help = payment_schedule.help_text
    cabinet = payment_schedule._cabinet
    previous_callback = cabinet.cabinet_callback

    def summary_text():
        text = original_summary()
        return text.replace(
            "🔒 Проверка: автоотправка ученикам не включена.",
            "✅ Авторассылка включена с 28.09.2026 в 10:00. Повтор — 5-го, просрочка — с 8-го."
        )

    def student_text(student_id):
        text = original_student(student_id)
        return text.replace(
            "🔒 Сообщения ученику пока не отправляются.",
            "✅ Авторассылка включена; отправка идёт только при однозначной Telegram-привязке."
        )

    def help_text():
        text = original_help()
        return text.replace(
            "🔒 Сейчас доступны расчёт и черновики для Маши. Автоотправка ученикам не включена.",
            "✅ Авторассылка включена с 28.09.2026 в 10:00. Неоплатившим повтор — 5-го, сообщение о просрочке — с 8-го."
        )

    async def callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if data == "cab:payments:drafts" and cabinet._admin_private(update):
            await query.answer()
            await query.edit_message_text(
                "🔔 <b>Проверка напоминаний</b>\n\n"
                "Выбери ученика, чтобы увидеть текст. Авторассылка включена с 28.09.2026; "
                "фактическая отправка происходит только при неоплаченной сумме и привязанном Telegram.",
                parse_mode="HTML",
                reply_markup=payment_schedule.student_list_markup(drafts=True),
            )
            return
        await previous_callback(update, context)

    payment_schedule.summary_text = summary_text
    payment_schedule.student_text = student_text
    payment_schedule.help_text = help_text
    payment_schedule._payments.payments_summary_text = summary_text
    payment_schedule._payments.payment_student_text = student_text
    cabinet.cabinet_callback = callback
    payment_schedule._delivery_ui_patched = True
    print("Payment delivery admin UI patched", flush=True)
