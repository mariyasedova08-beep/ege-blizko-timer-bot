"""Clear group-members UX for PREPODMIN.

Navigation:
Ученики и группы -> Группы -> группа -> Состав группы -> Добавить ученика.
Uses student_reminder_people as the single source of group membership so homework,
attendance and Telegram delivery stay in sync.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_student_reminders as student_reminders

ADD_MEMBER_NAME = 720


def _members(uid, gid):
    return student_reminders._members(uid, gid)


def _groups_markup(uid):
    rows = groups.groups(uid)
    buttons = [
        [InlineKeyboardButton(f"👥 {r['name']}", callback_data=f"gmem:group:{r['id']}")]
        for r in rows[:60]
    ]
    buttons.append([InlineKeyboardButton("➕ Создать группу", callback_data="group:add")])
    if rows:
        buttons.append([InlineKeyboardButton("🗑 Удалить / архив", callback_data="group:remove")])
    buttons.append([InlineKeyboardButton("⬅️ К форматам", callback_data="people:back")])
    return InlineKeyboardMarkup(buttons)


async def groups_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    rows = groups.groups(uid)
    text = (
        f"👥 Группы: {len(rows)}\n\nНажми на группу, чтобы открыть её и управлять составом."
        if rows else
        "👥 Группы\n\nПока групп нет. Создай первую."
    )
    await q.edit_message_text(text, reply_markup=_groups_markup(uid))
    raise ApplicationHandlerStop


def _group_markup(gid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Состав группы", callback_data=f"gmem:members:{gid}")],
        [InlineKeyboardButton("⬅️ К группам", callback_data="people:groups")],
    ])


async def group_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        gid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    group = groups.get_group(uid, gid)
    if not group:
        await q.edit_message_text("Группа не найдена.")
        raise ApplicationHandlerStop
    members = _members(uid, gid)
    linked = sum(1 for m in members if m["telegram_user_id"])
    await q.edit_message_text(
        f"👥 {group['name']}\n\n"
        f"Учеников: {len(members)}\n"
        f"Telegram подключён: {linked}/{len(members)}\n\n"
        "Открой состав группы, чтобы добавить учеников или проверить подключение.",
        reply_markup=_group_markup(gid),
    )
    raise ApplicationHandlerStop


def _members_markup(uid, gid):
    members = _members(uid, gid)
    buttons = []
    for m in members[:60]:
        icon = "✅" if m["telegram_user_id"] else "⏳"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {m['name']}",
                callback_data=f"gmem:member:{m['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("➕ Добавить ученика", callback_data=f"gmem:add:{gid}")])
    buttons.append([InlineKeyboardButton("⬅️ К группе", callback_data=f"gmem:group:{gid}")])
    return InlineKeyboardMarkup(buttons)


def _members_text(uid, gid):
    group = groups.get_group(uid, gid)
    if not group:
        return None
    members = _members(uid, gid)
    lines = [f"👥 Состав группы • {group['name']}", ""]
    if members:
        for m in members:
            status = "✅ Telegram подключён" if m["telegram_user_id"] else "⏳ Telegram не подключён"
            lines.append(f"• {m['name']} — {status}")
    else:
        lines.append("Пока учеников нет.")
    lines += ["", "Нажми «➕ Добавить ученика», чтобы пополнить состав."]
    return "\n".join(lines)


async def members_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        gid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    text = _members_text(uid, gid)
    if text is None:
        await q.edit_message_text("Группа не найдена.")
        raise ApplicationHandlerStop
    await q.edit_message_text(text, reply_markup=_members_markup(uid, gid))
    raise ApplicationHandlerStop


async def member_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        pid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    with base.db() as conn:
        row = conn.execute(
            "SELECT * FROM student_reminder_people WHERE id=? AND teacher_id=? AND kind='group' AND active=1",
            (pid, uid),
        ).fetchone()
    if not row or not groups.get_group(uid, row["group_id"]):
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop
    gid = int(row["group_id"])
    status = "✅ Telegram подключён" if row["telegram_user_id"] else "⏳ Telegram пока не подключён"
    buttons = []
    if not row["telegram_user_id"]:
        buttons.append([InlineKeyboardButton("📨 Отправить ссылку ученику", url=student_reminders._share_url(row))])
    buttons.append([InlineKeyboardButton("🗑 Убрать из группы", callback_data=f"gmem:remove:{pid}")])
    buttons.append([InlineKeyboardButton("⬅️ К составу", callback_data=f"gmem:members:{gid}")])
    await q.edit_message_text(
        f"👤 {row['name']}\n\n{status}\n\n"
        "Ученик уже учитывается в посещаемости и домашних заданиях. "
        "Telegram нужен только для автоматических сообщений, ДЗ и напоминаний.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    raise ApplicationHandlerStop


async def add_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        gid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        return ConversationHandler.END
    group = groups.get_group(uid, gid)
    if not group:
        await q.edit_message_text("Группа не найдена.")
        return ConversationHandler.END
    context.user_data["gmem_gid"] = gid
    await q.edit_message_text(
        f"➕ Добавить ученика • {group['name']}\n\n"
        "Напиши имя ученика одним сообщением.\n"
        "Например: Алина"
    )
    return ADD_MEMBER_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    gid = context.user_data.pop("gmem_gid", None)
    name = (update.message.text or "").strip()
    if not gid or not groups.get_group(uid, gid):
        await update.message.reply_text("Группа не найдена. Открой её заново.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    if len(name) < 2 or len(name) > 100 or name.startswith("/"):
        await update.message.reply_text("Напиши имя ученика обычным текстом.")
        context.user_data["gmem_gid"] = gid
        return ADD_MEMBER_NAME
    existing = {str(m["name"]).strip().casefold() for m in _members(uid, gid)}
    if name.casefold() in existing:
        await update.message.reply_text(
            f"{name} уже есть в этой группе.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👥 К составу", callback_data=f"gmem:members:{gid}")
            ]]),
        )
        return ConversationHandler.END
    row = student_reminders.add_member(uid, gid, name)
    if not row:
        await update.message.reply_text("Не удалось добавить ученика. Попробуй ещё раз.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    await update.message.reply_text(
        f"✅ {name} добавлен(а) в группу.\n\n"
        "Он(а) уже будет учитываться в посещаемости и ДЗ. "
        "Telegram можно подключить сейчас или позже.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📨 Отправить ссылку ученику", url=student_reminders._share_url(row))],
            [InlineKeyboardButton("➕ Добавить ещё", callback_data=f"gmem:add:{gid}")],
            [InlineKeyboardButton("👥 К составу", callback_data=f"gmem:members:{gid}")],
        ]),
    )
    return ConversationHandler.END


async def remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        pid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    with base.db() as conn:
        row = conn.execute(
            "SELECT group_id,name FROM student_reminder_people WHERE id=? AND teacher_id=? AND kind='group' AND active=1",
            (pid, uid),
        ).fetchone()
        if row:
            conn.execute("UPDATE student_reminder_people SET active=0 WHERE id=?", (pid,))
            conn.commit()
    if not row:
        await q.edit_message_text("Ученик уже удалён или не найден.")
        raise ApplicationHandlerStop
    gid = int(row["group_id"])
    await q.edit_message_text(
        f"✅ {row['name']} убран(а) из группы.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👥 К составу", callback_data=f"gmem:members:{gid}")
        ]]),
    )
    raise ApplicationHandlerStop


def install(app):
    add_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_begin, pattern=r"^gmem:add:\d+$")],
        states={ADD_MEMBER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)]},
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(add_conversation, group=-16)
    app.add_handler(CallbackQueryHandler(groups_menu, pattern=r"^people:groups$"), group=-16)
    app.add_handler(CallbackQueryHandler(group_card, pattern=r"^gmem:group:\d+$"), group=-16)
    app.add_handler(CallbackQueryHandler(members_view, pattern=r"^gmem:members:\d+$"), group=-16)
    app.add_handler(CallbackQueryHandler(member_view, pattern=r"^gmem:member:\d+$"), group=-16)
    app.add_handler(CallbackQueryHandler(remove_member, pattern=r"^gmem:remove:\d+$"), group=-16)
    print("PREPODMIN group members UX ready: groups -> group -> members -> add student", flush=True)
    return app
