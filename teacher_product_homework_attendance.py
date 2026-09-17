"""Homework + attendance for PREPODMIN.

Teacher-first MVP:
- mark attendance for today's individual lessons and group members;
- assign homework to an individual student or a group;
- notify linked Telegram students and let them mark homework done;
- show active homework and simple attendance stats.
"""
import re
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_today as today
import teacher_product_student_reminders as student_reminders

HW_TEXT, HW_DUE = range(610, 612)


def ensure_tables():
    student_reminders.ensure_tables()
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL CHECK(lesson_kind IN ('individual','group')),
                schedule_slot_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                student_id INTEGER,
                person_id INTEGER,
                person_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present','absent','cancelled')),
                marked_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_teacher_attendance_occurrence
            ON teacher_attendance(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                COALESCE(student_id,-1),COALESCE(person_id,-1)
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_attendance_teacher_date
            ON teacher_attendance(teacher_telegram_user_id,lesson_date,status);

            CREATE TABLE IF NOT EXISTS teacher_homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                target_kind TEXT NOT NULL CHECK(target_kind IN ('individual','group')),
                student_id INTEGER,
                group_id INTEGER,
                target_name TEXT NOT NULL,
                homework_text TEXT NOT NULL,
                due_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_teacher_due
            ON teacher_homework(teacher_telegram_user_id,active,due_date);

            CREATE TABLE IF NOT EXISTS teacher_homework_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                homework_id INTEGER NOT NULL,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER,
                person_id INTEGER,
                person_name TEXT NOT NULL,
                telegram_user_id INTEGER,
                status TEXT NOT NULL DEFAULT 'assigned' CHECK(status IN ('assigned','done')),
                completed_at TEXT,
                UNIQUE(homework_id,COALESCE(student_id,-1),COALESCE(person_id,-1))
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_recipients_hw
            ON teacher_homework_recipients(homework_id,status);
            """
        )
        conn.commit()


def _main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["➕ Быстрая задача"],
            ["📍 Сегодня", "🌅 Завтра"],
            ["🗓 Мои слоты", "✅ Задачи"],
            ["📚 ДЗ и посещаемость"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )


def _status_icon(status):
    return {"present": "✅", "absent": "❌", "cancelled": "↩️"}.get(status, "▫️")


def _attendance_status(uid, kind, slot_id, day, student_id=None, person_id=None):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT status FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND lesson_kind=? AND schedule_slot_id=?
              AND lesson_date=? AND COALESCE(student_id,-1)=COALESCE(?,-1)
              AND COALESCE(person_id,-1)=COALESCE(?,-1)
            """,
            (int(uid), kind, int(slot_id), day.isoformat(), student_id, person_id),
        ).fetchone()
    return row["status"] if row else None


def _save_attendance(uid, kind, slot_id, day, name, status, student_id=None, person_id=None):
    ensure_tables()
    now = datetime.now(schedule.tz(uid)).isoformat()
    with base.db() as conn:
        existing = conn.execute(
            """
            SELECT id FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND lesson_kind=? AND schedule_slot_id=?
              AND lesson_date=? AND COALESCE(student_id,-1)=COALESCE(?,-1)
              AND COALESCE(person_id,-1)=COALESCE(?,-1)
            """,
            (int(uid), kind, int(slot_id), day.isoformat(), student_id, person_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE teacher_attendance SET status=?,person_name=?,marked_at=? WHERE id=?",
                (status, name, now, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO teacher_attendance(
                    teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                    student_id,person_id,person_name,status,marked_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (int(uid), kind, int(slot_id), day.isoformat(), student_id, person_id, name, status, now),
            )
        conn.commit()


def _today_events(uid, day):
    rows = today._individual_today(uid, day) + today._group_today(uid, day)
    rows.sort(key=lambda e: (e["time"], e["kind"], e["name"].lower()))
    return rows


def _attendance_picker_markup(uid, day):
    rows = []
    compact = day.strftime("%Y%m%d")
    for event in _today_events(uid, day):
        moved = " ↪️" if event.get("moved") else ""
        if event["kind"] == "individual":
            status = _attendance_status(uid, "individual", event["slot_id"], day, student_id=event["student_id"])
            label = f"{_status_icon(status)} {event['time']} • 👤 {event['name']}{moved}"
            data = f"ha:atti:{event['slot_id']}:{event['student_id']}:{compact}"
        else:
            members = student_reminders._members(uid, event["group_id"])
            marked = sum(bool(_attendance_status(uid, "group", event["slot_id"], day, person_id=int(m["id"]))) for m in members)
            suffix = f" • {marked}/{len(members)}" if members else " • нет состава"
            label = f"👥 {event['time']} • {event['name']}{moved}{suffix}"
            data = f"ha:attg:{event['slot_id']}:{event['group_id']}:{compact}"
        rows.append([InlineKeyboardButton(label, callback_data=data)])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="ha:menu")])
    return InlineKeyboardMarkup(rows)


