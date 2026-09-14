import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base

ADD_LESSON_STUDENT, ADD_LESSON_DAY, ADD_LESSON_TIME = range(20, 23)
MOVE_DATE, MOVE_TIME = range(30, 32)
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_NAMES_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedule_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                time_text TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schedule_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                original_date TEXT NOT NULL,
                new_date TEXT NOT NULL,
                new_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_schedule_teacher
            ON schedule_slots(teacher_telegram_user_id, active, weekday, time_text);
            CREATE INDEX IF NOT EXISTS idx_schedule_moves_slot_date
            ON schedule_moves(schedule_slot_id, original_date);
            """
        )
        conn.commit()


def tz(uid):
    row = base.teacher(uid)
    value = row["timezone"] if row and row["timezone"] else "Europe/Moscow"
    try:
        return ZoneInfo(value)
    except Exception:
        return ZoneInfo("Europe/Moscow")


def get_student(uid, sid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name,contact FROM students WHERE id=? AND teacher_telegram_user_id=? AND active=1",
            (int(sid), int(uid)),
        ).fetchone()


def slots(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT ss.id,ss.student_id,ss.weekday,ss.time_text,s.name AS student_name
            FROM schedule_slots ss JOIN students s ON s.id=ss.student_id
            WHERE ss.teacher_telegram_user_id=? AND ss.active=1 AND s.active=1
            ORDER BY ss.weekday,ss.time_text,lower(s.name)
            """,
            (int(uid),),
        ).fetchall()


