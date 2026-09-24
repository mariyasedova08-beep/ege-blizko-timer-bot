"""Central student-message gateway for PREPODMIN.

Modes:
- auto: send immediately according to existing product rules
- draft: create a draft and ask the teacher to approve it
- manual: store in Outbox; teacher sends explicitly
- off: create/send nothing

All student-facing modules should route outbound messages through dispatch().
"""
import json
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule

MODES = {
    "auto": ("🤖 Автоматически", "Сообщения уходят сразу по действующим правилам."),
    "draft": ("📝 Сначала черновик", "ПРЕПАДМИН готовит текст и ждёт твоего подтверждения."),
    "manual": ("✋ Только вручную", "Сообщения складываются в «Непосланные». Ничего само не всплывает и не уходит."),
    "off": ("🔕 Полностью выключено", "Сообщения ученикам не создаются и не отправляются."),
}

CATEGORY_LABELS = {
    "transfer": "перенос",
    "cancellation": "отмена",
    "homework": "домашнее задание",
    "homework_reminder": "напоминание о ДЗ",
    "lesson_reminder": "напоминание о занятии",
    "other": "сообщение",
}


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_student_message_settings (
                teacher_telegram_user_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'auto',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teacher_student_message_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                recipient_chat_id INTEGER NOT NULL,
                recipient_name TEXT,
                category TEXT NOT NULL DEFAULT 'other',
                text TEXT NOT NULL,
                reply_markup_json TEXT,
                source_key TEXT,
                status TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                discarded_at TEXT,
                last_error TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_student_message_outbox_source
            ON teacher_student_message_outbox(teacher_telegram_user_id, source_key)
            WHERE source_key IS NOT NULL AND source_key<>'';

            CREATE INDEX IF NOT EXISTS idx_student_message_outbox_status
            ON teacher_student_message_outbox(
                teacher_telegram_user_id,status,created_at
            );
            """
        )
        conn.commit()


def ensure_settings(uid):
    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teacher_student_message_settings(
                teacher_telegram_user_id,mode,updated_at
            ) VALUES(?,'auto',?)
            """,
            (int(uid), now),
        )
        conn.commit()


def get_mode(uid):
    ensure_settings(uid)
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT mode FROM teacher_student_message_settings
            WHERE teacher_telegram_user_id=?
            """,
            (int(uid),),
        ).fetchone()
    mode = row["mode"] if row else "auto"
    return mode if mode in MODES else "auto"


def set_mode(uid, mode):
    if mode not in MODES:
        raise ValueError("unsupported student message mode")
    ensure_settings(uid)
    with base.db() as conn:
        conn.execute(
            """
            UPDATE teacher_student_message_settings
            SET mode=?,updated_at=?
            WHERE teacher_telegram_user_id=?
            """,
            (mode, datetime.utcnow().isoformat(), int(uid)),
        )
        conn.commit()


def _markup_json(markup):
    if markup is None:
        return None
    try:
        return json.dumps(markup.to_dict(), ensure_ascii=False)
    except Exception:
        return None


def _markup_from_json(raw, bot):
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return InlineKeyboardMarkup.de_json(data, bot)
    except Exception as exc:
        print(f"Student message markup restore failed: {type(exc).__name__}", flush=True)
        return None


def _row(uid, qid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT * FROM teacher_student_message_outbox
            WHERE id=? AND teacher_telegram_user_id=?
            """,
            (int(qid), int(uid)),
        ).fetchone()


def _existing_by_key(uid, source_key):
    if not source_key:
        return None
    with base.db() as conn:
        return conn.execute(
            """
            SELECT * FROM teacher_student_message_outbox
            WHERE teacher_telegram_user_id=? AND source_key=?
            LIMIT 1
            """,
            (int(uid), str(source_key)),
        ).fetchone()


