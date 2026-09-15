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

TASK_KINDS = {
    "work": ("📋 Работа", "работу"),
    "content": ("💡 Контент", "идею контента"),
    "tech": ("🛠 Техническое", "техническую задачу"),
}

MONTHS = {
    "января": 1, "янв": 1,
    "февраля": 2, "фев": 2,
    "марта": 3, "мар": 3,
    "апреля": 4, "апр": 4,
    "мая": 5, "май": 5,
    "июня": 6, "июн": 6,
    "июля": 7, "июл": 7,
    "августа": 8, "авг": 8,
    "сентября": 9, "сент": 9, "сен": 9,
    "октября": 10, "окт": 10,
    "ноября": 11, "ноя": 11,
    "декабря": 12, "дек": 12,
}

CATEGORY_PREFIX_RE = re.compile(
    r"^\s*(контент|идея|работа|рабочее|рабочая|тех|техническое|техническая)\s*(?:[-—:]\s*|\s+)",
    re.I,
)


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
        columns = {row[1] for row in conn.execute("PRAGMA table_info(teacher_tasks)").fetchall()}
        if "task_kind" not in columns:
            conn.execute("ALTER TABLE teacher_tasks ADD COLUMN task_kind TEXT NOT NULL DEFAULT 'work'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_teacher_tasks_kind ON teacher_tasks(teacher_telegram_user_id, completed, task_kind)"
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

    month_pattern = "|".join(sorted((re.escape(x) for x in MONTHS), key=len, reverse=True))
    m = re.search(rf"(?<!\d)(\d{{1,2}})\s+({month_pattern})(?:\s+(\d{{4}}))?", low, re.I)
    if m:
        day = int(m.group(1))
        month = MONTHS[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else base_date.year
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
    m = re.search(r"\b(?:в\s+)?([01]?\d|2[0-3])[:.]([0-5]\d)\b", low)
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    m = re.search(r"\bв\s+([0-2]?\d)(?:\s*(?:час(?:а|ов)?))?(?:\s+(утра|вечера|дня|ночи))?\b", low)
    if m:
        h = int(m.group(1))
        part = m.group(2)
        if 0 <= h <= 23:
            if part in {"вечера", "дня"} and h < 12:
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
    out = text.strip(" ,.;:-—")
    out = re.sub(r"\b(?:сегодня|завтра|послезавтра)\b", "", out, flags=re.I)
    out = re.sub(r"(?<!\d)\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?(?!\d)", "", out)
    month_pattern = "|".join(sorted((re.escape(x) for x in MONTHS), key=len, reverse=True))
    out = re.sub(rf"(?<!\d)\d{{1,2}}\s+(?:{month_pattern})(?:\s+\d{{4}})?", "", out, flags=re.I)
    out = re.sub(r"\bв\s+(?:[01]?\d|2[0-3])[:.]([0-5]\d)\b", "", out, flags=re.I)
    out = re.sub(r"\bв\s+[0-2]?\d(?:\s*(?:час(?:а|ов)?))?(?:\s+(?:утра|вечера|дня|ночи))?\b", "", out, flags=re.I)
    out = re.sub(r"\b(?:утром|днём|днем|вечером)\b", "", out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip(" ,.;:-—")
    if out.lower().startswith("и "):
        out = out[2:].strip()
    return out[:500] or "Задача"


def _kind_from_word(word):
    low = word.lower()
    if low in {"контент", "идея"}:
        return "content"
    if low.startswith("тех"):
        return "tech"
    return "work"


def _detect_kind_and_text(text, forced_kind=None):
    raw = str(text or "").strip()
    match = CATEGORY_PREFIX_RE.match(raw)
    detected = _kind_from_word(match.group(1)) if match else None
    cleaned = raw[match.end():].strip() if match else raw

    kind = forced_kind if forced_kind in TASK_KINDS else detected
    if kind not in TASK_KINDS:
        first = cleaned.lower().split(maxsplit=1)[0] if cleaned else ""
        if first in {"рилс", "reels", "пост", "сторис", "stories"}:
            kind = "content"
        else:
            kind = "work"
    return kind, cleaned or raw


def parse_tasks(uid, text, allow_no_date=False):
    base_date = _now(uid).date()
    normalized = re.sub(r"\s+", " ", text.strip())
    parts = re.split(
        r"\s*(?:;|\n)\s*|\s+и\s+(?=(?:сегодня|завтра|послезавтра|утром|дн[её]м|вечером|в\s+\d))",
        normalized,
        flags=re.I,
    )
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return []

    result = []
    global_date = _parse_explicit_date(normalized, base_date)
    inherited_date = global_date
    for part in parts:
        explicit_date = _parse_explicit_date(part, base_date)
        if explicit_date:
            inherited_date = explicit_date
        due_date = explicit_date or inherited_date
        if due_date is None and not allow_no_date:
            due_date = base_date
        due_time = _parse_time(part)
        title = _clean_title(part)
        result.append({"title": title, "due_date": due_date, "due_time": due_time})
    return result


def save_tasks(uid, parsed, source_type, source_text, task_kind="work"):
    now = datetime.utcnow().isoformat()
    ids = []
    with base.db() as conn:
        for task in parsed:
            due_date = task["due_date"].isoformat() if task.get("due_date") else ""
            cur = conn.execute(
                """
                INSERT INTO teacher_tasks(
                    teacher_telegram_user_id,title,due_date,due_time,
                    source_type,source_text,created_at,task_kind
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    int(uid), task["title"], due_date, task["due_time"],
                    source_type, source_text, now, task_kind,
                ),
            )
            ids.append(cur.lastrowid)
        conn.commit()
    return ids


def _fmt_task(task):
    if task.get("due_date"):
        when = task["due_date"].strftime("%d.%m")
        if task.get("due_time"):
            when += f" {task['due_time']}"
    else:
        when = "без даты"
    return f"• {when} — {task['title']}"


async def _save_from_text(update, context, text, source_type="text", forced_kind=None, allow_no_date=True):
    uid = update.effective_user.id
    task_kind, cleaned_text = _detect_kind_and_text(text, forced_kind)
    parsed = parse_tasks(uid, cleaned_text, allow_no_date=allow_no_date)
    if not parsed:
        await update.effective_message.reply_text("Не смогла выделить задачу. Напиши её ещё раз.")
        return []
    save_tasks(uid, parsed, source_type, text, task_kind=task_kind)
    label = TASK_KINDS[task_kind][0]
    lines = [f"✅ Добавила в {label}:"] + [_fmt_task(t) for t in parsed]
    await update.effective_message.reply_text("\n".join(lines), reply_markup=base.MAIN_KB)
    return parsed


def _category_counts(uid):
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT task_kind, COUNT(*) AS c
            FROM teacher_tasks
            WHERE teacher_telegram_user_id=? AND completed=0
            GROUP BY task_kind
            """,
            (int(uid),),
        ).fetchall()
    result = {k: 0 for k in TASK_KINDS}
    for row in rows:
        kind = row["task_kind"] if row["task_kind"] in TASK_KINDS else "work"
        result[kind] += int(row["c"] or 0)
    return result


async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    uid = update.effective_user.id
    today_date = _now(uid).date()
    counts = _category_counts(uid)
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
        f"📍 Сегодня: {today_count}\n"
        f"📅 С датой впереди: {upcoming_count}\n\n"
        f"📋 Работа: {counts['work']}\n"
        f"💡 Контент: {counts['content']}\n"
        f"🛠 Технические: {counts['tech']}\n\n"
        "Быстрее всего — кнопка «➕ Быстрая задача» внизу."
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Работа", callback_data="task:kind:work"),
            InlineKeyboardButton("💡 Контент", callback_data="task:kind:content"),
        ],
        [InlineKeyboardButton("🛠 Технические", callback_data="task:kind:tech")],
        [
            InlineKeyboardButton("📍 Сегодня", callback_data="task:today"),
            InlineKeyboardButton("📅 Ближайшие", callback_data="task:upcoming"),
        ],
        [InlineKeyboardButton("✅ Отметить выполненной", callback_data="task:done")],
    ])
    await update.message.reply_text(text, reply_markup=kb)


