import os
import re
from datetime import date, datetime, timedelta

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_today as today

ADD_TASK_TEXT = 90
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                due_time TEXT,
                source_type TEXT NOT NULL DEFAULT 'text',
                source_text TEXT,
                completed INTEGER NOT NULL DEFAULT 0,
                reminded_at TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_tasks_due
            ON teacher_tasks(teacher_telegram_user_id, completed, due_date, due_time);
            """
        )
        conn.commit()


def _now(uid):
    return datetime.now(schedule.tz(uid))


def _parse_explicit_date(text, base_date):
    low = text.lower()
    if "послезавтра" in low:
        return base_date + timedelta(days=2)
    if "завтра" in low:
        return base_date + timedelta(days=1)
    if "сегодня" in low:
        return base_date
    m = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)", text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else base_date.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            if not m.group(3) and d < base_date - timedelta(days=30):
                d = date(year + 1, month, day)
            return d
        except ValueError:
            pass
    return None


def _parse_time(text):
    low = text.lower()
    # 18:30 / 18.30
    m = re.search(r"\b(?:в\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)\b", low)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    # в 9 / в 9 утра / в 7 вечера
    m = re.search(r"\bв\s+([0-2]?\d)(?:\s*(?:час(?:а|ов)?))?(?:\s+(утра|вечера|дня|ночи))?\b", low)
    if m:
        h = int(m.group(1))
        part = m.group(2)
        if 0 <= h <= 23:
            if part == "вечера" and h < 12:
                h += 12
            elif part == "дня" and h < 12:
                h += 12
            elif part == "ночи" and h == 12:
                h = 0
            return f"{h:02d}:00"
    if "утром" in low:
        return "09:00"
    if "днём" in low or "днем" in low:
        return "15:00"
    if "вечером" in low:
        return "19:00"
    return None


def _clean_title(text):
    out = text.strip(" ,.;:-")
    out = re.sub(r"\b(?:сегодня|завтра|послезавтра)\b", "", out, flags=re.I)
    out = re.sub(r"(?<!\d)\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?(?!\d)", "", out)
    out = re.sub(r"\bв\s+(?:[01]?\d|2[0-3])[:.]([0-5]\d)\b", "", out, flags=re.I)
    out = re.sub(r"\bв\s+[0-2]?\d(?:\s*(?:час(?:а|ов)?))?(?:\s+(?:утра|вечера|дня|ночи))?\b", "", out, flags=re.I)
    out = re.sub(r"\b(?:утром|днём|днем|вечером)\b", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" ,.;:-")
    if out.lower().startswith("и "):
        out = out[2:].strip()
    return out[:500] or "Задача"


def parse_tasks(uid, text):
    base_date = _now(uid).date()
    normalized = re.sub(r"\s+", " ", text.strip())
    # Split only when the second part clearly begins with its own scheduling cue.
    parts = re.split(
        r"\s*(?:;|\n)\s*|\s+и\s+(?=(?:сегодня|завтра|послезавтра|утром|дн[её]м|вечером|в\s+\d))",
        normalized,
        flags=re.I,
    )
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []

    result = []
    inherited_date = _parse_explicit_date(normalized, base_date) or base_date
    for part in parts:
        explicit_date = _parse_explicit_date(part, base_date)
        due_date = explicit_date or inherited_date
        if explicit_date:
            inherited_date = explicit_date
        due_time = _parse_time(part)
        title = _clean_title(part)
        result.append({"title": title, "due_date": due_date, "due_time": due_time})
    return result


def save_tasks(uid, parsed, source_type, source_text):
    now = datetime.utcnow().isoformat()
    ids = []
    with base.db() as conn:
        for task in parsed:
            cur = conn.execute(
                """
                INSERT INTO teacher_tasks(
                    teacher_telegram_user_id,title,due_date,due_time,
                    source_type,source_text,created_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    int(uid), task["title"], task["due_date"].isoformat(), task["due_time"],
                    source_type, source_text, now,
                ),
            )
            ids.append(cur.lastrowid)
        conn.commit()
    return ids


def _fmt_task(task):
    when = task["due_date"].strftime("%d.%m")
    if task.get("due_time"):
        when += f" {task['due_time']}"
    return f"• {when} — {task['title']}"