async def send_today_attendance_prompt(message, uid, day):
    ensure_tables()
    if not _today_events(uid, day):
        return
    await message.reply_text(
        "🧾 Посещаемость сегодня\n\nОтметь, кто был на занятии. Для группы можно отметить каждого ученика отдельно.",
        reply_markup=_attendance_picker_markup(uid, day),
    )


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Посещаемость сегодня", callback_data="ha:attendance")],
        [InlineKeyboardButton("📝 Выдать ДЗ", callback_data="ha:hw:new")],
        [InlineKeyboardButton("📚 Активные ДЗ", callback_data="ha:hw:list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ha:stats")],
    ])
    await update.message.reply_text(
        "📚 ДЗ и посещаемость\n\nЗдесь можно отметить урок, выдать домашнее задание и увидеть долги.",
        reply_markup=kb,
    )
    raise ApplicationHandlerStop


async def callback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Посещаемость сегодня", callback_data="ha:attendance")],
        [InlineKeyboardButton("📝 Выдать ДЗ", callback_data="ha:hw:new")],
        [InlineKeyboardButton("📚 Активные ДЗ", callback_data="ha:hw:list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="ha:stats")],
    ])
    await q.edit_message_text("📚 ДЗ и посещаемость\n\nВыбери действие.", reply_markup=kb)
    raise ApplicationHandlerStop


async def attendance_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    day = datetime.now(schedule.tz(uid)).date()
    events = _today_events(uid, day)
    if not events:
        await q.edit_message_text("🧾 Сегодня занятий нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="ha:menu")]]))
    else:
        await q.edit_message_text(
            f"🧾 Посещаемость • {day.strftime('%d.%m')}\n\nВыбери занятие:",
            reply_markup=_attendance_picker_markup(uid, day),
        )
    raise ApplicationHandlerStop


def _attendance_choice_markup(prefix, slot_id, who_id, compact):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Был(а)", callback_data=f"ha:set:{prefix}:{slot_id}:{who_id}:{compact}:present"),
            InlineKeyboardButton("❌ Не был(а)", callback_data=f"ha:set:{prefix}:{slot_id}:{who_id}:{compact}:absent"),
        ],
        [InlineKeyboardButton("↩️ Отмена урока", callback_data=f"ha:set:{prefix}:{slot_id}:{who_id}:{compact}:cancelled")],
        [InlineKeyboardButton("⬅️ К занятиям", callback_data="ha:attendance")],
    ])