def _queue(uid, chat_id, recipient_name, category, text, reply_markup, source_key, status, expires_at):
    ensure_tables()
    existing = _existing_by_key(uid, source_key)
    if existing:
        return existing, False
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO teacher_student_message_outbox(
                    teacher_telegram_user_id,recipient_chat_id,recipient_name,
                    category,text,reply_markup_json,source_key,status,expires_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(uid), int(chat_id), str(recipient_name or ""),
                    str(category or "other"), str(text),
                    _markup_json(reply_markup), source_key, status,
                    expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at,
                    now,
                ),
            )
            qid = int(cur.lastrowid)
            conn.commit()
        except Exception:
            existing = _existing_by_key(uid, source_key)
            if existing:
                return existing, False
            raise
    return _row(uid, qid), True


def _expired(row):
    raw = row["expires_at"]
    if not raw:
        return False
    try:
        expiry = datetime.fromisoformat(raw)
        now = datetime.now(expiry.tzinfo) if expiry.tzinfo else datetime.utcnow()
        return now >= expiry
    except Exception:
        return False


def _category_label(value):
    return CATEGORY_LABELS.get(str(value), "сообщение")


def _preview_text(row, manual=False):
    title = "✋ Непосланное сообщение" if manual else "📝 Черновик сообщения ученику"
    text = str(row["text"])
    if len(text) > 2500:
        text = text[:2500] + "\n…"
    return (
        f"{title}\n\n"
        f"Кому: {row['recipient_name'] or 'ученик'}\n"
        f"Тип: {_category_label(row['category'])}\n\n"
        f"{text}"
    )


def _preview_markup(qid, back=False):
    rows = [
        [InlineKeyboardButton("📨 Отправить", callback_data=f"smsg:send:{int(qid)}")],
        [InlineKeyboardButton("🗑 Не отправлять", callback_data=f"smsg:drop:{int(qid)}")],
    ]
    if back:
        rows.append([InlineKeyboardButton("⬅️ К непосланным", callback_data="smsg:outbox")])
    return InlineKeyboardMarkup(rows)


async def dispatch(
    context,
    teacher_id,
    recipient_chat_id,
    text,
    *,
    recipient_name="",
    category="other",
    source_key=None,
    reply_markup=None,
    expires_at=None,
):
    """Send, draft, queue, or suppress one student message.

    Returns one of: sent, failed, draft, manual, off, duplicate, expired.
    """
    uid = int(teacher_id)
    mode = get_mode(uid)
    if mode == "off":
        return "off"

    if mode == "auto":
        try:
            await context.bot.send_message(
                chat_id=int(recipient_chat_id),
                text=str(text),
                reply_markup=reply_markup,
            )
            return "sent"
        except Exception as exc:
            print(
                f"Student message auto-send failed teacher={uid} "
                f"category={category} {type(exc).__name__}",
                flush=True,
            )
            return "failed"

    status = "draft" if mode == "draft" else "manual"
    row, created = _queue(
        uid, recipient_chat_id, recipient_name, category, text,
        reply_markup, source_key, status, expires_at,
    )
    if not created:
        return row["status"] if row["status"] in {"draft", "manual", "sent", "discarded", "expired"} else "duplicate"

    if mode == "draft":
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=_preview_text(row),
                reply_markup=_preview_markup(row["id"]),
            )
        except Exception as exc:
            print(
                f"Student message draft preview failed teacher={uid} "
                f"queue={row['id']} {type(exc).__name__}",
                flush=True,
            )
    return status


