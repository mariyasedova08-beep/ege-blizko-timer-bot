"""Availability slots for PREPODMIN.

A teacher defines weekly work windows and a default lesson/slot duration once.
For any day the bot overlays existing individual/group lessons (including moves)
and one-off manual blocks, then derives free slots automatically.
"""
import re
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_today as today

SET_WEEK, BLOCK_RANGE = range(510, 512)

DAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
DAY_NAMES_FULL = (
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"
)
DAY_ALIASES = {
    "пн": 0, "понедельник": 0,
    "вт": 1, "вторник": 1,
    "ср": 2, "среда": 2,
    "чт": 3, "четверг": 3,
    "пт": 4, "пятница": 4,
    "сб": 5, "суббота": 5,
    "вс": 6, "воскресенье": 6,
}


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_slot_settings (
                teacher_telegram_user_id INTEGER PRIMARY KEY,
                slot_minutes INTEGER NOT NULL DEFAULT 60,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teacher_work_windows (
                teacher_telegram_user_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                start_time TEXT,
                end_time TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id, weekday)
            );
            CREATE TABLE IF NOT EXISTS teacher_slot_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                block_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'личное',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_slot_blocks_day
            ON teacher_slot_blocks(teacher_telegram_user_id, block_date, start_time);
            """
        )
        conn.commit()


def _main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["➕ Быстрая задача"],
            ["📍 Сегодня", "🌅 Завтра"],
            ["🗓 Мои слоты", "✅ Задачи"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )


def _settings(uid):
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            "SELECT slot_minutes FROM teacher_slot_settings WHERE teacher_telegram_user_id=?",
            (int(uid),),
        ).fetchone()
    return int(row["slot_minutes"]) if row else 60


def _windows(uid):
    ensure_tables()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT weekday,start_time,end_time,active
            FROM teacher_work_windows
            WHERE teacher_telegram_user_id=?
            ORDER BY weekday
            """,
            (int(uid),),
        ).fetchall()
    return {int(r["weekday"]): r for r in rows}


def _window(uid, day):
    return _windows(uid).get(int(day.weekday()))