def slot(uid, slot_id):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT ss.id,ss.student_id,ss.weekday,ss.time_text,s.name AS student_name
            FROM schedule_slots ss JOIN students s ON s.id=ss.student_id
            WHERE ss.id=? AND ss.teacher_telegram_user_id=? AND ss.active=1 AND s.active=1
            """,
            (int(slot_id), int(uid)),
        ).fetchone()


def add_slot(uid, sid, weekday, time_text):
    with base.db() as conn:
        conn.execute(
            "INSERT INTO schedule_slots(teacher_telegram_user_id,student_id,weekday,time_text,created_at) VALUES(?,?,?,?,?)",
            (int(uid), int(sid), int(weekday), time_text, datetime.utcnow().isoformat()),
        )
        conn.commit()


def archive_slot(uid, slot_id):
    with base.db() as conn:
        conn.execute(
            "UPDATE schedule_slots SET active=0 WHERE id=? AND teacher_telegram_user_id=?",
            (int(slot_id), int(uid)),
        )
        conn.commit()


def save_move(uid, slot_id, original_date, new_date, new_time):
    with base.db() as conn:
        conn.execute(
            "DELETE FROM schedule_moves WHERE teacher_telegram_user_id=? AND schedule_slot_id=? AND original_date=?",
            (int(uid), int(slot_id), original_date),
        )
        conn.execute(
            "INSERT INTO schedule_moves(teacher_telegram_user_id,schedule_slot_id,original_date,new_date,new_time,created_at) VALUES(?,?,?,?,?,?)",
            (int(uid), int(slot_id), original_date, new_date, new_time, datetime.utcnow().isoformat()),
        )
        conn.commit()


def parse_time(value):
    value = value.strip().replace(".", ":")
    if not re.fullmatch(r"\d{1,2}:\d{2}", value):
        return None
    h, m = map(int, value.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def parse_date(value, today):
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(value, fmt).date()
            if fmt == "%d.%m":
                d = d.replace(year=today.year)
                if d < today - timedelta(days=30):
                    d = d.replace(year=today.year + 1)
            return d
        except ValueError:
            pass
    return None


def next_date(uid, s):
    now = datetime.now(tz(uid))
    delta = (int(s["weekday"]) - now.weekday()) % 7
    d = now.date() + timedelta(days=delta)
    if delta == 0:
        h, m = map(int, s["time_text"].split(":"))
        if (now.hour, now.minute) >= (h, m):
            d += timedelta(days=7)
    return d


def upcoming(uid, days=14):
    all_slots = slots(uid)
    if not all_slots:
        return []
    today = datetime.now(tz(uid)).date()
    end = today + timedelta(days=days)
    with base.db() as conn:
        rows = conn.execute(
            "SELECT schedule_slot_id,original_date,new_date,new_time FROM schedule_moves WHERE teacher_telegram_user_id=? AND original_date>=? AND original_date<=?",
            (int(uid), today.isoformat(), end.isoformat()),
        ).fetchall()
    moves = {(int(r["schedule_slot_id"]), r["original_date"]): r for r in rows}
    out = []
    for s in all_slots:
        d = today
        while d <= end:
            if d.weekday() == int(s["weekday"]):
                move = moves.get((int(s["id"]), d.isoformat()))
                if move:
                    out.append((date.fromisoformat(move["new_date"]), move["new_time"], s["student_name"], True))
                else:
                    out.append((d, s["time_text"], s["student_name"], False))
            d += timedelta(days=1)
    return sorted(out, key=lambda x: (x[0], x[1], x[2].lower()))


async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    all_slots = slots(uid)
    if not all_slots:
        text = "📅 Расписание\n\nПока занятий нет. Добавь первое регулярное занятие: ученик → день недели → время."
    else:
        lines = ["📅 Ближайшие 14 дней"]
        last = None
        for d, time_text, name, moved in upcoming(uid)[:40]:
            if d != last:
                lines.append(f"\n{DAY_NAMES[d.weekday()]}, {d.strftime('%d.%m')}")
                last = d
            lines.append(f"{time_text} — {name}{' ↪️' if moved else ''}")
        lines.append("\n↪️ — занятие перенесено")
        text = "\n".join(lines)
    buttons = [[InlineKeyboardButton("➕ Добавить занятие", callback_data="schedule:add")]]
    if all_slots:
        buttons += [
            [InlineKeyboardButton("↪️ Перенести занятие", callback_data="schedule:transfer")],
            [InlineKeyboardButton("🗑 Удалить из расписания", callback_data="schedule:remove")],
        ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def enhanced_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "📅 Расписание":
        return await schedule_menu(update, context)
    return await ORIGINAL_STUB(update, context)


async def add_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    students = base.list_students(q.from_user.id)
    if not students:
        await q.edit_message_text("Сначала добавь хотя бы одного ученика в разделе «👥 Ученики».")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(s["name"], callback_data=f"lesson:student:{s['id']}")] for s in students[:30]]
    await q.edit_message_text("Кому добавляем занятие?", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_LESSON_STUDENT


async def add_student_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sid = int(q.data.rsplit(":", 1)[1])
    student = get_student(q.from_user.id, sid)
    if not student:
        await q.edit_message_text("Не нашла ученика. Открой «👥 Ученики» и попробуй снова.")
        return ConversationHandler.END
    context.user_data["lesson_sid"] = sid
    context.user_data["lesson_name"] = student["name"]
    kb = [
        [InlineKeyboardButton("Пн", callback_data="lesson:day:0"), InlineKeyboardButton("Вт", callback_data="lesson:day:1"), InlineKeyboardButton("Ср", callback_data="lesson:day:2")],
        [InlineKeyboardButton("Чт", callback_data="lesson:day:3"), InlineKeyboardButton("Пт", callback_data="lesson:day:4"), InlineKeyboardButton("Сб", callback_data="lesson:day:5")],
        [InlineKeyboardButton("Вс", callback_data="lesson:day:6")],
    ]
    await q.edit_message_text(f"Ученик: {student['name']}\n\nВ какой день проходит регулярное занятие?", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_LESSON_DAY


async def add_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    weekday = int(q.data.rsplit(":", 1)[1])
    context.user_data["lesson_day"] = weekday
    await q.edit_message_text(f"{DAY_NAMES_FULL[weekday]}.\n\nНапиши время, например 18:30")
    return ADD_LESSON_TIME


async def add_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = parse_time(update.message.text)
    if not time_text:
        await update.message.reply_text("Не поняла время. Напиши, например: 18:30")
        return ADD_LESSON_TIME
    sid = context.user_data.pop("lesson_sid", None)
    weekday = context.user_data.pop("lesson_day", None)
    name = context.user_data.pop("lesson_name", "Ученик")
    if sid is None or weekday is None:
        await update.message.reply_text("Настройка сбилась. Открой «📅 Расписание» и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    add_slot(update.effective_user.id, sid, weekday, time_text)
    await update.message.reply_text(
        f"✅ {name}: {DAY_NAMES_FULL[weekday].lower()} в {time_text}.\nЭто регулярное еженедельное занятие.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def transfer_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    all_slots = slots(q.from_user.id)
    if not all_slots:
        await q.edit_message_text("Переносить пока нечего.")
        return
    kb = []
    for s in all_slots[:30]:
        d = next_date(q.from_user.id, s)
        label = f"{s['student_name']} • {DAY_NAMES[int(s['weekday'])]} {s['time_text']} • {d.strftime('%d.%m')}"
        kb.append([InlineKeyboardButton(label, callback_data=f"schedule:move:{s['id']}")])
    await q.edit_message_text("Какое ближайшее занятие переносим?", reply_markup=InlineKeyboardMarkup(kb))


async def move_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    s = slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    if not s:
        await q.edit_message_text("Занятие не найдено. Открой расписание заново.")
        return ConversationHandler.END
    original = next_date(q.from_user.id, s)
    context.user_data.update(move_slot=int(s["id"]), move_original=original.isoformat(), move_name=s["student_name"], move_old_time=s["time_text"])
    await q.edit_message_text(f"Переносим: {s['student_name']} — {original.strftime('%d.%m')} в {s['time_text']}.\n\nНа какую дату? Например: 16.09")
    return MOVE_DATE


async def move_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(tz(update.effective_user.id)).date()
    d = parse_date(update.message.text, today)
    if not d or d < today:
        await update.message.reply_text("Не поняла дату или она уже прошла. Напиши, например: 16.09")
        return MOVE_DATE
    context.user_data["move_new_date"] = d.isoformat()
    await update.message.reply_text("Во сколько будет перенесённое занятие? Например: 19:00")
    return MOVE_TIME


async def move_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Не поняла время. Напиши, например: 19:00")
        return MOVE_TIME
    slot_id = context.user_data.pop("move_slot", None)
    original = context.user_data.pop("move_original", None)
    new_date = context.user_data.pop("move_new_date", None)
    name = context.user_data.pop("move_name", "Ученик")
    old_time = context.user_data.pop("move_old_time", "")
    if not slot_id or not original or not new_date:
        await update.message.reply_text("Перенос сбился. Попробуй ещё раз через «📅 Расписание».", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    save_move(update.effective_user.id, slot_id, original, new_date, t)
    await update.message.reply_text(
        f"✅ Перенос сохранён.\n{name}: {date.fromisoformat(original).strftime('%d.%m')} {old_time} → {date.fromisoformat(new_date).strftime('%d.%m')} {t}.\n\nСледующим шагом подключим сообщение ученику.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def remove_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    all_slots = slots(q.from_user.id)
    if not all_slots:
        await q.edit_message_text("Удалять пока нечего 🙂")
        return
    kb = [[InlineKeyboardButton(f"🗑 {s['student_name']} • {DAY_NAMES[int(s['weekday'])]} {s['time_text']}", callback_data=f"schedule:rm:{s['id']}")] for s in all_slots[:30]]
    await q.edit_message_text("Какое регулярное занятие убрать?", reply_markup=InlineKeyboardMarkup(kb))


async def remove_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    archive_slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    await q.edit_message_text("✅ Регулярное занятие убрано из расписания.")


ORIGINAL_STUB = base.stub


def build_app():
    ensure_tables()
    base.stub = enhanced_stub
    app = base.build_app()
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_begin, pattern=r"^schedule:add$")],
        states={
            ADD_LESSON_STUDENT: [CallbackQueryHandler(add_student_pick, pattern=r"^lesson:student:\d+$")],
            ADD_LESSON_DAY: [CallbackQueryHandler(add_day, pattern=r"^lesson:day:[0-6]$")],
            ADD_LESSON_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(transfer_picker, pattern=r"^schedule:transfer$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(move_begin, pattern=r"^schedule:move:\d+$")],
        states={MOVE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, move_date)], MOVE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, move_time)]},
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(remove_picker, pattern=r"^schedule:remove$"))
    app.add_handler(CallbackQueryHandler(remove_apply, pattern=r"^schedule:rm:\d+$"))
    return app
