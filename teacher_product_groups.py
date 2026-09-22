from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule

ADD_GROUP_NAME = 40
ADD_GROUP_SLOT_GROUP, ADD_GROUP_SLOT_DAY, ADD_GROUP_SLOT_TIME = range(41, 44)
MOVE_GROUP_DATE, MOVE_GROUP_TIME = range(44, 46)

ORIGINAL_INDIVIDUAL_SCHEDULE_MENU = schedule.schedule_menu


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_groups_teacher
            ON teacher_groups(teacher_telegram_user_id, active, name);

            CREATE TABLE IF NOT EXISTS group_schedule_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                weekday INTEGER NOT NULL,
                time_text TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_group_schedule_teacher
            ON group_schedule_slots(teacher_telegram_user_id, active, weekday, time_text);

            CREATE TABLE IF NOT EXISTS group_schedule_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                original_date TEXT NOT NULL,
                new_date TEXT NOT NULL,
                new_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_group_moves_slot_date
            ON group_schedule_moves(schedule_slot_id, original_date);
            """
        )
        conn.commit()


def groups(uid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name FROM teacher_groups WHERE teacher_telegram_user_id=? AND active=1 ORDER BY lower(name)",
            (int(uid),),
        ).fetchall()


def get_group(uid, gid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name FROM teacher_groups WHERE id=? AND teacher_telegram_user_id=? AND active=1",
            (int(gid), int(uid)),
        ).fetchone()


def add_group(uid, name):
    with base.db() as conn:
        conn.execute(
            "INSERT INTO teacher_groups(teacher_telegram_user_id,name,created_at) VALUES(?,?,?)",
            (int(uid), name.strip(), datetime.utcnow().isoformat()),
        )
        conn.commit()


def archive_group(uid, gid):
    with base.db() as conn:
        conn.execute(
            "UPDATE teacher_groups SET active=0 WHERE id=? AND teacher_telegram_user_id=?",
            (int(gid), int(uid)),
        )
        conn.execute(
            "UPDATE group_schedule_slots SET active=0 WHERE group_id=? AND teacher_telegram_user_id=?",
            (int(gid), int(uid)),
        )
        conn.commit()


def group_slots(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT gs.id,gs.group_id,gs.weekday,gs.time_text,g.name AS group_name
            FROM group_schedule_slots gs
            JOIN teacher_groups g ON g.id=gs.group_id
            WHERE gs.teacher_telegram_user_id=? AND gs.active=1 AND g.active=1
            ORDER BY gs.weekday,gs.time_text,lower(g.name)
            """,
            (int(uid),),
        ).fetchall()