async def quick_task_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["prepodmin_task_kind"] = "auto"
    await update.message.reply_text(
        "➕ Напиши задачу одним сообщением.\n\n"
        "Можно так:\n"
        "• контент — снять рилс про бота\n"
        "• работа — проверить домашки завтра в 18:00\n"
        "• тех — проверить уведомления 20 сентября\n\n"
        "Если дату не напишешь — задача сохранится без даты."
    )
    return ADD_TASK_TEXT


async def add_text_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = str(q.data or "")
    forced_kind = data.rsplit(":", 1)[1] if data.startswith("task:add:") else "auto"
    context.user_data["prepodmin_task_kind"] = forced_kind
    if forced_kind in TASK_KINDS:
        label = TASK_KINDS[forced_kind][1]
        prompt = f"Напиши {label} одним сообщением. Если нужна дата или время — укажи их прямо в тексте."
    else:
        prompt = "Напиши задачу обычной фразой. Можно начать с «контент —», «работа —» или «тех —»."
    await q.edit_message_text(prompt)
    return ADD_TASK_TEXT


async def add_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    forced = context.user_data.pop("prepodmin_task_kind", "auto")
    await _save_from_text(
        update,
        context,
        update.message.text,
        "text",
        forced_kind=None if forced == "auto" else forced,
        allow_no_date=True,
    )
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
        if mode == "upcoming":
            return conn.execute(
                """
                SELECT * FROM teacher_tasks
                WHERE teacher_telegram_user_id=? AND completed=0 AND due_date>=?
                ORDER BY due_date,CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,due_time,id
                LIMIT 40
                """,
                (int(uid), today_date.isoformat()),
            ).fetchall()
        if mode in TASK_KINDS:
            return conn.execute(
                """
                SELECT * FROM teacher_tasks
                WHERE teacher_telegram_user_id=? AND completed=0 AND task_kind=?
                ORDER BY CASE WHEN due_date='' THEN 1 ELSE 0 END,due_date,
                         CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,due_time,id
                LIMIT 60
                """,
                (int(uid), mode),
            ).fetchall()
        return conn.execute(
            """
            SELECT * FROM teacher_tasks
            WHERE teacher_telegram_user_id=? AND completed=0
            ORDER BY CASE WHEN due_date='' THEN 1 ELSE 0 END,due_date,
                     CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,due_time,id
            LIMIT 60
            """,
            (int(uid),),
        ).fetchall()


