"""Admin UI for managing parent cabinets from Maria's cabinet."""
import secrets
import sqlite3
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler

import parent_cabinet
import run_bot_live85 as live85

bot = live85.bot
live23 = live85.live23
live15 = parent_cabinet.live15

_markup_patched = False
_original_build = ApplicationBuilder.build


def _admin_private(update):
    return update.effective_chat.type == "private" and bot.user_is_admin(update)


def _parent_counts():
    parent_cabinet.ensure_tables()
    now_iso = parent_cabinet.now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        linked = int(conn.execute(
            "SELECT COUNT(*) FROM parent_links WHERE active = 1"
        ).fetchone()[0] or 0)
        families = int(conn.execute(
            "SELECT COUNT(DISTINCT parent_telegram_user_id) FROM parent_links WHERE active = 1"
        ).fetchone()[0] or 0)
        pending = int(conn.execute(
            "SELECT COUNT(*) FROM parent_invites WHERE used_at IS NULL AND expires_at >= ?",
            (now_iso,),
        ).fetchone()[0] or 0)
    return linked, families, pending


def _active_students():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return live15._active_students(conn)


def _student_parent_state(student_id):
    now_iso = parent_cabinet.now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        linked = int(conn.execute(
            "SELECT COUNT(*) FROM parent_links WHERE student_id = ? AND active = 1",
            (int(student_id),),
        ).fetchone()[0] or 0)
        pending = int(conn.execute(
            "SELECT COUNT(*) FROM parent_invites WHERE student_id = ? AND used_at IS NULL AND expires_at >= ?",
            (int(student_id), now_iso),
        ).fetchone()[0] or 0)
    return linked, pending


def parents_text():
    linked, families, pending = _parent_counts()
    students = _active_students()
    return (
        "👨‍👩‍👧 <b>Родители</b>\n\n"
        f"Активных родительских привязок: <b>{linked}</b>\n"
        f"Родительских аккаунтов: <b>{families}</b>\n"
        f"Неиспользованных приглашений: <b>{pending}</b>\n"
        f"Активных учеников: <b>{len(students)}</b>\n\n"
        "Здесь можно создать персональную ссылку для родителя и посмотреть уже подключённые кабинеты."
    )


def parents_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Создать приглашение", callback_data="cab:parents:new")],
        [InlineKeyboardButton("👥 Подключённые родители", callback_data="cab:parents:linked")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="cab:parents")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def student_picker_markup():
    rows = []
    for student in _active_students():
        sid = int(student[0])
        linked, pending = _student_parent_state(sid)
        if linked:
            icon = "👨‍👩‍👧"
        elif pending:
            icon = "📨"
        else:
            icon = "➕"
        label = f"{icon} {parent_cabinet.student_name(student)}"
        if linked > 1:
            label += f" · {linked} родителя"
        elif linked == 1:
            label += " · подключён"
        elif pending:
            label += " · ссылка создана"
        if len(label) > 58:
            label = label[:57] + "…"
        rows.append([InlineKeyboardButton(label, callback_data=f"cab:parents:invite:{sid}")])
    rows.append([InlineKeyboardButton("← Родители", callback_data="cab:parents")])
    return InlineKeyboardMarkup(rows)