async def attendance_individual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        _, _, slot_text, sid_text, compact = q.data.split(":", 4)
        slot_id, sid = int(slot_text), int(sid_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        raise ApplicationHandlerStop
    student = schedule.get_student(uid, sid)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop
    status = _attendance_status(uid, "individual", slot_id, day, student_id=sid)
    text = f"👤 {student['name']} • {day.strftime('%d.%m')}\n\nТекущий статус: {_status_icon(status)} {status or 'не отмечен'}"
    await q.edit_message_text(text, reply_markup=_attendance_choice_markup("i", slot_id, sid, compact))
    raise ApplicationHandlerStop


async def attendance_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        _, _, slot_text, gid_text, compact = q.data.split(":", 4)
        slot_id, gid = int(slot_text), int(gid_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        raise ApplicationHandlerStop
    group = groups.get_group(uid, gid)
    members = student_reminders._members(uid, gid)
    if not group:
        await q.edit_message_text("Группа не найдена.")
        raise ApplicationHandlerStop
    if not members:
        await q.edit_message_text(
            f"👥 {group['name']}\n\nСостав группы пока не добавлен. Добавь учеников через «🔔 Напоминания» → привязка учеников — этот же список используется для посещаемости.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К занятиям", callback_data="ha:attendance")]]),
        )
        raise ApplicationHandlerStop
    rows = []
    for m in members:
        status = _attendance_status(uid, "group", slot_id, day, person_id=int(m["id"]))
        rows.append([InlineKeyboardButton(f"{_status_icon(status)} {m['name']}", callback_data=f"ha:gperson:{slot_id}:{m['id']}:{compact}")])
    rows.append([InlineKeyboardButton("⬅️ К занятиям", callback_data="ha:attendance")])
    await q.edit_message_text(f"👥 {group['name']} • {day.strftime('%d.%m')}\n\nНажми на ученика:", reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop


async def attendance_group_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        _, _, slot_text, pid_text, compact = q.data.split(":", 4)
        slot_id, pid = int(slot_text), int(pid_text)
    except Exception:
        raise ApplicationHandlerStop
    with base.db() as conn:
        person = conn.execute("SELECT id,name FROM student_reminder_people WHERE id=? AND teacher_id=? AND active=1", (pid, uid)).fetchone()
    if not person:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        f"👤 {person['name']}\n\nОтметь посещаемость:",
        reply_markup=_attendance_choice_markup("g", slot_id, pid, compact),
    )
    raise ApplicationHandlerStop


async def attendance_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        _, _, prefix, slot_text, who_text, compact, status = q.data.split(":", 6)
        slot_id, who_id = int(slot_text), int(who_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        raise ApplicationHandlerStop
    if status not in {"present", "absent", "cancelled"}:
        raise ApplicationHandlerStop
    if prefix == "i":
        student = schedule.get_student(uid, who_id)
        if not student:
            raise ApplicationHandlerStop
        _save_attendance(uid, "individual", slot_id, day, student["name"], status, student_id=who_id)
        await q.answer("Посещаемость сохранена", show_alert=False)
        await q.edit_message_text(
            f"👤 {student['name']} • {day.strftime('%d.%m')}\n\n{_status_icon(status)} Статус сохранён.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К занятиям", callback_data="ha:attendance")]]),
        )
    else:
        with base.db() as conn:
            person = conn.execute("SELECT id,name,group_id FROM student_reminder_people WHERE id=? AND teacher_id=? AND active=1", (who_id, uid)).fetchone()
        if not person:
            raise ApplicationHandlerStop
        _save_attendance(uid, "group", slot_id, day, person["name"], status, person_id=who_id)
        await q.edit_message_text(
            f"👤 {person['name']} • {day.strftime('%d.%m')}\n\n{_status_icon(status)} Статус сохранён.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К занятиям", callback_data="ha:attendance")]]),
        )
    raise ApplicationHandlerStop


async def homework_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "📝 Выдать ДЗ\n\nКому?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Ученику", callback_data="ha:hw:pick:i")],
            [InlineKeyboardButton("👥 Группе", callback_data="ha:hw:pick:g")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="ha:menu")],
        ]),
    )
    raise ApplicationHandlerStop


