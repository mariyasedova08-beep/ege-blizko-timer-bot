"""Admin-only, preview-first channel publisher for EGE BLIZKO.

This is intentionally separate from PREPODMIN and from the automatic
hydroxides announcement in public_channel_trainers. Nothing sends on startup.
"""
import html
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

import public_channel_trainers as hub

bot = hub.bot
live7 = hub.live7
live23 = hub.live23
CHANNEL = hub.CHANNEL_USERNAME
BUTTON = "📣 Пост в канал"
_CALLBACK_ROOT = "cab:post:"
_INSTALLED = False
_previous_text_router = None
_previous_cabinet_callback = None
_previous_cabinet_markup = None


def _db():
    return sqlite3.connect(bot.COREAPP_DB_PATH, timeout=15)


def ensure_tables():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ege_channel_post_drafts(
                id TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                trainer_code TEXT NOT NULL,
                body_html TEXT NOT NULL,
                button_url TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft','sending','sent','unknown','cancelled')),
                created_at TEXT NOT NULL,
                message_id INTEGER,
                published_at TEXT
            )
        """)


def _is_admin_private(update):
    return bool(
        update.effective_user
        and update.effective_chat
        and update.effective_chat.type == "private"
        and bot.user_is_admin(update)
    )


def _trainer_rows():
    return [
        (str(code), str(title), str(start_param))
        for code, title, start_param, *_ in hub._catalog_rows(include_hidden=False)
    ]


def _trainer(code):
    return next((x for x in _trainer_rows() if x[0] == code), None)


def _make_post(trainer, username):
    code, title, param = trainer
    safe_title = html.escape(title)
    safe_username = str(username or "").lstrip("@")
    if not safe_username or not all(c.isalnum() or c == "_" for c in safe_username):
        raise ValueError("bot_username_missing")
    if not param or not all(c.isalnum() or c in "_-" for c in param):
        raise ValueError("invalid_trainer_start_parameter")
    url = f"https://t.me/{safe_username}?start={param}"
    if code == "middlesalts":
        body = (
            "💗 <b>ПРИВЕТ! ТРЕНИРУЕМ СВОЙСТВА СРЕДНИХ СОЛЕЙ</b>\n\n"
            "🧂 Новый тренажёр: <b>100 вопросов</b> по реакциям средних солей "
            "с металлами, кислотами, основаниями и другими солями.\n\n"
            "Выбирай 10, 20, 40 или 100 вопросов. "
            "Ошибки сохраняются — можно вернуться и разобрать их отдельно.\n\n"
            "Не угадываем продукты, а разбираемся, когда реакция действительно идёт.\n\n"
            "Чтобы научиться решать задачи — нужно решать задачи! 💗\n\n"
            "<b>ЕГЭ БЛИЗКО</b>"
        )
    else:
        body = (
            "💗 <b>Привет, ребята!</b>\n\n"
            f"🧪 Тренажёр по теме <b>{safe_title}</b> уже доступен в ЕГЭ БЛИЗКО.\n\n"
            "Закрепляем теорию практикой: решаем вопросы, "
            "разбираем ошибки и возвращаемся к сложным заданиям.\n\n"
            "Чтобы научиться решать задачи — нужно решать задачи! 💗"
        )
    return body, url


def _menu_markup(rows):
    buttons = [
        [InlineKeyboardButton(title[:54], callback_data=f"cab:post:new:{code}")]
        for code, title, _ in rows
        if len(code.encode("utf-8")) <= 28
    ]
    buttons.append([InlineKeyboardButton("✖ Закрыть", callback_data="cab:post:close")])
    return InlineKeyboardMarkup(buttons)


def _draft_markup(draft_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опубликовать в канал", callback_data=f"cab:post:send:{draft_id}")],
        [InlineKeyboardButton("🗑 Отменить", callback_data=f"cab:post:cancel:{draft_id}")],
    ])


def create_draft(owner_id, trainer, username):
    ensure_tables()
    body, url = _make_post(trainer, username)
    draft_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute(
            """INSERT INTO ege_channel_post_drafts
               (id,owner_id,trainer_code,body_html,button_url,status,created_at)
               VALUES (?,?,?,?,?,'draft',?)""",
            (draft_id, int(owner_id), trainer[0], body, url, now),
        )
    return draft_id, body, url


def _draft(draft_id, owner_id):
    with _db() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM ege_channel_post_drafts WHERE id=? AND owner_id=?""",
            (str(draft_id), int(owner_id)),
        ).fetchone()
        return dict(row) if row else None


