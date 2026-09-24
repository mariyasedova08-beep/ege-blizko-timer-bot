"""Pilot feedback channel for PREPODMIN testers."""
import os
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import teacher_product_mvp as base


DEVELOPER_CHAT_ID = os.getenv("TEACHER_PRODUCT_DEVELOPER_CHAT_ID", "").strip()
BUTTON = "💬 Разработчикам"
_PENDING_KEY = "prepodmin_feedback_kind"
_INSTALLED = False

KINDS = {
    "bug": ("🐞 Проблема", "проблему"),
    "idea": ("💡 Идея", "идею"),
}


def ensure_tables():
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_product_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                teacher_name TEXT,
                teacher_subject TEXT,
                telegram_username TEXT,
                feedback_kind TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_teacher_product_feedback_status
            ON teacher_product_feedback(status, created_at)
            """
        )
        conn.commit()


def _with_feedback_button():
    current = getattr(base, "MAIN_KB", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []

    cleaned = []
    for row in rows:
        new_row = [
            button for button in row
            if getattr(button, "text", button) != BUTTON
        ]
        if new_row:
            cleaned.append(new_row)

    cleaned.append([KeyboardButton(BUTTON)])
    return ReplyKeyboardMarkup(
        cleaned,
        resize_keyboard=True,
        is_persistent=True,
    )


async def open_feedback(update, context):
    uid = int(update.effective_user.id)
    teacher = base.teacher(uid)
    if not teacher or not teacher["onboarding_completed_at"]:
        return

    context.user_data.pop(_PENDING_KEY, None)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🐞 Сообщить о проблеме", callback_data="feedback:bug")],
        [InlineKeyboardButton("💡 Предложить идею", callback_data="feedback:idea")],
        [InlineKeyboardButton("✖️ Отмена", callback_data="feedback:cancel")],
    ])
    await update.message.reply_text(
        "💬 <b>Связь с разработчиками</b>\n\n"
        "Что хочешь отправить?",
        parse_mode="HTML",
        reply_markup=kb,
    )
    raise ApplicationHandlerStop


async def choose_feedback(update, context):
    q = update.callback_query
    uid = int(q.from_user.id)
    teacher = base.teacher(uid)
    if not teacher or not teacher["onboarding_completed_at"]:
        await q.answer()
        return

    data = str(q.data or "")
    if data == "feedback:cancel":
        context.user_data.pop(_PENDING_KEY, None)
        await q.answer("Отменено")
        await q.edit_message_text("Отправка отменена.")
        raise ApplicationHandlerStop

    kind = data.rsplit(":", 1)[1] if ":" in data else ""
    if kind not in KINDS:
        await q.answer()
        return

    context.user_data[_PENDING_KEY] = kind
    label, noun = KINDS[kind]
    await q.answer()
    if kind == "bug":
        prompt = (
            f"{label}\n\n"
            "Опиши, что не работает: что ты нажал(а), что произошло и как, по твоему мнению, должно было работать.\n\n"
            "Отправь одним сообщением."
        )
    else:
        prompt = (
            f"{label}\n\n"
            "Опиши, что хотелось бы добавить или изменить в ПРЕПАДМИН.\n\n"
            "Отправь одним сообщением."
        )
    await q.edit_message_text(prompt)
    raise ApplicationHandlerStop


async def feedback_text_router(update, context):
    kind = context.user_data.get(_PENDING_KEY)
    if kind not in KINDS:
        return

    uid = int(update.effective_user.id)
    teacher = base.teacher(uid)
    if not teacher or not teacher["onboarding_completed_at"]:
        context.user_data.pop(_PENDING_KEY, None)
        return

    message = str(update.message.text or "").strip()
    if not message:
        return

    now = datetime.utcnow().isoformat()
    username = str(update.effective_user.username or "").strip()

    with base.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO teacher_product_feedback(
                teacher_telegram_user_id,teacher_name,teacher_subject,
                telegram_username,feedback_kind,message,status,created_at
            ) VALUES(?,?,?,?,?,?,'new',?)
            """,
            (
                uid,
                teacher["name"] or "",
                teacher["subject"] or "",
                username,
                kind,
                message,
                now,
            ),
        )
        feedback_id = int(cur.lastrowid)
        conn.commit()

    context.user_data.pop(_PENDING_KEY, None)

    label, _noun = KINDS[kind]
    await update.message.reply_text(
        f"✅ Отправлено разработчикам.\n\n"
        f"{label} • обращение #{feedback_id}\n"
        "Спасибо — это поможет улучшить ПРЕПАДМИН.",
        reply_markup=base.MAIN_KB,
    )

    if DEVELOPER_CHAT_ID:
        try:
            teacher_line = teacher["name"] or "Преподаватель"
            if teacher["subject"]:
                teacher_line += f" · {teacher['subject']}"
            username_line = f"@{username}" if username else "username не указан"

            await context.bot.send_message(
                chat_id=int(DEVELOPER_CHAT_ID),
                text=(
                    f"📨 <b>Новый отзыв ПРЕПАДМИН #{feedback_id}</b>\n\n"
                    f"{label}\n"
                    f"От: {teacher_line}\n"
                    f"Telegram: {username_line}\n\n"
                    f"{message}"
                ),
                parse_mode="HTML",
            )
            print(
                f"PREPODMIN feedback forwarded id={feedback_id} kind={kind}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"PREPODMIN feedback forward failed id={feedback_id} error={type(exc).__name__}: {exc}",
                flush=True,
            )
    else:
        print(
            f"PREPODMIN feedback saved id={feedback_id} kind={kind}; developer chat is not configured",
            flush=True,
        )

    raise ApplicationHandlerStop