def _blocks(uid, day):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT id,start_time,end_time,label
            FROM teacher_slot_blocks
            WHERE teacher_telegram_user_id=? AND block_date=?
            ORDER BY start_time,id
            """,
            (int(uid), day.isoformat()),
        ).fetchall()


def _parse_clock(value):
    value = str(value or "").strip().replace(".", ":")
    if re.fullmatch(r"\d{1,2}", value):
        value += ":00"
    if not re.fullmatch(r"\d{1,2}:\d{2}", value):
        return None
    h, m = map(int, value.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def _minutes(value):
    h, m = map(int, str(value).split(":"))
    return h * 60 + m


def _clock(total):
    return f"{total // 60:02d}:{total % 60:02d}"


def _overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _events(uid, day):
    rows = today._individual_today(uid, day) + today._group_today(uid, day)
    rows.sort(key=lambda e: (e["time"], e["kind"], e["name"].lower()))
    return rows


def _day_buttons(uid):
    local_today = datetime.now(schedule.tz(uid)).date()
    rows = []
    pair = []
    for offset in range(7):
        d = local_today + timedelta(days=offset)
        if offset == 0:
            label = "Сегодня"
        elif offset == 1:
            label = "Завтра"
        else:
            label = f"{DAY_NAMES[d.weekday()]} {d.strftime('%d.%m')}"
        pair.append(InlineKeyboardButton(label, callback_data=f"slots:day:{d.strftime('%Y%m%d')}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("⚙️ Рабочие часы", callback_data="slots:setup")])
    return InlineKeyboardMarkup(rows)


def _week_summary(uid):
    windows = _windows(uid)
    slot_minutes = _settings(uid)
    lines = [f"Длительность слота: {slot_minutes} мин"]
    for weekday in range(7):
        row = windows.get(weekday)
        if not row or not int(row["active"] or 0):
            lines.append(f"{DAY_NAMES[weekday]} — выходной")
        else:
            lines.append(f"{DAY_NAMES[weekday]} — {row['start_time']}–{row['end_time']}")
    return "\n".join(lines)


async def slots_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    ensure_tables()
    windows = _windows(uid)
    text = "🗓 Мои слоты\n\n"
    if not windows:
        text += (
            "Сначала задай рабочие часы недели. После этого я сам буду видеть, "
            "где стоят ученики и группы, а где осталось свободное время.\n\n"
            "Нажми «⚙️ Рабочие часы»."
        )
    else:
        text += _week_summary(uid) + "\n\nВыбери день, чтобы увидеть свободные и занятые слоты."
    await update.message.reply_text(text, reply_markup=_day_buttons(uid))


def _day_text(uid, day):
    window = _window(uid, day)
    duration = _settings(uid)
    events = _events(uid, day)
    blocks = _blocks(uid, day)

    lines = [
        f"🗓 Слоты • {DAY_NAMES_FULL[day.weekday()].capitalize()}, {day.strftime('%d.%m.%Y')}",
        f"Длительность: {duration} мин",
        "",
    ]

    if not window or not int(window["active"] or 0):
        lines.append("🏖 По шаблону это выходной.")
        if events:
            lines.append("\n⚠️ Но в расписании есть занятия:")
            for e in events:
                icon = "👤" if e["kind"] == "individual" else "👥"
                moved = " ↪️" if e.get("moved") else ""
                lines.append(f"🔴 {e['time']} • {icon} {e['name']}{moved}")
        return "\n".join(lines)

    start = _minutes(window["start_time"])
    end = _minutes(window["end_time"])
    if end <= start:
        return "\n".join(lines + ["⚠️ Рабочее окно настроено некорректно. Исправь его через «Рабочие часы»."])

    lines.append(f"Рабочее окно: {window['start_time']}–{window['end_time']}")
    lines.append("")

    event_intervals = []
    for event in events:
        try:
            s = _minutes(event["time"])
        except Exception:
            continue
        event_intervals.append((s, s + duration, event))

    block_intervals = []
    for block in blocks:
        try:
            block_intervals.append((_minutes(block["start_time"]), _minutes(block["end_time"]), block))
        except Exception:
            continue

    free = 0
    busy = 0
    blocked = 0
    cursor = start
    while cursor + duration <= end:
        slot_end = cursor + duration
        event_hits = [e for es, ee, e in event_intervals if _overlap(cursor, slot_end, es, ee)]
        block_hits = [b for bs, be, b in block_intervals if _overlap(cursor, slot_end, bs, be)]
        shown = f"{_clock(cursor)}–{_clock(slot_end)}"
        if event_hits:
            busy += 1
            labels = []
            for e in event_hits:
                icon = "👤" if e["kind"] == "individual" else "👥"
                moved = " ↪️" if e.get("moved") else ""
                labels.append(f"{icon} {e['name']}{moved}")
            lines.append(f"🔴 {shown} • " + ", ".join(labels))
        elif block_hits:
            blocked += 1
            labels = [str(b["label"] or "личное") for b in block_hits]
            hold = any("брон" in x.lower() or "удерж" in x.lower() for x in labels)
            lines.append(f"{'🟡' if hold else '🔒'} {shown} • " + ", ".join(labels))
        else:
            free += 1
            lines.append(f"🟢 {shown} • свободно")
        cursor += duration

    outside = []
    for es, ee, event in event_intervals:
        if es < start or ee > end:
            outside.append(event)
    if outside:
        lines.append("\n⚠️ Занятия вне рабочего окна:")
        for e in outside:
            icon = "👤" if e["kind"] == "individual" else "👥"
            lines.append(f"• {e['time']} — {icon} {e['name']}")

    lines.extend([
        "",
        f"Итого: 🟢 свободно {free} • 🔴 занято {busy} • 🔒/🟡 закрыто {blocked}",
    ])
    return "\n".join(lines)


def _day_markup(uid, day):
    rows = [
        [InlineKeyboardButton("🔒 Закрыть время", callback_data=f"slots:block:{day.strftime('%Y%m%d')}")],
    ]
    blocks = _blocks(uid, day)
    if blocks:
        rows.append([InlineKeyboardButton("🔓 Открыть блокировку", callback_data=f"slots:unblocklist:{day.strftime('%Y%m%d')}")])
    rows.extend([
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"slots:day:{day.strftime('%Y%m%d')}")],
        [InlineKeyboardButton("← К дням", callback_data="slots:menu")],
    ])
    return InlineKeyboardMarkup(rows)


async def day_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        day = datetime.strptime(q.data.rsplit(":", 1)[1], "%Y%m%d").date()
    except Exception:
        await q.edit_message_text("Не получилось определить дату.")
        return
    await q.edit_message_text(_day_text(q.from_user.id, day), reply_markup=_day_markup(q.from_user.id, day))


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    windows = _windows(uid)
    text = "🗓 Мои слоты\n\n"
    text += (_week_summary(uid) if windows else "Рабочие часы пока не настроены.")
    text += "\n\nВыбери день."
    await q.edit_message_text(text, reply_markup=_day_buttons(uid))


async def setup_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    await q.edit_message_text(
        "⚙️ Рабочие часы\n\n"
        "Пришли неделю одним сообщением. Можно указать только те дни, которые хочешь изменить.\n\n"
        "Пример:\n"
        "Пн 10:00-20:00; Вт 12:00-19:00; Ср 10:00-20:00; "
        "Чт 12:00-19:00; Пт 10:00-18:00; Сб выходной; Вс выходной\n\n"
        f"Сейчас слот = {_settings(uid)} минут. После сохранения предложу выбрать длительность."
    )
    return SET_WEEK


def _parse_week_text(text):
    changes = {}
    chunks = [x.strip() for x in re.split(r"[;\n]+", str(text or "")) if x.strip()]
    for chunk in chunks:
        m = re.match(r"^([А-Яа-яЁё]+)\s+(.+)$", chunk)
        if not m:
            continue
        day_word = m.group(1).lower().replace("ё", "е")
        weekday = DAY_ALIASES.get(day_word)
        if weekday is None:
            continue
        tail = m.group(2).strip().lower()
        if "выход" in tail or tail in {"нет", "-"}:
            changes[weekday] = None
            continue
        pair = re.search(r"(\d{1,2}(?::\d{2})?)\s*[-–—]\s*(\d{1,2}(?::\d{2})?)", tail)
        if not pair:
            continue
        start = _parse_clock(pair.group(1))
        end = _parse_clock(pair.group(2))
        if not start or not end or _minutes(end) <= _minutes(start):
            continue
        changes[weekday] = (start, end)
    return changes


async def setup_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    changes = _parse_week_text(update.message.text)
    if not changes:
        await update.message.reply_text(
            "Не смогла разобрать рабочие часы. Напиши, например:\nПн 10:00-20:00; Вт 12:00-19:00; Ср выходной"
        )
        return SET_WEEK

    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        for weekday, value in changes.items():
            if value is None:
                conn.execute(
                    """
                    INSERT INTO teacher_work_windows(teacher_telegram_user_id,weekday,start_time,end_time,active,updated_at)
                    VALUES(?,?,?,?,0,?)
                    ON CONFLICT(teacher_telegram_user_id,weekday) DO UPDATE SET
                        start_time=NULL,end_time=NULL,active=0,updated_at=excluded.updated_at
                    """,
                    (uid, weekday, None, None, now),
                )
            else:
                start, end = value
                conn.execute(
                    """
                    INSERT INTO teacher_work_windows(teacher_telegram_user_id,weekday,start_time,end_time,active,updated_at)
                    VALUES(?,?,?,?,1,?)
                    ON CONFLICT(teacher_telegram_user_id,weekday) DO UPDATE SET
                        start_time=excluded.start_time,end_time=excluded.end_time,active=1,updated_at=excluded.updated_at
                    """,
                    (uid, weekday, start, end, now),
                )
        conn.commit()

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("45 мин", callback_data="slots:duration:45"),
            InlineKeyboardButton("60 мин", callback_data="slots:duration:60"),
        ],
        [
            InlineKeyboardButton("90 мин", callback_data="slots:duration:90"),
            InlineKeyboardButton("120 мин", callback_data="slots:duration:120"),
        ],
        [InlineKeyboardButton("Оставить как есть", callback_data="slots:menu")],
    ])
    await update.message.reply_text(
        "✅ Рабочие часы сохранены.\n\nТеперь выбери обычную длительность одного занятия/слота:",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def set_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    minutes = int(q.data.rsplit(":", 1)[1])
    if minutes not in {45, 60, 90, 120}:
        return
    uid = int(q.from_user.id)
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO teacher_slot_settings(teacher_telegram_user_id,slot_minutes,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(teacher_telegram_user_id) DO UPDATE SET
                slot_minutes=excluded.slot_minutes,updated_at=excluded.updated_at
            """,
            (uid, minutes, datetime.utcnow().isoformat()),
        )
        conn.commit()
    await q.edit_message_text(
        f"✅ Длительность слота: {minutes} мин.\n\n{_week_summary(uid)}",
        reply_markup=_day_buttons(uid),
    )