async def _save_from_text(update, context, text, source_type="text"):
    uid = update.effective_user.id
    parsed = parse_tasks(uid, text)
    if not parsed:
        await update.effective_message.reply_text("Не смогла выделить задачу. Скажи или напиши её ещё раз.")
        return []
    save_tasks(uid, parsed, source_type, text)
    lines = ["✅ Добавила в задачи:"] + [_fmt_task(t) for t in parsed]
    await update.effective_message.reply_text("\n".join(lines), reply_markup=base.MAIN_KB)
    return parsed


async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    uid = update.effective_user.id
    today_date = _now(uid).date()
    with base.db() as conn:
        today_count = conn.execute(
            "SELECT COUNT(*) AS c FROM teacher_tasks WHERE teacher_telegram_user_id=? AND completed=0 AND due_date=?",
            (int(uid), today_date.isoformat()),
        ).fetchone()["c"]
        upcoming_count = conn.execute(
            "SELECT COUNT(*) AS c FROM teacher_tasks WHERE teacher_telegram_user_id=? AND completed=0 AND due_date>=?",
            (int(uid), today_date.isoformat()),
        ).fetchone()["c"]
    text = (
        "✅ Задачи\n\n"
        f"Сегодня: {today_count}\n"
        f"Всего предстоящих: {upcoming_count}\n\n"
        "Можно добавить задачу текстом или просто отправить голосовое прямо в чат."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить текстом", callback_data="task:add")],
        [InlineKeyboardButton("📍 Задачи на сегодня", callback_data="task:today")],
        [InlineKeyboardButton("📅 Ближайшие задачи", callback_data="task:upcoming")],
        [InlineKeyboardButton("✅ Отметить выполненной", callback_data="task:done")],
    ])
    await update.message.reply_text(text, reply_markup=kb)


async def add_text_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "Напиши задачу обычной фразой.\n\n"
        "Например: «завтра в 9 проверить домашки у группы ЕГЭ»."
    )
    return ADD_TASK_TEXT


async def add_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_from_text(update, context, update.message.text, "text")
    return ConversationHandler.END


def _task_rows(uid, mode="today"):
    today_date = _now(uid).date()
    with base.db() as conn:
        if mode == "today":
            return conn.execute(
                """
                SELECT * FROM teacher_tasks
                WHERE teacher_telegram_user_id=? AND completed=0 AND due_date=?
                ORDER BY CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,due_time,id
                """,
                (int(uid), today_date.isoformat()),
            ).fetchall()
        return conn.execute(
            """
            SELECT * FROM teacher_tasks
            WHERE teacher_telegram_user_id=? AND completed=0 AND due_date>=?
            ORDER BY due_date,CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,due_time,id
            LIMIT 40
            """,
            (int(uid), today_date.isoformat()),
        ).fetchall()


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mode = "today" if q.data == "task:today" else "upcoming"
    rows = _task_rows(q.from_user.id, mode)
    if not rows:
        await q.edit_message_text("На сегодня задач нет 🎉" if mode == "today" else "Предстоящих задач нет.")
        return
    lines = ["📍 Задачи на сегодня" if mode == "today" else "📅 Ближайшие задачи"]
    for r in rows:
        d = date.fromisoformat(r["due_date"])
        when = d.strftime("%d.%m") + (f" {r['due_time']}" if r["due_time"] else "")
        lines.append(f"• {when} — {r['title']}")
    await q.edit_message_text("\n".join(lines))


async def done_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = _task_rows(q.from_user.id, "upcoming")
    if not rows:
        await q.edit_message_text("Нечего отмечать — активных задач нет.")
        return
    kb = []
    for r in rows[:30]:
        d = date.fromisoformat(r["due_date"]).strftime("%d.%m")
        t = f" {r['due_time']}" if r["due_time"] else ""
        kb.append([InlineKeyboardButton(f"✅ {d}{t} • {r['title'][:45]}", callback_data=f"task:done:{r['id']}")])
    await q.edit_message_text("Что выполнено?", reply_markup=InlineKeyboardMarkup(kb))


