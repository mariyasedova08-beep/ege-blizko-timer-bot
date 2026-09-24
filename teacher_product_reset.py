"""Safe teacher-only reset flow for a full PREPODMIN end-to-end test."""
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, ContextTypes

import teacher_product_mvp as base
import teacher_product_reminders as reminders


NOTICE_TEXT = (
    "Привет! Я сейчас перезапускаю ПРЕП | АДМИН и заново настраиваю данные "
    "для полного тестирования. На время могут исчезнуть расписание, ДЗ и уведомления. "
    "Когда настройка будет готова, я пришлю новое сообщение. Пока ничего делать не нужно 💗\n\n"
    "Маша"
)


def _table_exists(conn, table_name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone())


def _columns(conn, table_name):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()}


def linked_students(uid):
    """Return the bounded notification audience: active, Telegram-linked pupils."""
    with base.db() as conn:
        if not _table_exists(conn, "student_reminder_people"):
            return []
        rows = conn.execute(
            """
            SELECT id,name,telegram_user_id,kind,group_id
            FROM student_reminder_people
            WHERE teacher_id=? AND active=1 AND telegram_user_id IS NOT NULL
            ORDER BY lower(name),id
            """,
            (int(uid),),
        ).fetchall()
    unique = {}
    for row in rows:
        chat_id = int(row["telegram_user_id"])
        if chat_id not in unique:
            unique[chat_id] = dict(row)
    return list(unique.values())


def create_backup(uid):
    """Copy the SQLite database before a destructive teacher-scoped reset."""
    source = Path(base.DB_PATH)
    backup_dir = source.parent / "prepodmin_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"before-e2e-{int(uid)}-{stamp}.sqlite3"
    with base.db() as source_conn, sqlite3.connect(target) as backup_conn:
        source_conn.backup(backup_conn)
    return str(target)


def delete_teacher_data(uid):
    """Delete only this teacher's data, including newer product tables."""
    uid = int(uid)
    deleted = {}
    with base.db() as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]

        parent_specs = [
            ("teacher_homework", "id", "teacher_telegram_user_id", "teacher_homework_status", "assignment_id"),
            ("teacher_homework", "id", "teacher_telegram_user_id", "teacher_homework_reminder_sent", "assignment_id"),
            ("teacher_courses", "id", "teacher_telegram_user_id", "teacher_course_groups", "course_id"),
            ("teacher_courses", "id", "teacher_telegram_user_id", "teacher_course_students", "course_id"),
            ("student_reminder_people", "id", "teacher_id", "student_lesson_messages", "person_id"),
            ("student_reminder_people", "id", "teacher_id", "student_lesson_replies", "person_id"),
        ]
        for parent, parent_id, owner_column, child, child_fk in parent_specs:
            if parent not in tables or child not in tables:
                continue
            ids = [r[0] for r in conn.execute(
                f'SELECT "{parent_id}" FROM "{parent}" WHERE "{owner_column}"=?',
                (uid,),
            ).fetchall()]
            if ids:
                marks = ",".join("?" for _ in ids)
                cur = conn.execute(f'DELETE FROM "{child}" WHERE "{child_fk}" IN ({marks})', ids)
                deleted[child] = deleted.get(child, 0) + max(0, cur.rowcount)

        for table in tables:
            columns = _columns(conn, table)
            owner_column = None
            if "teacher_telegram_user_id" in columns:
                owner_column = "teacher_telegram_user_id"
            elif "teacher_id" in columns:
                owner_column = "teacher_id"
            if owner_column:
                cur = conn.execute(f'DELETE FROM "{table}" WHERE "{owner_column}"=?', (uid,))
                deleted[table] = deleted.get(table, 0) + max(0, cur.rowcount)

        if "teachers" in tables:
            cur = conn.execute("DELETE FROM teachers WHERE telegram_user_id=?", (uid,))
            deleted["teachers"] = deleted.get("teachers", 0) + max(0, cur.rowcount)
        conn.commit()
    return deleted


def _audience_text(rows):
    if not rows:
        return "Подключённых действующих учеников не найдено."
    names = "\n".join(f"• {r['name']}" for r in rows)
    return f"Получатели: {len(rows)}\n\n{names}"


async def reset_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = linked_students(update.effective_user.id)
    await update.message.reply_text(
        "🧪 Полный тест ПРЕПАДМИНа\n\n"
        + _audience_text(rows)
        + "\n\nСначала этим ученикам уйдёт предупреждение. Данные пока не удаляются.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"📨 Отправить предупреждение ({len(rows)})",
                callback_data="e2e:notify",
            )],
            [InlineKeyboardButton("❌ Отмена", callback_data="e2e:cancel")],
        ]),
    )
    raise ApplicationHandlerStop


async def notify_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message.chat.id != q.from_user.id:
        await q.answer("Недоступно", show_alert=True)
        raise ApplicationHandlerStop
    await q.answer("Отправляю…")
    rows = linked_students(q.from_user.id)
    sent = failed = 0
    for row in rows:
        try:
            await context.bot.send_message(int(row["telegram_user_id"]), NOTICE_TEXT)
            sent += 1
        except Exception:
            failed += 1
    await q.edit_message_text(
        f"📨 Предупреждение отправлено: {sent}\nНе доставлено: {failed}\n\n"
        "Следующий шаг создаст резервную копию и полностью очистит только твои данные ПРЕПАДМИНа.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗄 Создать копию и очистить", callback_data="e2e:reset")],
            [InlineKeyboardButton("⏸ Остановиться", callback_data="e2e:cancel")],
        ]),
    )
    raise ApplicationHandlerStop


async def reset_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message.chat.id != q.from_user.id:
        await q.answer("Недоступно", show_alert=True)
        raise ApplicationHandlerStop
    await q.answer("Создаю резервную копию…")
    uid = int(q.from_user.id)
    backup_path = create_backup(uid)
    deleted = delete_teacher_data(uid)
    context.user_data.clear()
    total = sum(deleted.values())
    await q.edit_message_text(
        "✅ Твои данные ПРЕПАДМИНа очищены.\n\n"
        f"Удалено записей: {total}. Резервная копия сохранена.\n"
        "Нажми /start — и пройдём полную настройку заново."
    )
    print(f"PREPODMIN E2E reset uid={uid} backup={backup_path} deleted={total}", flush=True)
    raise ApplicationHandlerStop


async def cancel_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Отменено")
    await q.edit_message_text("Тестовый сброс отменён. Данные не изменены.")
    raise ApplicationHandlerStop


def install(app):
    app.add_handler(CommandHandler("e2e_test", reset_preview), group=-40)
    app.add_handler(CallbackQueryHandler(notify_students, pattern=r"^e2e:notify$"), group=-40)
    app.add_handler(CallbackQueryHandler(reset_confirmed, pattern=r"^e2e:reset$"), group=-40)
    app.add_handler(CallbackQueryHandler(cancel_reset, pattern=r"^e2e:cancel$"), group=-40)
    print("PREPODMIN safe E2E reset flow ready", flush=True)


def build_app():
    """Compatibility link used by the existing payments → reminders app chain."""
    return reminders.build_app()