async def block_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        day = datetime.strptime(q.data.rsplit(":", 1)[1], "%Y%m%d").date()
    except Exception:
        await q.edit_message_text("Не получилось определить дату.")
        return ConversationHandler.END
    context.user_data["slots_block_date"] = day.isoformat()
    await q.edit_message_text(
        f"🔒 Закрыть время • {day.strftime('%d.%m')}\n\n"
        "Напиши диапазон и, если хочешь, причину. Например:\n"
        "15:00-17:00 личное\n"
        "или\n"
        "12:00-13:00 удержание"
    )
    return BLOCK_RANGE


def _parse_block(text):
    m = re.match(
        r"^\s*(\d{1,2}(?::\d{2})?)\s*[-–—]\s*(\d{1,2}(?::\d{2})?)(?:\s+(.+))?\s*$",
        str(text or ""),
    )
    if not m:
        return None
    start = _parse_clock(m.group(1))
    end = _parse_clock(m.group(2))
    if not start or not end or _minutes(end) <= _minutes(start):
        return None
    label = (m.group(3) or "личное").strip()[:80]
    return start, end, label


async def block_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    day_text = context.user_data.pop("slots_block_date", None)
    parsed = _parse_block(update.message.text)
    if not day_text or not parsed:
        await update.message.reply_text("Не поняла диапазон. Напиши, например: 15:00-17:00 личное")
        return BLOCK_RANGE
    start, end, label = parsed
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO teacher_slot_blocks(
                teacher_telegram_user_id,block_date,start_time,end_time,label,created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, day_text, start, end, label, datetime.utcnow().isoformat()),
        )
        conn.commit()
    day = date.fromisoformat(day_text)
    await update.message.reply_text(
        f"✅ Закрыла {day.strftime('%d.%m')} {start}–{end}: {label}",
        reply_markup=base.MAIN_KB,
    )
    await update.message.reply_text(_day_text(uid, day), reply_markup=_day_markup(uid, day))
    return ConversationHandler.END


