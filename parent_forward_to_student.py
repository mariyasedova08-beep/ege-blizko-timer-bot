"""Admin flow: send a parent-cabinet invitation to a student for forwarding to a parent."""
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import parent_admin_ui
import parent_cabinet
import parent_invite_campaign

bot = parent_cabinet.bot

_previous_parents_markup = parent_admin_ui.parents_markup
_previous_admin_parent_callback = parent_admin_ui.admin_parent_callback


def _shown_name(student):
    try:
        return str(student[1] or "Ученик")
    except Exception:
        return "Ученик"


def parents_markup_with_forward():
    base = _previous_parents_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:parents:forward"
        for row in rows for button in row
    ):
        insert_at = 2 if len(rows) >= 2 else len(rows)
        rows.insert(insert_at, [
            InlineKeyboardButton(
                "📤 Отправить ученику для родителя",
                callback_data="cab:parents:forward",
            )
        ])
    return InlineKeyboardMarkup(rows)


parent_admin_ui.parents_markup = parents_markup_with_forward


def picker_markup():
    rows = []
    for student in parent_admin_ui._active_students():
        sid = int(student[0])
        telegram_user_id = student[4]
        icon = "📤" if telegram_user_id is not None else "⚠️"
        label = f"{icon} {_shown_name(student)}"
        if telegram_user_id is None:
            label += " · Telegram не привязан"
        if len(label) > 60:
            label = label[:59] + "…"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"cab:parents:forward:preview:{sid}")
        ])
    rows.append([InlineKeyboardButton("← Родители", callback_data="cab:parents")])
    return InlineKeyboardMarkup(rows)


def confirm_markup(student_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Отправить ученику",
            callback_data=f"cab:parents:forward:send:{int(student_id)}",
        )],
        [InlineKeyboardButton("← Выбрать другого", callback_data="cab:parents:forward")],
        [InlineKeyboardButton("← Родители", callback_data="cab:parents")],
    ])


def student_message(link):
    safe_link = html.escape(link)
    return (
        "Привет! 💗\n\n"
        "Пожалуйста, перешли это сообщение одному из родителей.\n\n"
        "Я подключила отдельный <b>личный кабинет родителя</b> в боте <b>«ЕГЭ БЛИЗКО»</b>.\n\n"
        "В нём родитель сможет посмотреть:\n"
        "🚦 как сейчас идут дела\n"
        "📊 успеваемость\n"
        "📝 результаты пробников\n"
        "🏠 домашние работы\n"
        "🎓 посещаемость\n"
        "💳 информацию об оплате\n\n"
        "Чтобы подключить кабинет именно к твоим данным, родителю нужно перейти по персональной ссылке ниже и нажать <b>Start / Начать</b>:\n\n"
        f"{safe_link}\n\n"
        "Ссылка предназначена для родителя и привяжет кабинет именно к твоему профилю.\n\n"
        "Если возникнут вопросы, в кабинете можно связаться с <b>Марией Александровной</b>. 💗"
    )


async def admin_parent_callback_with_forward(update, context):
    query = update.callback_query
    if not query or not parent_admin_ui._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:parents:forward":
        await query.answer()
        await query.edit_message_text(
            "📤 <b>Отправить ученику для родителя</b>\n\n"
            "Выбери ученика. Бот сначала покажет превью и только после подтверждения отправит ему готовое сообщение с персональной ссылкой.\n\n"
            "📤 — Telegram ученика привязан\n"
            "⚠️ — отправить автоматически пока нельзя",
            parse_mode="HTML",
            reply_markup=picker_markup(),
        )
        return

    if data.startswith("cab:parents:forward:preview:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await query.answer("Не удалось определить ученика", show_alert=True)
            return
        student = parent_cabinet.student_by_id(student_id)
        if not student:
            await query.answer("Ученик сейчас недоступен", show_alert=True)
            return
        if student[4] is None:
            await query.answer(
                "У ученика не привязан Telegram. Сначала нужно привязать его аккаунт.",
                show_alert=True,
            )
            return

        await query.answer()
        await query.edit_message_text(
            "📤 <b>Проверка перед отправкой</b>\n\n"
            f"Ученик: <b>{html.escape(_shown_name(student))}</b>\n\n"
            "После подтверждения бот отправит ученику сообщение с персональной ссылкой на кабинет родителя. "
            "Сам родитель сообщение напрямую от бота на этом шаге не получает.",
            parse_mode="HTML",
            reply_markup=confirm_markup(student_id),
        )
        return

    if data.startswith("cab:parents:forward:send:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await query.answer("Не удалось определить ученика", show_alert=True)
            return
        student = parent_cabinet.student_by_id(student_id)
        if not student:
            await query.answer("Ученик сейчас недоступен", show_alert=True)
            return
        telegram_user_id = student[4]
        if telegram_user_id is None:
            await query.answer("Telegram ученика не привязан", show_alert=True)
            return

        token, created = parent_invite_campaign._get_or_create_invite(student_id)
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=parent_{token}"

        try:
            await context.bot.send_message(
                chat_id=int(telegram_user_id),
                text=student_message(link),
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍👩‍👧 Открыть кабинет родителя", url=link)]
                ]),
            )
        except Exception as exc:
            await query.answer("Не удалось отправить сообщение ученику", show_alert=True)
            print(
                f"PARENT_FORWARD failed student_id={student_id} telegram={telegram_user_id} error={type(exc).__name__}: {exc}",
                flush=True,
            )
            return

        await query.answer("Отправлено ученику")
        await query.edit_message_text(
            "✅ <b>Сообщение отправлено ученику</b>\n\n"
            f"Ученик: <b>{html.escape(_shown_name(student))}</b>\n"
            f"Ссылка: {'создана новая' if created else 'использована действующая'}\n\n"
            "Теперь ученику нужно просто переслать это сообщение одному из родителей.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Отправить другому", callback_data="cab:parents:forward")],
                [InlineKeyboardButton("← Родители", callback_data="cab:parents")],
            ]),
        )
        print(
            f"PARENT_FORWARD sent student_id={student_id} telegram={telegram_user_id} invite_created={int(created)}",
            flush=True,
        )
        return

    await _previous_admin_parent_callback(update, context)


parent_admin_ui.admin_parent_callback = admin_parent_callback_with_forward
print("Parent forward-to-student flow ready", flush=True)