def group_slot(uid, slot_id):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT gs.id,gs.group_id,gs.weekday,gs.time_text,g.name AS group_name
            FROM group_schedule_slots gs
            JOIN teacher_groups g ON g.id=gs.group_id
            WHERE gs.id=? AND gs.teacher_telegram_user_id=? AND gs.active=1 AND g.active=1
            """,
            (int(slot_id), int(uid)),
        ).fetchone()


def add_group_slot(uid, gid, weekday, time_text):
    with base.db() as conn:
        conn.execute(
            "INSERT INTO group_schedule_slots(teacher_telegram_user_id,group_id,weekday,time_text,created_at) VALUES(?,?,?,?,?)",
            (int(uid), int(gid), int(weekday), time_text, datetime.utcnow().isoformat()),
        )
        conn.commit()


def archive_group_slot(uid, slot_id):
    with base.db() as conn:
        conn.execute(
            "UPDATE group_schedule_slots SET active=0 WHERE id=? AND teacher_telegram_user_id=?",
            (int(slot_id), int(uid)),
        )
        conn.commit()


def save_group_move(uid, slot_id, original_date, new_date, new_time):
    with base.db() as conn:
        conn.execute(
            "DELETE FROM group_schedule_moves WHERE teacher_telegram_user_id=? AND schedule_slot_id=? AND original_date=?",
            (int(uid), int(slot_id), original_date),
        )
        conn.execute(
            "INSERT INTO group_schedule_moves(teacher_telegram_user_id,schedule_slot_id,original_date,new_date,new_time,created_at) VALUES(?,?,?,?,?,?)",
            (int(uid), int(slot_id), original_date, new_date, new_time, datetime.utcnow().isoformat()),
        )
        conn.commit()


def next_group_date(uid, s):
    now = datetime.now(schedule.tz(uid))
    delta = (int(s["weekday"]) - now.weekday()) % 7
    d = now.date() + timedelta(days=delta)
    if delta == 0:
        h, m = map(int, s["time_text"].split(":"))
        if (now.hour, now.minute) >= (h, m):
            d += timedelta(days=7)
    return d


def group_upcoming(uid, days=14):
    all_slots = group_slots(uid)
    if not all_slots:
        return []
    today = datetime.now(schedule.tz(uid)).date()
    end = today + timedelta(days=days)
    with base.db() as conn:
        rows = conn.execute(
            "SELECT schedule_slot_id,original_date,new_date,new_time FROM group_schedule_moves WHERE teacher_telegram_user_id=? AND original_date>=? AND original_date<=?",
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
                    out.append((date.fromisoformat(move["new_date"]), move["new_time"], s["group_name"], True))
                else:
                    out.append((d, s["time_text"], s["group_name"], False))
            d += timedelta(days=1)
    return sorted(out, key=lambda x: (x[0], x[1], x[2].lower()))


async def people_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👥 Ученики и группы\n\nВыбери формат работы. Они ведутся отдельно."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Индивидуальные", callback_data="people:individual")],
        [InlineKeyboardButton("👥 Группы", callback_data="people:groups")],
    ])
    await update.message.reply_text(text, reply_markup=kb)


def _telegram_link_status(uid, student_id):
    with base.db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_reminder_people'"
        ).fetchone()
        if not exists:
            return False
        row = conn.execute(
            """SELECT telegram_user_id FROM student_reminder_people
               WHERE teacher_id=? AND kind='individual' AND student_id=? AND active=1
               LIMIT 1""",
            (int(uid), int(student_id)),
        ).fetchone()
    return bool(row and row["telegram_user_id"])


async def individual_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = base.list_students(q.from_user.id)
    if rows:
        lines = []
        for r in rows[:30]:
            status = "🟢 Telegram подключён" if _telegram_link_status(q.from_user.id, r["id"]) else "🔴 Telegram не подключён"
            lines.append(f"• {r['name']} — {status}")
        names = "\n".join(lines)
        text = f"👤 Индивидуальные: {len(rows)}\n\n{names}"
    else:
        text = "👤 Индивидуальные\n\nПока учеников нет."
    buttons = [[InlineKeyboardButton("➕ Добавить ученика", callback_data="student:add")]]
    if rows:
        buttons.append([InlineKeyboardButton("📨 Подключить Telegram", callback_data="srem:individual")])
    buttons += [
        [InlineKeyboardButton("🗑 Удалить / архив", callback_data="student:remove")],
        [InlineKeyboardButton("⬅️ К форматам", callback_data="people:back")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def groups_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = groups(q.from_user.id)
    if rows:
        names = "\n".join(f"• {r['name']}" for r in rows[:30])
        text = f"👥 Группы: {len(rows)}\n\n{names}"
    else:
        text = "👥 Группы\n\nПока групп нет. Создай первую."
    buttons = [[InlineKeyboardButton("➕ Создать группу", callback_data="group:add")]]
    if rows:
        buttons.append([InlineKeyboardButton("🗑 Удалить / архив", callback_data="group:remove")])
    buttons.append([InlineKeyboardButton("⬅️ К форматам", callback_data="people:back")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def people_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "👥 Ученики и группы\n\nВыбери формат работы. Они ведутся отдельно.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Индивидуальные", callback_data="people:individual")],
            [InlineKeyboardButton("👥 Группы", callback_data="people:groups")],
        ]),
    )


async def add_group_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Как называется группа?\n\nНапример: ЕГЭ 11 класс или Пн/Ср 18:00")
    return ADD_GROUP_NAME


async def add_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Название слишком короткое. Напиши название группы.")
        return ADD_GROUP_NAME
    add_group(update.effective_user.id, name)
    await update.message.reply_text(f"✅ Группа «{name}» создана.", reply_markup=base.MAIN_KB)
    return ConversationHandler.END


async def remove_group_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = groups(q.from_user.id)
    if not rows:
        await q.edit_message_text("Удалять пока нечего.")
        return
    kb = [[InlineKeyboardButton(f"🗑 {r['name']}", callback_data=f"group:rm:{r['id']}")] for r in rows[:30]]
    await q.edit_message_text("Какую группу убрать в архив?", reply_markup=InlineKeyboardMarkup(kb))


async def remove_group_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    archive_group(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    await q.edit_message_text("✅ Группа перенесена в архив.")


async def schedule_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Индивидуальное", callback_data="schedule:individual")],
        [InlineKeyboardButton("👥 Группы", callback_data="groups:schedule")],
    ])
    await update.message.reply_text("📅 Расписание\n\nКакое расписание открыть?", reply_markup=kb)


async def individual_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    all_slots = schedule.slots(uid)
    if not all_slots:
        text = "📅 Индивидуальное расписание\n\nПока занятий нет. Добавь первое регулярное занятие."
    else:
        lines = ["📅 Индивидуальные • ближайшие 14 дней"]
        last = None
        for d, time_text, name, moved in schedule.upcoming(uid)[:40]:
            if d != last:
                lines.append(f"\n{schedule.DAY_NAMES[d.weekday()]}, {d.strftime('%d.%m')}")
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
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def group_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    all_slots = group_slots(uid)
    if not all_slots:
        text = "📅 Расписание групп\n\nПока занятий нет. Добавь первое регулярное занятие группы."
    else:
        lines = ["📅 Группы • ближайшие 14 дней"]
        last = None
        for d, time_text, name, moved in group_upcoming(uid)[:40]:
            if d != last:
                lines.append(f"\n{schedule.DAY_NAMES[d.weekday()]}, {d.strftime('%d.%m')}")
                last = d
            lines.append(f"{time_text} — {name}{' ↪️' if moved else ''}")
        lines.append("\n↪️ — занятие перенесено")
        text = "\n".join(lines)
    buttons = [[InlineKeyboardButton("➕ Добавить занятие группы", callback_data="gs:add")]]
    if all_slots:
        buttons += [
            [InlineKeyboardButton("↪️ Перенести занятие", callback_data="gs:transfer")],
            [InlineKeyboardButton("🗑 Удалить из расписания", callback_data="gs:remove")],
        ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def group_slot_add_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = groups(q.from_user.id)
    if not rows:
        await q.edit_message_text("Сначала создай группу в разделе «👥 Ученики и группы» → «👥 Группы».")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(r["name"], callback_data=f"gs:group:{r['id']}")] for r in rows[:30]]
    await q.edit_message_text("Какой группе добавляем занятие?", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_GROUP_SLOT_GROUP


async def group_slot_pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.rsplit(":", 1)[1])
    row = get_group(q.from_user.id, gid)
    if not row:
        await q.edit_message_text("Группа не найдена.")
        return ConversationHandler.END
    context.user_data["gs_gid"] = gid
    context.user_data["gs_name"] = row["name"]
    kb = [
        [InlineKeyboardButton("Пн", callback_data="gs:day:0"), InlineKeyboardButton("Вт", callback_data="gs:day:1"), InlineKeyboardButton("Ср", callback_data="gs:day:2")],
        [InlineKeyboardButton("Чт", callback_data="gs:day:3"), InlineKeyboardButton("Пт", callback_data="gs:day:4"), InlineKeyboardButton("Сб", callback_data="gs:day:5")],
        [InlineKeyboardButton("Вс", callback_data="gs:day:6")],
    ]
    await q.edit_message_text(f"Группа: {row['name']}\n\nВ какой день проходит занятие?", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_GROUP_SLOT_DAY


async def group_slot_pick_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    weekday = int(q.data.rsplit(":", 1)[1])
    context.user_data["gs_day"] = weekday
    await q.edit_message_text(f"{schedule.DAY_NAMES_FULL[weekday]}.\n\nНапиши время, например 18:30")
    return ADD_GROUP_SLOT_TIME


async def group_slot_pick_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = schedule.parse_time(update.message.text)
    if not time_text:
        await update.message.reply_text("Не поняла время. Напиши, например: 18:30")
        return ADD_GROUP_SLOT_TIME
    gid = context.user_data.pop("gs_gid", None)
    weekday = context.user_data.pop("gs_day", None)
    name = context.user_data.pop("gs_name", "Группа")
    if gid is None or weekday is None:
        await update.message.reply_text("Настройка сбилась. Открой расписание и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    add_group_slot(update.effective_user.id, gid, weekday, time_text)
    await update.message.reply_text(
        f"✅ {name}: {schedule.DAY_NAMES_FULL[weekday].lower()} в {time_text}.\nЭто регулярное групповое занятие.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def group_transfer_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = group_slots(q.from_user.id)
    if not rows:
        await q.edit_message_text("Переносить пока нечего.")
        return
    kb = []
    for s in rows[:30]:
        d = next_group_date(q.from_user.id, s)
        label = f"{s['group_name']} • {schedule.DAY_NAMES[int(s['weekday'])]} {s['time_text']} • {d.strftime('%d.%m')}"
        kb.append([InlineKeyboardButton(label, callback_data=f"gs:move:{s['id']}")])
    await q.edit_message_text("Какое ближайшее групповое занятие переносим?", reply_markup=InlineKeyboardMarkup(kb))


async def group_move_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    s = group_slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    if not s:
        await q.edit_message_text("Занятие не найдено.")
        return ConversationHandler.END
    original = next_group_date(q.from_user.id, s)
    context.user_data.update(gm_slot=int(s["id"]), gm_original=original.isoformat(), gm_name=s["group_name"], gm_old_time=s["time_text"])
    await q.edit_message_text(f"Переносим: {s['group_name']} — {original.strftime('%d.%m')} в {s['time_text']}.\n\nНа какую дату? Например: 16.09")
    return MOVE_GROUP_DATE


async def group_move_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(schedule.tz(update.effective_user.id)).date()
    d = schedule.parse_date(update.message.text, today)
    if not d or d < today:
        await update.message.reply_text("Не поняла дату или она уже прошла. Напиши, например: 16.09")
        return MOVE_GROUP_DATE
    context.user_data["gm_new_date"] = d.isoformat()
    await update.message.reply_text("Во сколько будет перенесённое занятие? Например: 19:00")
    return MOVE_GROUP_TIME


async def group_move_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = schedule.parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Не поняла время. Напиши, например: 19:00")
        return MOVE_GROUP_TIME
    slot_id = context.user_data.pop("gm_slot", None)
    original = context.user_data.pop("gm_original", None)
    new_date = context.user_data.pop("gm_new_date", None)
    name = context.user_data.pop("gm_name", "Группа")
    old_time = context.user_data.pop("gm_old_time", "")
    if not slot_id or not original or not new_date:
        await update.message.reply_text("Перенос сбился. Попробуй ещё раз через расписание.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    save_group_move(update.effective_user.id, slot_id, original, new_date, t)
    await update.message.reply_text(
        f"✅ Перенос группы сохранён.\n{name}: {date.fromisoformat(original).strftime('%d.%m')} {old_time} → {date.fromisoformat(new_date).strftime('%d.%m')} {t}.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def group_remove_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = group_slots(q.from_user.id)
    if not rows:
        await q.edit_message_text("Удалять пока нечего.")
        return
    kb = [[InlineKeyboardButton(f"🗑 {s['group_name']} • {schedule.DAY_NAMES[int(s['weekday'])]} {s['time_text']}", callback_data=f"gs:rm:{s['id']}")] for s in rows[:30]]
    await q.edit_message_text("Какое регулярное групповое занятие удалить?", reply_markup=InlineKeyboardMarkup(kb))


async def group_remove_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    archive_group_slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    await q.edit_message_text("✅ Групповое занятие убрано из расписания.")


def build_app():
    ensure_tables()
    base.MAIN_KB = ReplyKeyboardMarkup(
        [["👥 Ученики и группы", "📅 Расписание"], ["🔔 Напоминания", "💳 Оплаты"], ["⚙️ Настройки"]],
        resize_keyboard=True,
    )
    schedule.schedule_menu = schedule_selector
    app = schedule.build_app()

    app.add_handler(MessageHandler(filters.Regex(r"^👥 Ученики и группы$"), people_menu))
    app.add_handler(CallbackQueryHandler(individual_menu, pattern=r"^people:individual$"))
    app.add_handler(CallbackQueryHandler(groups_menu, pattern=r"^people:groups$"))
    app.add_handler(CallbackQueryHandler(people_back, pattern=r"^people:back$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_group_begin, pattern=r"^group:add$")],
        states={ADD_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_name)]},
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(remove_group_picker, pattern=r"^group:remove$"))
    app.add_handler(CallbackQueryHandler(remove_group_apply, pattern=r"^group:rm:\d+$"))

    app.add_handler(CallbackQueryHandler(individual_schedule_callback, pattern=r"^schedule:individual$"))
    app.add_handler(CallbackQueryHandler(group_schedule_menu, pattern=r"^groups:schedule$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(group_slot_add_begin, pattern=r"^gs:add$")],
        states={
            ADD_GROUP_SLOT_GROUP: [CallbackQueryHandler(group_slot_pick_group, pattern=r"^gs:group:\d+$")],
            ADD_GROUP_SLOT_DAY: [CallbackQueryHandler(group_slot_pick_day, pattern=r"^gs:day:[0-6]$")],
            ADD_GROUP_SLOT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_slot_pick_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(group_transfer_picker, pattern=r"^gs:transfer$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(group_move_begin, pattern=r"^gs:move:\d+$")],
        states={
            MOVE_GROUP_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_move_date)],
            MOVE_GROUP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_move_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(group_remove_picker, pattern=r"^gs:remove$"))
    app.add_handler(CallbackQueryHandler(group_remove_apply, pattern=r"^gs:rm:\d+$"))
    return app