async def homework_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    kind = q.data.rsplit(":", 1)[1]
    if kind == "i":
        people = base.list_students(uid)
        rows = [[InlineKeyboardButton(r["name"], callback_data=f"ha:hw:target:i:{r['id']}")] for r in people[:50]]
        title = "Выбери ученика:"
    else:
        people = groups.groups(uid)
        rows = [[InlineKeyboardButton(r["name"], callback_data=f"ha:hw:target:g:{r['id']}")] for r in people[:50]]
        title = "Выбери группу:"
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="ha:hw:new")])
    await q.edit_message_text(title if people else "Пока никого нет.", reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop


async def homework_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    parts = q.data.split(":")
    kind, target_id = parts[3], int(parts[4])
    if kind == "i":
        target = schedule.get_student(uid, target_id)
    else:
        target = groups.get_group(uid, target_id)
    if not target:
        await q.edit_message_text("Не удалось найти ученика или группу.")
        return ConversationHandler.END
    context.user_data["ha_hw"] = {"kind": kind, "target_id": target_id, "target_name": target["name"]}
    await q.edit_message_text(f"📝 ДЗ для: {target['name']}\n\nНапиши текст домашнего задания одним сообщением.")
    return HW_TEXT


async def homework_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get("ha_hw")
    if not data:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text("Напиши текст задания чуть подробнее.")
        return HW_TEXT
    data["text"] = text[:3000]
    await update.message.reply_text(
        "Когда дедлайн?\n\nНапиши «завтра», «через 3 дня» или дату, например 20.09.",
    )
    return HW_DUE


def _parse_due(uid, text):
    today_local = datetime.now(schedule.tz(uid)).date()
    value = (text or "").strip().lower().replace("ё", "е")
    if value == "завтра":
        return today_local + timedelta(days=1)
    m = re.search(r"через\s+(\d{1,2})\s+д", value)
    if m:
        return today_local + timedelta(days=int(m.group(1)))
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(value, fmt).date()
            if fmt == "%d.%m":
                d = d.replace(year=today_local.year)
                if d < today_local:
                    d = d.replace(year=today_local.year + 1)
            return d
        except Exception:
            pass
    return None


def _linked_individual(uid, sid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name,telegram_user_id FROM student_reminder_people WHERE teacher_id=? AND kind='individual' AND student_id=? AND active=1",
            (int(uid), int(sid)),
        ).fetchone()


async def homework_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    data = context.user_data.get("ha_hw")
    if not data:
        return ConversationHandler.END
    due = _parse_due(uid, update.message.text)
    if not due:
        await update.message.reply_text("Не поняла дату. Напиши, например: завтра, через 3 дня или 20.09.")
        return HW_DUE
    if due < datetime.now(schedule.tz(uid)).date():
        await update.message.reply_text("Дедлайн уже прошёл. Укажи будущую дату.")
        return HW_DUE

    now = datetime.now(schedule.tz(uid)).isoformat()
    with base.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO teacher_homework(
                teacher_telegram_user_id,target_kind,student_id,group_id,target_name,
                homework_text,due_date,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                "individual" if data["kind"] == "i" else "group",
                data["target_id"] if data["kind"] == "i" else None,
                data["target_id"] if data["kind"] == "g" else None,
                data["target_name"], data["text"], due.isoformat(), now,
            ),
        )
        homework_id = int(cur.lastrowid)
        recipients = []
        if data["kind"] == "i":
            student = schedule.get_student(uid, data["target_id"])
            person = _linked_individual(uid, data["target_id"])
            if student:
                recipients = [{
                    "student_id": data["target_id"],
                    "person_id": int(person["id"]) if person else None,
                    "name": student["name"],
                    "telegram_user_id": int(person["telegram_user_id"]) if person and person["telegram_user_id"] else None,
                }]
        else:
            recipients = [{
                "student_id": None,
                "person_id": int(m["id"]),
                "name": m["name"],
                "telegram_user_id": int(m["telegram_user_id"]) if m["telegram_user_id"] else None,
            } for m in student_reminders._members(uid, data["target_id"])]

        recipient_ids = []
        for r in recipients:
            rc = conn.execute(
                """
                INSERT INTO teacher_homework_recipients(
                    homework_id,teacher_telegram_user_id,student_id,person_id,person_name,telegram_user_id
                ) VALUES(?,?,?,?,?,?)
                """,
                (homework_id, uid, r["student_id"], r["person_id"], r["name"], r["telegram_user_id"]),
            )
            recipient_ids.append((int(rc.lastrowid), r))
        conn.commit()

    delivered = 0
    for recipient_id, r in recipient_ids:
        if not r["telegram_user_id"]:
            continue
        try:
            await context.bot.send_message(
                chat_id=r["telegram_user_id"],
                text=(
                    f"📝 Новое домашнее задание\n\n"
                    f"{data['text']}\n\n"
                    f"⏰ Сдать до {due.strftime('%d.%m.%Y')}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Я сделал(а)", callback_data=f"ha:hwdone:{recipient_id}")
                ]]),
            )
            delivered += 1
        except Exception:
            pass

    context.user_data.pop("ha_hw", None)
    note = f"\n📨 В Telegram доставлено: {delivered}/{len(recipient_ids)}" if recipient_ids else "\n⚠️ В группе пока нет добавленных участников, но ДЗ сохранено."
    await update.message.reply_text(
        f"✅ ДЗ сохранено\n\n{data['target_name']}\n⏰ До {due.strftime('%d.%m.%Y')}{note}",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def student_homework_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        recipient_id = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT r.*,h.homework_text,h.target_name,h.due_date
            FROM teacher_homework_recipients r
            JOIN teacher_homework h ON h.id=r.homework_id
            WHERE r.id=?
            """,
            (recipient_id,),
        ).fetchone()
        if not row or not row["telegram_user_id"] or int(row["telegram_user_id"]) != int(q.from_user.id):
            await q.answer("Эта кнопка относится к другому ученику.", show_alert=True)
            raise ApplicationHandlerStop
        if row["status"] != "done":
            conn.execute(
                "UPDATE teacher_homework_recipients SET status='done',completed_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), recipient_id),
            )
            conn.commit()
    await q.edit_message_text("✅ Готово! Я отметила домашнее задание как выполненное.")
    try:
        await context.bot.send_message(
            chat_id=int(row["teacher_telegram_user_id"]),
            text=f"✅ ДЗ выполнено: {row['person_name']}\n{row['homework_text'][:500]}",
        )
    except Exception:
        pass
    raise ApplicationHandlerStop


def _active_homework(uid):
    today_local = datetime.now(schedule.tz(uid)).date().isoformat()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT h.*,
                   COUNT(r.id) AS recipients,
                   SUM(CASE WHEN r.status='done' THEN 1 ELSE 0 END) AS done_count
            FROM teacher_homework h
            LEFT JOIN teacher_homework_recipients r ON r.homework_id=h.id
            WHERE h.teacher_telegram_user_id=? AND h.active=1
            GROUP BY h.id
            ORDER BY h.due_date,h.id
            """,
            (int(uid),),
        ).fetchall()