async def unblock_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        day = datetime.strptime(q.data.rsplit(":", 1)[1], "%Y%m%d").date()
    except Exception:
        await q.edit_message_text("Не получилось определить дату.")
        return
    blocks = _blocks(q.from_user.id, day)
    if not blocks:
        await q.answer("На эту дату блокировок нет", show_alert=True)
        return
    kb = []
    for b in blocks:
        kb.append([
            InlineKeyboardButton(
                f"🔓 {b['start_time']}–{b['end_time']} • {b['label']}",
                callback_data=f"slots:unblock:{b['id']}:{day.strftime('%Y%m%d')}",
            )
        ])
    kb.append([InlineKeyboardButton("← Назад", callback_data=f"slots:day:{day.strftime('%Y%m%d')}")])
    await q.edit_message_text("Какую блокировку открыть?", reply_markup=InlineKeyboardMarkup(kb))


async def unblock_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":")
    try:
        block_id = int(parts[2])
        day = datetime.strptime(parts[3], "%Y%m%d").date()
    except Exception:
        await q.edit_message_text("Не получилось определить блокировку.")
        return
    uid = int(q.from_user.id)
    with base.db() as conn:
        conn.execute(
            "DELETE FROM teacher_slot_blocks WHERE id=? AND teacher_telegram_user_id=?",
            (block_id, uid),
        )
        conn.commit()
    await q.edit_message_text(_day_text(uid, day), reply_markup=_day_markup(uid, day))


def install(app):
    ensure_tables()
    base.MAIN_KB = _main_keyboard()

    setup_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_begin, pattern=r"^slots:setup$")],
        states={SET_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_save)]},
        fallbacks=[],
        per_message=False,
    )
    block_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(block_begin, pattern=r"^slots:block:\d{8}$")],
        states={BLOCK_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_save)]},
        fallbacks=[],
        per_message=False,
    )

    app.add_handler(setup_conversation, group=-15)
    app.add_handler(block_conversation, group=-15)
    app.add_handler(MessageHandler(filters.Regex(r"^🗓 Мои слоты$"), slots_menu), group=-14)
    app.add_handler(CallbackQueryHandler(day_view, pattern=r"^slots:day:\d{8}$"), group=-14)
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern=r"^slots:menu$"), group=-14)
    app.add_handler(CallbackQueryHandler(set_duration, pattern=r"^slots:duration:(?:45|60|90|120)$"), group=-14)
    app.add_handler(CallbackQueryHandler(unblock_list, pattern=r"^slots:unblocklist:\d{8}$"), group=-14)
    app.add_handler(CallbackQueryHandler(unblock_apply, pattern=r"^slots:unblock:\d+:\d{8}$"), group=-14)
    print("PREPODMIN availability slots ready: weekly windows + busy/free + manual blocks", flush=True)
    return app