def claim_draft(draft_id, owner_id):
    """Atomic one-time transition. No Telegram call is made inside a DB lock."""
    with _db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT created_at FROM ege_channel_post_drafts WHERE id=? AND owner_id=? AND status='draft'",
            (str(draft_id), int(owner_id)),
        ).fetchone()
        if not row:
            return False
        if datetime.fromisoformat(row[0]) < datetime.now(timezone.utc) - timedelta(hours=48):
            conn.execute(
                "UPDATE ege_channel_post_drafts SET status='cancelled' WHERE id=? AND owner_id=?",
                (str(draft_id), int(owner_id)),
            )
            return False
        result = conn.execute(
            "UPDATE ege_channel_post_drafts SET status='sending' WHERE id=? AND owner_id=? AND status='draft'",
            (str(draft_id), int(owner_id)),
        )
        return result.rowcount == 1


def _finish(draft_id, owner_id, status, message_id=None):
    assert status in {"sent", "unknown", "cancelled"}
    with _db() as conn:
        conn.execute(
            """UPDATE ege_channel_post_drafts
               SET status=?, message_id=?, published_at=?
               WHERE id=? AND owner_id=? AND status='sending'""",
            (
                status, message_id,
                datetime.now(timezone.utc).isoformat() if status == "sent" else None,
                str(draft_id), int(owner_id),
            ),
        )


def _cancel(draft_id, owner_id):
    with _db() as conn:
        changed = conn.execute(
            "UPDATE ege_channel_post_drafts SET status='cancelled' WHERE id=? AND owner_id=? AND status='draft'",
            (str(draft_id), int(owner_id)),
        )
        return changed.rowcount == 1


async def _can_post(context):
    try:
        member = await context.bot.get_chat_member(CHANNEL, context.bot.id)
    except Exception:
        return False
    status = str(getattr(member, "status", "")).lower()
    if status in {"creator", "owner"}:
        return True
    return status == "administrator" and getattr(member, "can_post_messages", None) is True


async def _send_menu(message):
    rows = _trainer_rows()
    if not rows:
        await message.reply_text("В каталоге пока нет открытых тренажёров.")
        return
    await message.reply_text(
        "📣 <b>Готовый пост в канал ЕГЭ БЛИЗКО</b>\n\n"
        "Выбери тренажёр. Я покажу текст и ссылку для проверки. "
        "В канал ничего не уйдёт, пока не нажмёшь «Опубликовать».\n\n"
        "⚠️ Если ты уже публиковала объявление вручную, не отправляй его повторно.",
        parse_mode="HTML",
        reply_markup=_menu_markup(rows),
    )


async def text_router(update, context):
    if (
        _is_admin_private(update) and update.message
        and str(update.message.text or "").strip() == BUTTON
    ):
        await _send_menu(update.message)
        return
    return await _previous_text_router(update, context)