def delivery_summary(uid, total, sent=0, failed=0, *, singular=True):
    mode = get_mode(uid)
    total = int(total or 0)
    sent = int(sent or 0)
    failed = int(failed or 0)
    if total == 0:
        return "📨 Telegram ученика не привязан." if singular else "📨 В группе нет привязанных Telegram."
    if mode == "off":
        return "🔕 Сообщения ученикам выключены — ничего не отправлено."
    if mode == "draft":
        return (
            f"📝 Подготовлен черновик: {total}."
            if total == 1 else
            f"📝 Подготовлены черновики: {total}. Отправка только после твоего подтверждения."
        )
    if mode == "manual":
        return (
            "✋ Сообщение добавлено в «Непосланные»."
            if total == 1 else
            f"✋ В «Непосланные» добавлено сообщений: {total}."
        )
    if failed == 0:
        return "📨 Ученик уведомлён." if singular else f"📨 Уведомления отправлены: {sent}."
    return f"⚠️ Уведомления: отправлено {sent}, не доставлено {failed}."


def mode_line(uid):
    mode = get_mode(uid)
    return f"{MODES[mode][0]} — {MODES[mode][1]}"


def _pending_count(uid):
    with base.db() as conn:
        return int(conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM teacher_student_message_outbox
            WHERE teacher_telegram_user_id=? AND status IN ('draft','manual')
            """,
            (int(uid),),
        ).fetchone()["c"] or 0)


def _settings_text(uid):
    mode = get_mode(uid)
    pending = _pending_count(uid)
    return (
        "⚙️ Настройки\n\n"
        "💬 Сообщения ученикам\n"
        f"Сейчас: {MODES[mode][0]}\n"
        f"{MODES[mode][1]}\n\n"
        f"📥 Непосланных сообщений: {pending}\n\n"
        "Режим применяется к переносам, отменам, ДЗ и автоматическим напоминаниям."
    )


def _settings_markup(uid):
    mode = get_mode(uid)
    buttons = []
    for key in ("auto", "draft", "manual", "off"):
        mark = "✅" if key == mode else "▫️"
        buttons.append([
            InlineKeyboardButton(
                f"{mark} {MODES[key][0]}",
                callback_data=f"smsg:mode:{key}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            f"📥 Непосланные ({_pending_count(uid)})",
            callback_data="smsg:outbox",
        )
    ])
    return InlineKeyboardMarkup(buttons)


async def settings_menu(update, context):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    await update.message.reply_text(
        _settings_text(uid),
        reply_markup=_settings_markup(uid),
    )
    raise ApplicationHandlerStop


async def set_mode_callback(update, context):
    q = update.callback_query
    uid = int(q.from_user.id)
    mode = q.data.rsplit(":", 1)[1]
    if mode not in MODES:
        await q.answer("Неизвестный режим", show_alert=True)
        raise ApplicationHandlerStop
    set_mode(uid, mode)
    await q.answer("Режим сохранён")
    await q.edit_message_text(
        _settings_text(uid),
        reply_markup=_settings_markup(uid),
    )
    raise ApplicationHandlerStop


def _pending_rows(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT * FROM teacher_student_message_outbox
            WHERE teacher_telegram_user_id=? AND status IN ('draft','manual')
            ORDER BY id DESC LIMIT 30
            """,
            (int(uid),),
        ).fetchall()


async def outbox(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    rows = _pending_rows(uid)
    if not rows:
        await q.edit_message_text(
            "📥 Непосланные\n\nСейчас здесь пусто.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К настройкам", callback_data="smsg:settings")
            ]]),
        )
        raise ApplicationHandlerStop
    lines = ["📥 Непосланные", "", f"Сообщений: {len(rows)}"]
    buttons = []
    for row in rows:
        label = (
            f"{'📝' if row['status']=='draft' else '✋'} "
            f"{row['recipient_name'] or 'Ученик'} · {_category_label(row['category'])}"
        )
        buttons.append([
            InlineKeyboardButton(label[:60], callback_data=f"smsg:view:{row['id']}")
        ])
    buttons.append([InlineKeyboardButton("⬅️ К настройкам", callback_data="smsg:settings")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


async def settings_callback(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    await q.edit_message_text(_settings_text(uid), reply_markup=_settings_markup(uid))
    raise ApplicationHandlerStop


async def view_message(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    qid = int(q.data.rsplit(":", 1)[1])
    row = _row(uid, qid)
    if not row or row["status"] not in {"draft", "manual"}:
        await q.edit_message_text(
            "Это сообщение уже обработано.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К непосланным", callback_data="smsg:outbox")
            ]]),
        )
        raise ApplicationHandlerStop
    await q.edit_message_text(
        _preview_text(row, manual=row["status"] == "manual"),
        reply_markup=_preview_markup(qid, back=True),
    )
    raise ApplicationHandlerStop