async def done_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task_id = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        row = conn.execute(
            "SELECT title FROM teacher_tasks WHERE id=? AND teacher_telegram_user_id=? AND completed=0",
            (task_id, int(q.from_user.id)),
        ).fetchone()
        if not row:
            await q.edit_message_text("Задача уже выполнена или не найдена.")
            return
        conn.execute(
            "UPDATE teacher_tasks SET completed=1,completed_at=? WHERE id=? AND teacher_telegram_user_id=?",
            (datetime.utcnow().isoformat(), task_id, int(q.from_user.id)),
        )
        conn.commit()
    await q.edit_message_text(f"✅ Выполнено: {row['title']}")


async def _transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OPENAI_API_KEY:
        return None
    tg_file = await context.bot.get_file(update.message.voice.file_id)
    audio = await tg_file.download_as_bytearray()
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    files = {"file": ("voice.ogg", bytes(audio), "audio/ogg")}
    data = {"model": "gpt-4o-mini-transcribe", "language": "ru"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
        )
        response.raise_for_status()
        payload = response.json()
        return (payload.get("text") or "").strip()


async def voice_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    if not OPENAI_API_KEY:
        await update.message.reply_text(
            "🎙 Голосовые задачи уже предусмотрены, но распознавание речи ещё не подключено к ПРЕПОДМИН.\n\n"
            "Пока можешь открыть «✅ Задачи» → «➕ Добавить текстом»."
        )
        return
    try:
        text = await _transcribe_voice(update, context)
    except Exception as exc:
        print(f"Voice transcription failed: {type(exc).__name__}: {exc}", flush=True)
        await update.message.reply_text("Не получилось распознать голосовое. Попробуй ещё раз или добавь задачу текстом.")
        return
    if not text:
        await update.message.reply_text("Не удалось разобрать голосовое. Попробуй записать ещё раз.")
        return
    await update.message.reply_text(f"🎙 Я услышала:\n{text}")
    await _save_from_text(update, context, text, "voice")


async def check_task_reminders(context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    with base.db() as conn:
        teachers = conn.execute(
            "SELECT telegram_user_id,timezone FROM teachers WHERE onboarding_completed_at IS NOT NULL"
        ).fetchall()
    for teacher in teachers:
        uid = int(teacher["telegram_user_id"])
        now = _now(uid)
        with base.db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM teacher_tasks
                WHERE teacher_telegram_user_id=? AND completed=0
                  AND reminded_at IS NULL AND due_date=? AND due_time IS NOT NULL
                """,
                (uid, now.date().isoformat()),
            ).fetchall()
        for row in rows:
            h, m = map(int, row["due_time"].split(":"))
            due_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            seconds = (now - due_dt).total_seconds()
            if 0 <= seconds < 150:
                try:
                    await context.bot.send_message(uid, f"🔔 Задача на сейчас:\n\n{row['title']}")
                    with base.db() as conn:
                        conn.execute(
                            "UPDATE teacher_tasks SET reminded_at=? WHERE id=? AND teacher_telegram_user_id=?",
                            (datetime.utcnow().isoformat(), int(row["id"]), uid),
                        )
                        conn.commit()
                except Exception as exc:
                    print(f"Task reminder failed uid={uid}: {type(exc).__name__}: {exc}", flush=True)


def build_app():
    ensure_tables()
    app = today.build_app()
    base.MAIN_KB = ReplyKeyboardMarkup(
        [
            ["📍 Сегодня", "✅ Задачи"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )
    app.add_handler(MessageHandler(filters.Regex(r"^✅ Задачи$"), tasks_menu), group=-3)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_text_begin, pattern=r"^task:add$")],
        states={ADD_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_text_save)]},
        fallbacks=[], per_message=False,
    ), group=-3)
    app.add_handler(CallbackQueryHandler(list_tasks, pattern=r"^task:(?:today|upcoming)$"), group=-3)
    app.add_handler(CallbackQueryHandler(done_picker, pattern=r"^task:done$"), group=-3)
    app.add_handler(CallbackQueryHandler(done_apply, pattern=r"^task:done:\d+$"), group=-3)
    app.add_handler(MessageHandler(filters.VOICE, voice_task), group=-4)
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_task_reminders, interval=60, first=15, name="teacher_task_reminders")
    return app