async def cabinet_callback(update, context):
    q = update.callback_query
    data = str(q.data or "") if q else ""
    if not data.startswith(_CALLBACK_ROOT):
        return await _previous_cabinet_callback(update, context)
    if not _is_admin_private(update):
        if q:
            await q.answer("Только владелец бота", show_alert=True)
        return
    await q.answer()
    if data == "cab:post:close":
        await q.edit_message_text("📣 Публикация отменена. Ничего не отправлено.")
        return
    if data == "cab:post:menu":
        await q.edit_message_text(
            "📣 <b>Выбери тренажёр для объявления</b>",
            parse_mode="HTML",
            reply_markup=_menu_markup(_trainer_rows()),
        )
        return
    if data.startswith("cab:post:new:"):
        code = data[len("cab:post:new:"):]
        trainer = _trainer(code)
        if not trainer:
            await q.edit_message_text("Тренажёр не найден или скрыт из каталога.")
            return
        username = str(getattr(context.bot, "username", "") or "")
        try:
            draft_id, body, url = create_draft(update.effective_user.id, trainer, username)
        except ValueError:
            await q.edit_message_text("Не удалось сформировать ссылку на бота. Сообщи разработчику.")
            return
        await q.edit_message_text(
            "👀 <b>ПРЕДПРОСМОТР — ещё не опубликовано</b>\n"
            f"Канал: {html.escape(CHANNEL)}\n\n{body}\n\n"
            f"🔗 {html.escape(url)}\n\n"
            "Опубликовано будет только после подтверждения ниже.",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=_draft_markup(draft_id),
        )
        return
    if data.startswith("cab:post:cancel:"):
        draft_id = data[len("cab:post:cancel:"):]
        if _cancel(draft_id, update.effective_user.id):
            await q.edit_message_text("🗑 Черновик удалён. Пост не отправлен.")
        else:
            await q.edit_message_text("Черновик уже отправлен, отменён или устарел.")
        return
    if data.startswith("cab:post:send:"):
        draft_id = data[len("cab:post:send:"):]
        draft = _draft(draft_id, update.effective_user.id)
        if not draft or draft["status"] != "draft":
            await q.edit_message_text("Этот пост уже обработан или черновик устарел. Повторная отправка заблокирована.")
            return
        if not await _can_post(context):
            await q.edit_message_text(
                "⛔ Бот пока не может публиковать в канале. "
                "Добавь бота администратором @egeblizko_chem и включи право «Публикация сообщений». "
                "После этого создай новый черновик.",
            )
            return
        if not claim_draft(draft_id, update.effective_user.id):
            await q.edit_message_text("Отправка уже началась, пост обработан или черновик устарел.")
            return
        try:
            result = await context.bot.send_message(
                chat_id=CHANNEL,
                text=draft["body_html"],
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🧪 Открыть тренажёр", url=draft["button_url"])
                ]]),
            )
        except Exception as exc:
            # Telegram may have accepted a message before a network timeout.
            # Never retry the same draft automatically: avoid duplicate posts.
            _finish(draft_id, update.effective_user.id, "unknown")
            print(f"EGE_CHANNEL_POST_UNCERTAIN error_type={type(exc).__name__}", flush=True)
            await q.edit_message_text(
                "⚠️ Не удалось подтвердить публикацию. "
                "Проверь канал вручную: Telegram мог принять сообщение. "
                "Не нажимай повторную отправку, пока не проверишь.",
            )
            return
        _finish(draft_id, update.effective_user.id, "sent", int(result.message_id))
        print(f"EGE_CHANNEL_POST_SENT message_id={result.message_id}", flush=True)
        await q.edit_message_text(
            "✅ <b>Опубликовано в канале ЕГЭ БЛИЗКО!</b>\n"
            f"Пост: https://t.me/{CHANNEL.lstrip('@')}/{result.message_id}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return


def _admin_keyboard():
    old = getattr(live23, "ADMIN_KEYBOARD", None)
    rows = [list(row) for row in getattr(old, "keyboard", ())] if old else []
    if not any(BUTTON == str(getattr(b, "text", b)) for row in rows for b in row):
        rows.append([KeyboardButton(BUTTON)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _cabinet_markup():
    old = _previous_cabinet_markup()
    rows = [list(row) for row in old.inline_keyboard]
    if not any(any(str(getattr(b, "callback_data", "")) == "cab:post:menu" for b in row) for row in rows):
        rows.append([InlineKeyboardButton("📣 Пост в канал", callback_data="cab:post:menu")])
    return InlineKeyboardMarkup(rows)


def install():
    global _INSTALLED, _previous_text_router, _previous_cabinet_callback, _previous_cabinet_markup
    if _INSTALLED:
        return
    ensure_tables()
    _previous_text_router = live7.student_text_router
    _previous_cabinet_callback = live23.cabinet_callback
    _previous_cabinet_markup = live23.cabinet_markup
    live7.student_text_router = text_router
    live23.cabinet_callback = cabinet_callback
    live23.cabinet_markup = _cabinet_markup
    live23.ADMIN_KEYBOARD = _admin_keyboard()
    _INSTALLED = True
    print("EGE_CHANNEL_POSTS_READY preview_only=1 requires_admin_confirmation=1", flush=True)