async def send_message(update, context):
    q = update.callback_query
    uid = int(q.from_user.id)
    qid = int(q.data.rsplit(":", 1)[1])
    row = _row(uid, qid)
    if not row or row["status"] not in {"draft", "manual"}:
        await q.answer("Сообщение уже обработано", show_alert=True)
        raise ApplicationHandlerStop
    if _expired(row):
        with base.db() as conn:
            conn.execute(
                "UPDATE teacher_student_message_outbox SET status='expired',last_error='expired before send' WHERE id=?",
                (qid,),
            )
            conn.commit()
        await q.answer("Это сообщение уже потеряло актуальность", show_alert=True)
        await q.edit_message_text(
            "⌛ Сообщение устарело и не было отправлено.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К непосланным", callback_data="smsg:outbox")
            ]]),
        )
        raise ApplicationHandlerStop
    try:
        await context.bot.send_message(
            chat_id=int(row["recipient_chat_id"]),
            text=row["text"],
            reply_markup=_markup_from_json(row["reply_markup_json"], context.bot),
        )
        with base.db() as conn:
            conn.execute(
                """
                UPDATE teacher_student_message_outbox
                SET status='sent',sent_at=?,last_error=NULL
                WHERE id=?
                """,
                (datetime.utcnow().isoformat(), qid),
            )
            conn.commit()
        await q.answer("Отправлено")
        await q.edit_message_text(
            "✅ Сообщение отправлено ученику.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ К непосланным", callback_data="smsg:outbox")
            ]]),
        )
    except Exception as exc:
        with base.db() as conn:
            conn.execute(
                "UPDATE teacher_student_message_outbox SET last_error=? WHERE id=?",
                (f"{type(exc).__name__}: {exc}"[:500], qid),
            )
            conn.commit()
        await q.answer("Не удалось отправить", show_alert=True)
    raise ApplicationHandlerStop


async def drop_message(update, context):
    q = update.callback_query
    uid = int(q.from_user.id)
    qid = int(q.data.rsplit(":", 1)[1])
    row = _row(uid, qid)
    if not row or row["status"] not in {"draft", "manual"}:
        await q.answer("Сообщение уже обработано", show_alert=True)
        raise ApplicationHandlerStop
    with base.db() as conn:
        conn.execute(
            """
            UPDATE teacher_student_message_outbox
            SET status='discarded',discarded_at=?
            WHERE id=?
            """,
            (datetime.utcnow().isoformat(), qid),
        )
        conn.commit()
    await q.answer("Не отправляю")
    await q.edit_message_text(
        "🗑 Сообщение не отправлено.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ К непосланным", callback_data="smsg:outbox")
        ]]),
    )
    raise ApplicationHandlerStop


def install(app):
    ensure_tables()
    app.add_handler(
        MessageHandler(filters.Regex(r"^⚙️ Настройки$"), settings_menu),
        group=-30,
    )
    for pattern, handler in (
        (r"^smsg:settings$", settings_callback),
        (r"^smsg:mode:(?:auto|draft|manual|off)$", set_mode_callback),
        (r"^smsg:outbox$", outbox),
        (r"^smsg:view:\d+$", view_message),
        (r"^smsg:send:\d+$", send_message),
        (r"^smsg:drop:\d+$", drop_message),
    ):
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern), group=-30)
    print(
        "PREPODMIN student messaging ready: auto + draft approval + manual outbox + off",
        flush=True,
    )
    return app
