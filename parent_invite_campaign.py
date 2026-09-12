"""Prepare a reviewed parent invitation campaign from Maria's admin cabinet."""
import html
import secrets
import sqlite3
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import parent_admin_ui
import parent_cabinet

bot = parent_cabinet.bot

_previous_parents_markup = parent_admin_ui.parents_markup
_previous_admin_parent_callback = parent_admin_ui.admin_parent_callback


def _linked_student_ids():
    parent_cabinet.ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return {
            int(row[0])
            for row in conn.execute(
                "SELECT DISTINCT student_id FROM parent_links WHERE active = 1"
            ).fetchall()
        }


def _active_invite(student_id):
    parent_cabinet.ensure_tables()
    now_iso = parent_cabinet.now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT token, expires_at
            FROM parent_invites
            WHERE student_id = ? AND used_at IS NULL AND expires_at >= ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (int(student_id), now_iso),
        ).fetchone()


def _get_or_create_invite(student_id):
    existing = _active_invite(student_id)
    if existing:
        return existing[0], False
    created = parent_cabinet.now()
    expires = created + timedelta(days=30)
    token = secrets.token_hex(12)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO parent_invites(token, student_id, created_at, expires_at) VALUES(?,?,?,?)",
            (token, int(student_id), created.isoformat(), expires.isoformat()),
        )
        conn.commit()
    return token, True


def campaign_counts():
    students = parent_admin_ui._active_students()
    linked = _linked_student_ids()
    waiting = [student for student in students if int(student[0]) not in linked]
    with_invite = sum(1 for student in waiting if _active_invite(student[0]))
    return len(students), len(linked), len(waiting), with_invite


def campaign_text():
    total, linked, waiting, with_invite = campaign_counts()
    return (
        "📣 <b>Рассылка родителям</b>\n\n"
        f"Активных учеников: <b>{total}</b>\n"
        f"Родитель уже подключён: <b>{linked}</b>\n"
        f"Нужно пригласить: <b>{waiting}</b>\n"
        f"Из них уже есть действующая ссылка: <b>{with_invite}</b>\n\n"
        "На этом этапе бот <b>не пишет родителям сам</b>. Он подготовит для Марии Александровны "
        "отдельное готовое сообщение для каждого ребёнка с персональной ссылкой. После проверки его можно переслать родителю."
    )


def campaign_markup():
    _total, _linked, waiting, _with_invite = campaign_counts()
    rows = []
    if waiting:
        rows.append([InlineKeyboardButton(
            f"📄 Сформировать {waiting} приглашений",
            callback_data="cab:parents:campaign:confirm",
        )])
    rows.extend([
        [InlineKeyboardButton("🔄 Обновить", callback_data="cab:parents:campaign")],
        [InlineKeyboardButton("← Родители", callback_data="cab:parents")],
    ])
    return InlineKeyboardMarkup(rows)


def confirm_markup():
    _total, _linked, waiting, _with_invite = campaign_counts()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"✅ Да, подготовить {waiting}",
            callback_data="cab:parents:campaign:prepare",
        )],
        [InlineKeyboardButton("← Отмена", callback_data="cab:parents:campaign")],
    ])


def invite_message(student_name, link):
    safe_name = html.escape(str(student_name or "ребёнок"))
    safe_link = html.escape(link)
    return (
        "Здравствуйте! 💗\n\n"
        "Я подключила для родителей отдельный личный кабинет в Telegram-боте <b>«ЕГЭ БЛИЗКО»</b>.\n\n"
        f"Кабинет привязан к ученику: <b>{safe_name}</b>.\n\n"
        "В нём вы сможете самостоятельно посмотреть:\n"
        "🚦 общий статус и текущую динамику\n"
        "📊 успеваемость\n"
        "📝 результаты пробников\n"
        "🏠 домашние работы\n"
        "🎓 посещаемость занятий\n"
        "💳 информацию об оплате и срок следующего платежа\n\n"
        "Кабинет нужен для того, чтобы основные результаты и организационные моменты были собраны в одном месте. "
        "При этом отдельная цифра или один неудачный результат — не повод переживать: я вижу динамику учеников со своей стороны, "
        "и если ситуация действительно потребует внимания родителя, обязательно сообщу об этом отдельно.\n\n"
        "По любому вопросу об обучении или оплате в кабинете также можно связаться со мной — <b>Марией Александровной</b>.\n\n"
        "Чтобы подключить кабинет именно к вашему ребёнку, перейдите по персональной ссылке:\n\n"
        f"{safe_link}\n\n"
        "Ссылка персональная, одноразовая и привязывает кабинет только к данным вашего ребёнка. 💗"
    )


def parents_markup_with_campaign():
    base = _previous_parents_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:parents:campaign"
        for row in rows for button in row
    ):
        insert_at = 1 if rows else 0
        rows.insert(insert_at, [
            InlineKeyboardButton("📣 Подготовить рассылку", callback_data="cab:parents:campaign")
        ])
    return InlineKeyboardMarkup(rows)


parent_admin_ui.parents_markup = parents_markup_with_campaign


async def admin_parent_callback_with_campaign(update, context):
    query = update.callback_query
    if not query or not parent_admin_ui._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:parents:campaign":
        await query.answer()
        await query.edit_message_text(
            campaign_text(), parse_mode="HTML", reply_markup=campaign_markup()
        )
        return

    if data == "cab:parents:campaign:confirm":
        _total, _linked, waiting, _with_invite = campaign_counts()
        if not waiting:
            await query.answer("Все родители уже подключены", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            "📄 <b>Подготовить приглашения?</b>\n\n"
            f"Будет сформировано <b>{waiting}</b> персональных сообщений и отправлено только в ваш админский чат для проверки.\n\n"
            "Родителям на этом шаге ничего не отправляется.",
            parse_mode="HTML",
            reply_markup=confirm_markup(),
        )
        return

    if data == "cab:parents:campaign:prepare":
        students = parent_admin_ui._active_students()
        linked = _linked_student_ids()
        waiting = [student for student in students if int(student[0]) not in linked]
        if not waiting:
            await query.answer("Все родители уже подключены", show_alert=True)
            return
        await query.answer("Готовлю персональные приглашения")
        me = await context.bot.get_me()
        created_count = 0
        reused_count = 0
        sent_count = 0
        failed = []
        for student in waiting:
            sid = int(student[0])
            token, created = _get_or_create_invite(sid)
            created_count += int(created)
            reused_count += int(not created)
            link = f"https://t.me/{me.username}?start=parent_{token}"
            try:
                await query.message.reply_text(
                    invite_message(parent_cabinet.student_name(student), link),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent_count += 1
            except Exception:
                failed.append(parent_cabinet.student_name(student))
        lines = [
            "✅ <b>Пакет родительской рассылки подготовлен</b>",
            "",
            f"Готовых сообщений: <b>{sent_count}</b>",
            f"Новых ссылок: <b>{created_count}</b>",
            f"Использованы уже действующие ссылки: <b>{reused_count}</b>",
            "",
            "Сообщения отправлены только вам для проверки. Родителям ничего автоматически не отправлялось.",
        ]
        if failed:
            lines.extend(["", "⚠️ Не удалось подготовить:", *[f"• {html.escape(name)}" for name in failed]])
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← Родители", callback_data="cab:parents")]
            ]),
        )
        return

    await _previous_admin_parent_callback(update, context)


parent_admin_ui.admin_parent_callback = admin_parent_callback_with_campaign
print("Parent invitation campaign preview ready", flush=True)