async def homework_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    rows = _active_homework(uid)
    buttons = []
    if not rows:
        text = "📚 Активных домашних заданий нет."
    else:
        lines = ["📚 Активные ДЗ"]
        for h in rows[:30]:
            due = date.fromisoformat(h["due_date"])
            recipients = int(h["recipients"] or 0)
            done = int(h["done_count"] or 0)
            debt = max(0, recipients - done)
            marker = "🔴" if due < datetime.now(schedule.tz(uid)).date() and debt else "🟢" if recipients and debt == 0 else "🟡"
            lines.append(f"\n{marker} {h['target_name']} • до {due.strftime('%d.%m')} • выполнено {done}/{recipients}")
            lines.append(str(h["homework_text"])[:120])
            buttons.append([InlineKeyboardButton(f"{marker} {h['target_name']} • {due.strftime('%d.%m')}", callback_data=f"ha:hw:view:{h['id']}")])
        text = "\n".join(lines)
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="ha:menu")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


async def homework_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    hid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        h = conn.execute("SELECT * FROM teacher_homework WHERE id=? AND teacher_telegram_user_id=?", (hid, uid)).fetchone()
        recipients = conn.execute("SELECT * FROM teacher_homework_recipients WHERE homework_id=? ORDER BY lower(person_name)", (hid,)).fetchall()
    if not h:
        await q.edit_message_text("ДЗ не найдено.")
        raise ApplicationHandlerStop
    lines = [f"📝 {h['target_name']}", f"⏰ До {date.fromisoformat(h['due_date']).strftime('%d.%m.%Y')}", "", h["homework_text"]]
    if recipients:
        lines.append("\nКто выполнил:")
        for r in recipients:
            lines.append(f"{'✅' if r['status']=='done' else '▫️'} {r['person_name']}")
    else:
        lines.append("\nУчастники не привязаны.")
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Закрыть ДЗ", callback_data=f"ha:hw:close:{hid}")],
        [InlineKeyboardButton("⬅️ К активным ДЗ", callback_data="ha:hw:list")],
    ]))
    raise ApplicationHandlerStop


