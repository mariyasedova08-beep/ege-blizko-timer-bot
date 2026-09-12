"""Student-facing personal payment view for Grade 11 course."""
import html

from telegram import ReplyKeyboardMarkup

import run_bot_live85
import payment_delivery
import payment_schedule

live85 = run_bot_live85
live79 = live85.live79
live7 = live79.live7

PAYMENT_BUTTON = "💳 Оплата"

# Keep the existing student tools and add a dedicated payment button.
live7.STUDENT_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🧪 Тривиальные названия"],
        ["❌ Мои ошибки", "📊 Моя статистика"],
        [PAYMENT_BUTTON],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

_original_student_text_router = live7.student_text_router


def _row_for_telegram_user(telegram_user_id):
    matches = []
    for row in payment_schedule.schedule_rows():
        recipient = payment_delivery._recipient(row)
        if recipient and int(recipient[0]) == int(telegram_user_id):
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _paid_period_label(row):
    paid = []
    for period, month in payment_schedule._payments.PAYMENT_PERIODS:
        if payment_schedule.cents(row["coverage"].get(period, 0)) > 0:
            paid.append(month.lower())
    if not paid:
        return "оплата пока не отмечена"
    if len(paid) == len(payment_schedule._payments.PAYMENT_PERIODS):
        return "весь курс"
    if len(paid) == 1:
        return paid[0]
    return f"{paid[0]}–{paid[-1]}"


def personal_payment_text(telegram_user_id):
    row = _row_for_telegram_user(telegram_user_id)
    if not row:
        return (
            "💳 <b>Оплата</b>\n\n"
            "Информация об оплате для этого кабинета пока не подключена. "
            "Если это ошибка, напиши Маше 💗"
        )

    lines = [
        "💳 <b>Оплата курса</b>",
        "",
        f"Ученик: <b>{html.escape(row['name'])}</b>",
        f"График: <b>{payment_schedule.CADENCE_LABELS[row['cadence']]}</b>",
        f"✅ Оплачено: <b>{html.escape(_paid_period_label(row))}</b>",
    ]

    item = row.get("next_invoice")
    if row["cadence"] == "prepaid" or not item:
        if row["cadence"] == "review":
            lines.extend([
                "",
                "⚠️ График оплаты сейчас уточняется. Если у тебя есть вопрос по оплате, напиши Маше.",
            ])
        else:
            lines.extend([
                "",
                "🏁 <b>Курс оплачен полностью.</b>",
                "Дополнительные платежи не требуются 💗",
            ])
        return "\n".join(lines)

    lines.extend([
        "",
        f"Следующая оплата: <b>{html.escape(item['label'])}</b>",
        f"Сумма: <b>{payment_schedule.money(item['remaining_cents'])}</b>",
        f"Оплатить до: <b>{item['due_date']:%d.%m.%Y}</b> включительно.",
    ])
    if item["status"] == "overdue":
        lines.append("🔴 <b>Срок оплаты уже прошёл.</b>")
    lines.extend([
        "",
        "После оплаты, пожалуйста, пришли Маше расчётный чек, чтобы она отметила платёж. 💗",
        "Если ты уже оплатил(а), а здесь ещё не обновилось — просто пришли чек Маше.",
    ])
    return "\n".join(lines)


async def student_text_router(update, context):
    if (
        update.effective_chat.type == "private"
        and update.message
        and update.message.text
        and update.message.text.strip() == PAYMENT_BUTTON
    ):
        await update.message.reply_text(
            personal_payment_text(update.effective_user.id),
            parse_mode="HTML",
            reply_markup=live7.STUDENT_KEYBOARD,
        )
        return
    await _original_student_text_router(update, context)


live7.student_text_router = student_text_router
print("Student payment cabinet button ready", flush=True)