async def _push_feedback_button(context):
    migration_key = "tester-feedback-button-v1"
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_feedback_migrations(
                teacher_telegram_user_id INTEGER NOT NULL,
                migration_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id,migration_key)
            )
            """
        )
        teachers = conn.execute(
            """
            SELECT telegram_user_id
            FROM teachers
            WHERE onboarding_completed_at IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
        sent_ids = {
            int(row[0]) for row in conn.execute(
                """
                SELECT teacher_telegram_user_id
                FROM teacher_feedback_migrations
                WHERE migration_key=?
                """,
                (migration_key,),
            ).fetchall()
        }

    sent = skipped = failed = 0
    for row in teachers:
        uid = int(row["telegram_user_id"])
        if uid in sent_ids:
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "💬 Добавила связь с разработчиками.\n\n"
                    "Если во время теста что-то не работает или появится идея — "
                    "нажми «💬 Разработчикам» в меню."
                ),
                reply_markup=base.MAIN_KB,
            )
            with base.db() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO teacher_feedback_migrations(
                        teacher_telegram_user_id,migration_key,sent_at
                    ) VALUES(?,?,?)
                    """,
                    (uid, migration_key, datetime.utcnow().isoformat()),
                )
                conn.commit()
            sent += 1
        except Exception as exc:
            failed += 1
            print(
                f"PREPODMIN feedback keyboard push failed uid={uid} error={type(exc).__name__}",
                flush=True,
            )

    print(
        f"PREPODMIN feedback keyboard push: sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    ensure_tables()
    base.MAIN_KB = _with_feedback_button()

    app.add_handler(
        MessageHandler(filters.Regex(r"^💬 Разработчикам$"), open_feedback),
        group=-92,
    )
    app.add_handler(
        CallbackQueryHandler(choose_feedback, pattern=r"^feedback:(?:bug|idea|cancel)$"),
        group=-92,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_text_router),
        group=-91,
    )

    if app.job_queue is not None:
        app.job_queue.run_once(
            _push_feedback_button,
            when=3,
            name="prepodmin_feedback_keyboard_push_v1",
        )

    print(
        "PREPODMIN pilot feedback ready: bug + idea + developer forwarding",
        flush=True,
    )