def _row_when(row):
    if row["due_date"]:
        try:
            value = date.fromisoformat(row["due_date"]).strftime("%d.%m")
        except Exception:
            value = row["due_date"]
        if row["due_time"]:
            value += f" {row['due_time']}"
        return value
    return "без даты"


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = str(q.data or "")
    if data.startswith("task:kind:"):
        mode = data.rsplit(":", 1)[1]
        title = TASK_KINDS.get(mode, ("✅ Задачи", ""))[0]
    else:
        mode = "today" if data == "task:today" else "upcoming"
        title = "📍 Задачи на сегодня" if mode == "today" else "📅 Ближайшие задачи"
    rows = _task_rows(q.from_user.id, mode)
    lines = [title]
    if not rows:
        lines.append("\nПока здесь пусто 🎉")
    else:
        lines.append("")
        for r in rows:
            lines.append(f"• {_row_when(r)} — {r['title']}")

    markup = None
    if mode in TASK_KINDS:
        verb = TASK_KINDS[mode][1]
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ Добавить {verb}", callback_data=f"task:add:{mode}")]
        ])
    await q.edit_message_text("\n".join(lines), reply_markup=markup)


async def done_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = _task_rows(q.from_user.id, "all")
    if not rows:
        await q.edit_message_text("Нечего отмечать — активных задач нет.")
        return
    kb = []
    for r in rows[:30]:
        prefix = TASK_KINDS.get(r["task_kind"], TASK_KINDS["work"])[0].split()[0]
        kb.append([
            InlineKeyboardButton(
                f"✅ {prefix} {_row_when(r)} • {r['title'][:40]}",
                callback_data=f"task:done:{r['id']}",
            )
        ])
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
            "Пока используй «➕ Быстрая задача»."
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
    await _save_from_text(update, context, text, "voice", allow_no_date=True)


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
            ["➕ Быстрая задача"],
            ["📍 Сегодня", "✅ Задачи"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )
    app.add_handler(MessageHandler(filters.Regex(r"^✅ Задачи$"), tasks_menu), group=-4)
    app.add_handler(ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^➕ Быстрая задача$"), quick_task_begin),
            CallbackQueryHandler(add_text_begin, pattern=r"^task:add(?::(?:work|content|tech))?$"),
        ],
        states={ADD_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_text_save)]},
        fallbacks=[],
        per_message=False,
    ), group=-5)
    app.add_handler(CallbackQueryHandler(list_tasks, pattern=r"^task:(?:today|upcoming|kind:(?:work|content|tech))$"), group=-4)
    app.add_handler(CallbackQueryHandler(done_picker, pattern=r"^task:done$"), group=-4)
    app.add_handler(CallbackQueryHandler(done_apply, pattern=r"^task:done:\d+$"), group=-4)
    app.add_handler(MessageHandler(filters.VOICE, voice_task), group=-6)
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_task_reminders, interval=60, first=15, name="teacher_task_reminders")
    return app