def linked_text():
    parent_cabinet.ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT parent_name, parent_username, parent_telegram_user_id, student_id, linked_at
            FROM parent_links
            WHERE active = 1
            ORDER BY linked_at DESC
            """
        ).fetchall()
    lines = ["👥 <b>Подключённые родители</b>", ""]
    if not rows:
        lines.append("Пока ни один родитель не подключён.")
        return "\n".join(lines)
    for parent_name, username, _uid, student_id, _linked_at in rows:
        student = parent_cabinet.student_by_id(student_id)
        if not student:
            continue
        parent = parent_name or "Родитель"
        if username:
            parent += f" (@{username})"
        lines.append(f"• <b>{parent_cabinet.student_name(student)}</b> — {parent}")
    return "\n".join(lines)


def _patch_cabinet_markup():
    global _markup_patched
    if _markup_patched:
        return
    previous = live23.cabinet_markup

    def cabinet_markup_with_parents():
        base = previous()
        rows = [list(row) for row in base.inline_keyboard]
        if not any(
            getattr(button, "callback_data", None) == "cab:parents"
            for row in rows for button in row
        ):
            insert_at = max(0, len(rows) - 1)
            rows.insert(insert_at, [
                InlineKeyboardButton("👨‍👩‍👧 Родители", callback_data="cab:parents")
            ])
        return InlineKeyboardMarkup(rows)

    live23.cabinet_markup = cabinet_markup_with_parents
    _markup_patched = True


async def admin_parent_callback(update, context):
    query = update.callback_query
    if not query or not _admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:parents":
        await query.answer()
        await query.edit_message_text(
            parents_text(), parse_mode="HTML", reply_markup=parents_markup()
        )
        return

    if data == "cab:parents:new":
        await query.answer()
        await query.edit_message_text(
            "➕ <b>Создать приглашение родителю</b>\n\nВыбери ученика.\n\n"
            "👨‍👩‍👧 — родитель уже подключён\n"
            "📨 — есть действующая ссылка\n"
            "➕ — приглашения ещё нет",
            parse_mode="HTML",
            reply_markup=student_picker_markup(),
        )
        return

    if data == "cab:parents:linked":
        await query.answer()
        await query.edit_message_text(
            linked_text(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить", callback_data="cab:parents:linked")],
                [InlineKeyboardButton("← Родители", callback_data="cab:parents")],
            ]),
        )
        return

    if data.startswith("cab:parents:invite:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await query.answer("Не удалось определить ученика", show_alert=True)
            return
        student = parent_cabinet.student_by_id(student_id)
        if not student:
            await query.answer("Ученик сейчас недоступен", show_alert=True)
            return

        parent_cabinet.ensure_tables()
        created = parent_cabinet.now()
        expires = created + timedelta(days=30)
        token = secrets.token_hex(12)
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            # Only one active unused invitation per child: older unused links expire now.
            conn.execute(
                """
                UPDATE parent_invites
                SET expires_at = ?
                WHERE student_id = ? AND used_at IS NULL AND expires_at > ?
                """,
                (created.isoformat(), student_id, created.isoformat()),
            )
            conn.execute(
                "INSERT INTO parent_invites(token, student_id, created_at, expires_at) VALUES(?,?,?,?)",
                (token, student_id, created.isoformat(), expires.isoformat()),
            )
            conn.commit()

        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=parent_{token}"
        await query.answer("Новая ссылка создана")
        await query.message.reply_text(
            "👨‍👩‍👧 <b>Персональная ссылка для родителя</b>\n\n"
            f"Ребёнок: <b>{parent_cabinet.student_name(student)}</b>\n"
            "Ссылка одноразовая и действует 30 дней. Предыдущая неиспользованная ссылка для этого ребёнка закрыта.\n\n"
            f"{link}\n\n"
            "После перехода родительский кабинет привяжется только к этому ребёнку.",
            parse_mode="HTML",
        )
        await query.edit_message_text(
            "✅ Ссылка создана.\n\nМожно выбрать другого ученика или вернуться в раздел родителей.",
            reply_markup=student_picker_markup(),
        )
        return


def build_with_parent_admin(self):
    # run_bot_live90 patches the latest admin cabinet before Application.build is called.
    # Patch the final markup here, while keeping its callback identity intact for startup checks.
    _patch_cabinet_markup()
    app = _original_build(self)
    # Registered during build, before the legacy generic cab:* handler is added by main().
    app.add_handler(CallbackQueryHandler(admin_parent_callback, pattern=r"^cab:parents(?:$|:)"))
    return app


ApplicationBuilder.build = build_with_parent_admin
print("Parent admin cabinet button hook ready", flush=True)