async def homework_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    hid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        conn.execute("UPDATE teacher_homework SET active=0 WHERE id=? AND teacher_telegram_user_id=?", (hid, uid))
        conn.commit()
    await q.edit_message_text("✅ ДЗ закрыто и убрано из активных.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К разделу", callback_data="ha:menu")]]))
    raise ApplicationHandlerStop


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    since = (datetime.now(schedule.tz(uid)).date() - timedelta(days=30)).isoformat()
    with base.db() as conn:
        att = conn.execute(
            """
            SELECT status,COUNT(*) AS n FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND lesson_date>=?
            GROUP BY status
            """,
            (uid, since),
        ).fetchall()
        hw = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done
            FROM teacher_homework_recipients
            WHERE teacher_telegram_user_id=?
            """,
            (uid,),
        ).fetchone()
    counts = {r["status"]: int(r["n"]) for r in att}
    total_hw = int(hw["total"] or 0) if hw else 0
    done_hw = int(hw["done"] or 0) if hw else 0
    text = (
        "📊 Статистика • последние 30 дней\n\n"
        f"✅ Были: {counts.get('present',0)}\n"
        f"❌ Пропуски: {counts.get('absent',0)}\n"
        f"↩️ Отмены: {counts.get('cancelled',0)}\n\n"
        f"📝 ДЗ выполнено: {done_hw}/{total_hw}"
    )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="ha:menu")]]))
    raise ApplicationHandlerStop


def install(app):
    ensure_tables()
    base.MAIN_KB = _main_keyboard()

    homework_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(homework_target, pattern=r"^ha:hw:target:[ig]:\d+$")],
        states={
            HW_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, homework_text)],
            HW_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, homework_due)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(homework_conv, group=-18)
    app.add_handler(MessageHandler(filters.Regex(r"^📚 ДЗ и посещаемость$"), main_menu), group=-17)
    app.add_handler(CallbackQueryHandler(callback_menu, pattern=r"^ha:menu$"), group=-17)
    app.add_handler(CallbackQueryHandler(attendance_today, pattern=r"^ha:attendance$"), group=-17)
    app.add_handler(CallbackQueryHandler(attendance_individual, pattern=r"^ha:atti:\d+:\d+:\d{8}$"), group=-17)
    app.add_handler(CallbackQueryHandler(attendance_group, pattern=r"^ha:attg:\d+:\d+:\d{8}$"), group=-17)
    app.add_handler(CallbackQueryHandler(attendance_group_person, pattern=r"^ha:gperson:\d+:\d+:\d{8}$"), group=-17)
    app.add_handler(CallbackQueryHandler(attendance_set, pattern=r"^ha:set:[ig]:\d+:\d+:\d{8}:(?:present|absent|cancelled)$"), group=-17)
    app.add_handler(CallbackQueryHandler(homework_new, pattern=r"^ha:hw:new$"), group=-17)
    app.add_handler(CallbackQueryHandler(homework_picker, pattern=r"^ha:hw:pick:[ig]$"), group=-17)
    app.add_handler(CallbackQueryHandler(homework_list, pattern=r"^ha:hw:list$"), group=-17)
    app.add_handler(CallbackQueryHandler(homework_view, pattern=r"^ha:hw:view:\d+$"), group=-17)
    app.add_handler(CallbackQueryHandler(homework_close, pattern=r"^ha:hw:close:\d+$"), group=-17)
    app.add_handler(CallbackQueryHandler(student_homework_done, pattern=r"^ha:hwdone:\d+$"), group=-17)
    app.add_handler(CallbackQueryHandler(stats, pattern=r"^ha:stats$"), group=-17)
    print("PREPODMIN homework+attendance ready: today attendance + homework + student completion + stats", flush=True)
    return app
