"""Homework + attendance for PREPODMIN.

Teacher-facing flows:
- attendance for actual lesson occurrences, including moved lessons
- homework for individual students or groups
- per-student homework status and overdue view
- delivery to linked students + one-tap completion
"""
from datetime import date, datetime, timedelta
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_today as today
import teacher_product_student_reminders as student_reminders
import teacher_product_student_messaging as messaging

HW_KIND, HW_TARGET, HW_TEXT, HW_DUE = range(610, 614)


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
                subject_kind TEXT NOT NULL CHECK(subject_kind IN ('individual','group_member')),
                subject_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present','absent')),
                updated_at TEXT NOT NULL,
                UNIQUE(
                    teacher_telegram_user_id, lesson_kind, schedule_slot_id,
                    lesson_date, subject_kind, subject_id
                )
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_attendance_day
            ON teacher_attendance(teacher_telegram_user_id, lesson_date);

            CREATE TABLE IF NOT EXISTS teacher_homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                target_kind TEXT NOT NULL CHECK(target_kind IN ('individual','group')),
                target_id INTEGER NOT NULL,
                homework_text TEXT NOT NULL,
                due_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_teacher_due
            ON teacher_homework(teacher_telegram_user_id, active, due_date);

            CREATE TABLE IF NOT EXISTS teacher_homework_status (
                assignment_id INTEGER NOT NULL,
                subject_kind TEXT NOT NULL CHECK(subject_kind IN ('individual','group_member')),
                subject_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
                done_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(assignment_id, subject_kind, subject_id)
            );

            CREATE TABLE IF NOT EXISTS teacher_homework_reminder_sent (
                assignment_id INTEGER NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                reminder_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(assignment_id, subject_kind, subject_id, reminder_key)
            );
            """
        )
        conn.commit()


def _main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["➕ Быстрая задача"],
            ["📍 Сегодня", "🌅 Завтра"],
            ["📚 Домашнее", "✅ Посещаемость"],
            ["🗓 Мои слоты", "✅ Задачи"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )


def _events(uid, day):
    rows = today._individual_today(uid, day) + today._group_today(uid, day)
    rows.sort(key=lambda e: (e["time"], e["kind"], e["name"].lower()))
    return rows


def _members(uid, gid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT id,name,telegram_user_id
            FROM student_reminder_people
            WHERE teacher_id=? AND kind='group' AND group_id=? AND active=1
            ORDER BY lower(name)
            """,
            (int(uid), int(gid)),
        ).fetchall()


def _attendance_status(uid, kind, slot_id, lesson_date, subject_kind, subject_id):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT status FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND lesson_kind=? AND schedule_slot_id=?
              AND lesson_date=? AND subject_kind=? AND subject_id=?
            """,
            (
                int(uid), kind, int(slot_id), lesson_date.isoformat(),
                subject_kind, int(subject_id),
            ),
        ).fetchone()
    return row["status"] if row else None


def _set_attendance(uid, kind, slot_id, lesson_date, subject_kind, subject_id, status):
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO teacher_attendance(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                subject_kind,subject_id,status,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                subject_kind,subject_id
            ) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at
            """,
            (
                int(uid), kind, int(slot_id), lesson_date.isoformat(),
                subject_kind, int(subject_id), status, now,
            ),
        )
        conn.commit()


def _status_icon(status):
    return "✅" if status == "present" else "❌" if status == "absent" else "▫️"


async def _safe_edit(q, text, reply_markup=None):
    try:
        await q.edit_message_text(text, reply_markup=reply_markup)
        return True
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return False
        raise


def _event_from_key(uid, kind, slot_id, day):
    for event in _events(uid, day):
        if event["kind"] == kind and int(event["slot_id"]) == int(slot_id):
            return event
    return None


def _attendance_day_text(uid, day):
    events = _events(uid, day)
    lines = [f"✅ Посещаемость • {day.strftime('%d.%m.%Y')}"]
    if not events:
        lines += ["", "На эту дату занятий нет."]
        return "\n".join(lines)

    lines += ["", "Нажми на занятие и отметь, кто был."]
    for e in events:
        moved = " ↪️" if e.get("moved") else ""
        if e["kind"] == "individual":
            status = _attendance_status(
                uid, "individual", e["slot_id"], day, "individual", e["student_id"]
            )
            lines.append(f"{_status_icon(status)} {e['time']} • 👤 {e['name']}{moved}")
        else:
            members = _members(uid, e["group_id"])
            marked = 0
            present = 0
            absent = 0
            for m in members:
                st = _attendance_status(uid, "group", e["slot_id"], day, "group_member", m["id"])
                if st:
                    marked += 1
                    present += int(st == "present")
                    absent += int(st == "absent")
            if not members:
                tail = " • участников нет"
            elif marked == 0:
                tail = " • не отмечено"
            else:
                tail = f" • ✅ {present} / ❌ {absent} / ▫️ {len(members)-marked}"
            lines.append(f"👥 {e['time']} • {e['name']}{moved}{tail}")
    return "\n".join(lines)


def _attendance_day_markup(uid, day):
    buttons = []
    for e in _events(uid, day):
        icon = "👤" if e["kind"] == "individual" else "👥"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {e['time']} • {e['name']}",
                callback_data=f"edu:att:event:{e['kind']}:{e['slot_id']}:{day.strftime('%Y%m%d')}",
            )
        ])
    local_today = datetime.now(schedule.tz(uid)).date()
    yesterday = local_today - timedelta(days=1)
    buttons += [
        [
            InlineKeyboardButton("Сегодня", callback_data=f"edu:att:day:{local_today.strftime('%Y%m%d')}"),
            InlineKeyboardButton("Вчера", callback_data=f"edu:att:day:{yesterday.strftime('%Y%m%d')}"),
        ],
        [InlineKeyboardButton("📊 За 30 дней", callback_data="edu:att:stats")],
    ]
    return InlineKeyboardMarkup(buttons)


async def attendance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    day = datetime.now(schedule.tz(uid)).date()
    await update.message.reply_text(
        _attendance_day_text(uid, day),
        reply_markup=_attendance_day_markup(uid, day),
    )
    raise ApplicationHandlerStop


async def attendance_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    try:
        day = datetime.strptime(q.data.rsplit(":", 1)[1], "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось определить дату.", show_alert=True)
        raise ApplicationHandlerStop
    await _safe_edit(
        q,
        _attendance_day_text(uid, day),
        reply_markup=_attendance_day_markup(uid, day),
    )
    raise ApplicationHandlerStop


def _attendance_event_view(uid, event, day):
    moved = "\n↪️ Занятие было перенесено." if event.get("moved") else ""
    lines = [
        f"✅ Посещаемость • {day.strftime('%d.%m')}",
        "",
        f"{'👤' if event['kind']=='individual' else '👥'} {event['time']} • {event['name']}{moved}",
        "",
    ]
    buttons = []
    compact = day.strftime("%Y%m%d")
    if event["kind"] == "individual":
        st = _attendance_status(
            uid, "individual", event["slot_id"], day, "individual", event["student_id"]
        )
        lines.append(f"Статус: {_status_icon(st)} " + (
            "был(а)" if st == "present" else "не был(а)" if st == "absent" else "не отмечено"
        ))
        buttons.append([
            InlineKeyboardButton(
                "✅ Был(а)",
                callback_data=f"edu:att:set:individual:{event['slot_id']}:{compact}:individual:{event['student_id']}:present",
            ),
            InlineKeyboardButton(
                "❌ Не был(а)",
                callback_data=f"edu:att:set:individual:{event['slot_id']}:{compact}:individual:{event['student_id']}:absent",
            ),
        ])
        buttons.append([
            InlineKeyboardButton(
                "📚 Выдать ДЗ",
                callback_data=f"edu:hwquick:individual:{event['student_id']}",
            )
        ])
    else:
        members = _members(uid, event["group_id"])
        if not members:
            lines.append(
                "У группы пока нет участников.\n"
                "Добавь их через «🔔 Напоминания» → «Привязать учеников / ответы»."
            )
        else:
            lines.append("Сначала нажми «✅ Все были», затем отметь отсутствующих.")
            buttons.append([
                InlineKeyboardButton(
                    "✅ Все были",
                    callback_data=f"edu:att:all:{event['slot_id']}:{compact}:{event['group_id']}",
                )
            ])
            for m in members[:50]:
                st = _attendance_status(
                    uid, "group", event["slot_id"], day, "group_member", m["id"]
                )
                buttons.append([
                    InlineKeyboardButton(
                        f"{_status_icon(st)} {m['name']}",
                        callback_data=f"edu:att:toggle:{event['slot_id']}:{compact}:{m['id']}",
                    )
                ])
            buttons.append([
                InlineKeyboardButton(
                    "📚 Выдать ДЗ группе",
                    callback_data=f"edu:hwquick:group:{event['group_id']}",
                )
            ])
    buttons.append([
        InlineKeyboardButton("← К занятиям", callback_data=f"edu:att:day:{compact}")
    ])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def attendance_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    try:
        _, _, _, kind, slot_text, compact = q.data.split(":")
        slot_id = int(slot_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось определить занятие.", show_alert=True)
        raise ApplicationHandlerStop
    event = _event_from_key(uid, kind, slot_id, day)
    if not event:
        await q.edit_message_text("Занятие не найдено. Возможно, расписание уже изменилось.")
        raise ApplicationHandlerStop
    text, kb = _attendance_event_view(uid, event, day)
    await _safe_edit(q, text, reply_markup=kb)
    raise ApplicationHandlerStop


async def attendance_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        await q.answer()
        raise ApplicationHandlerStop
    try:
        _, _, _, kind, slot_text, compact, subject_kind, subject_text, status = q.data.split(":")
        slot_id = int(slot_text)
        subject_id = int(subject_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось сохранить отметку.", show_alert=True)
        raise ApplicationHandlerStop
    if status not in {"present", "absent"}:
        await q.answer()
        raise ApplicationHandlerStop
    event = _event_from_key(uid, kind, slot_id, day)
    if not event:
        await q.answer("Занятие больше не найдено.", show_alert=True)
        raise ApplicationHandlerStop
    current = _attendance_status(uid, kind, slot_id, day, subject_kind, subject_id)
    if current == status:
        await q.answer("Уже отмечено ✅" if status == "present" else "Уже отмечен пропуск ❌")
        raise ApplicationHandlerStop
    _set_attendance(uid, kind, slot_id, day, subject_kind, subject_id, status)
    await q.answer("Сохранено")
    text, kb = _attendance_event_view(uid, event, day)
    await _safe_edit(q, text, reply_markup=kb)
    raise ApplicationHandlerStop


async def attendance_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        await q.answer()
        raise ApplicationHandlerStop
    try:
        _, _, _, slot_text, compact, gid_text = q.data.split(":")
        slot_id = int(slot_text)
        gid = int(gid_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось сохранить посещаемость.", show_alert=True)
        raise ApplicationHandlerStop
    event = _event_from_key(uid, "group", slot_id, day)
    if not event or int(event["group_id"]) != gid:
        await q.answer("Занятие больше не найдено.", show_alert=True)
        raise ApplicationHandlerStop
    members = _members(uid, gid)
    changed = False
    for m in members:
        if _attendance_status(uid, "group", slot_id, day, "group_member", m["id"]) != "present":
            _set_attendance(uid, "group", slot_id, day, "group_member", m["id"], "present")
            changed = True
    if not changed:
        await q.answer("Все уже отмечены ✅")
        raise ApplicationHandlerStop
    await q.answer("Все отмечены ✅")
    text, kb = _attendance_event_view(uid, event, day)
    await _safe_edit(q, text, reply_markup=kb)
    raise ApplicationHandlerStop


async def attendance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    try:
        _, _, _, slot_text, compact, pid_text = q.data.split(":")
        slot_id = int(slot_text)
        pid = int(pid_text)
        day = datetime.strptime(compact, "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось сохранить посещаемость.", show_alert=True)
        raise ApplicationHandlerStop
    event = _event_from_key(uid, "group", slot_id, day)
    if not event:
        await q.answer("Занятие больше не найдено.", show_alert=True)
        raise ApplicationHandlerStop
    valid_ids = {int(m["id"]) for m in _members(uid, event["group_id"])}
    if pid not in valid_ids:
        await q.answer("Участник группы не найден.", show_alert=True)
        raise ApplicationHandlerStop
    current = _attendance_status(uid, "group", slot_id, day, "group_member", pid)
    new_status = "absent" if current == "present" else "present"
    _set_attendance(uid, "group", slot_id, day, "group_member", pid, new_status)
    text, kb = _attendance_event_view(uid, event, day)
    await _safe_edit(q, text, reply_markup=kb)
    raise ApplicationHandlerStop


async def attendance_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    today_local = datetime.now(schedule.tz(uid)).date()
    since = today_local - timedelta(days=29)
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT status,COUNT(*) AS c
            FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND lesson_date>=? AND lesson_date<=?
            GROUP BY status
            """,
            (uid, since.isoformat(), today_local.isoformat()),
        ).fetchall()
    counts = {r["status"]: int(r["c"]) for r in rows}
    present = counts.get("present", 0)
    absent = counts.get("absent", 0)
    total = present + absent
    pct = round(present * 100 / total) if total else 0
    text = (
        f"📊 Посещаемость за 30 дней\n\n"
        f"✅ Присутствовали: {present}\n"
        f"❌ Пропуски: {absent}\n"
        f"Всего отметок: {total}\n"
        f"Посещаемость: {pct}%"
    )
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "← Сегодня",
                callback_data=f"edu:att:day:{today_local.strftime('%Y%m%d')}",
            )
        ]]),
    )
    raise ApplicationHandlerStop


def _parse_due(text, uid):
    raw = str(text or "").strip().lower().replace("ё", "е")
    today_local = datetime.now(schedule.tz(uid)).date()
    if raw == "сегодня":
        return today_local
    if raw == "завтра":
        return today_local + timedelta(days=1)
    m = re.fullmatch(r"через\s+(\d{1,2})\s+дн(?:я|ей|ь)?", raw)
    if m:
        return today_local + timedelta(days=int(m.group(1)))
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            if fmt == "%d.%m":
                parsed = parsed.replace(year=today_local.year)
                if parsed < today_local - timedelta(days=1):
                    parsed = parsed.replace(year=today_local.year + 1)
            return parsed
        except ValueError:
            pass
    return None


def _target_name(uid, kind, target_id):
    if kind == "individual":
        row = schedule.get_student(uid, target_id)
    else:
        row = groups.get_group(uid, target_id)
    return row["name"] if row else None


def _assignment(aid, uid=None):
    ensure_tables()
    with base.db() as conn:
        if uid is None:
            return conn.execute("SELECT * FROM teacher_homework WHERE id=?", (int(aid),)).fetchone()
        return conn.execute(
            "SELECT * FROM teacher_homework WHERE id=? AND teacher_telegram_user_id=?",
            (int(aid), int(uid)),
        ).fetchone()


def _sync_statuses(assignment):
    if not assignment:
        return
    now = datetime.utcnow().isoformat()
    uid = int(assignment["teacher_telegram_user_id"])
    with base.db() as conn:
        if assignment["target_kind"] == "individual":
            if schedule.get_student(uid, assignment["target_id"]):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO teacher_homework_status(
                        assignment_id,subject_kind,subject_id,status,updated_at
                    ) VALUES(?,'individual',?,'pending',?)
                    """,
                    (int(assignment["id"]), int(assignment["target_id"]), now),
                )
        else:
            for m in _members(uid, assignment["target_id"]):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO teacher_homework_status(
                        assignment_id,subject_kind,subject_id,status,updated_at
                    ) VALUES(?,'group_member',?,'pending',?)
                    """,
                    (int(assignment["id"]), int(m["id"]), now),
                )
        conn.commit()


def _status_rows(assignment):
    _sync_statuses(assignment)
    uid = int(assignment["teacher_telegram_user_id"])
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT subject_kind,subject_id,status,done_at
            FROM teacher_homework_status
            WHERE assignment_id=?
            ORDER BY subject_kind,subject_id
            """,
            (int(assignment["id"]),),
        ).fetchall()
        out = []
        for r in rows:
            if r["subject_kind"] == "individual":
                person = conn.execute(
                    "SELECT name FROM students WHERE id=? AND teacher_telegram_user_id=?",
                    (int(r["subject_id"]), uid),
                ).fetchone()
            else:
                person = conn.execute(
                    "SELECT name FROM student_reminder_people WHERE id=? AND teacher_id=?",
                    (int(r["subject_id"]), uid),
                ).fetchone()
            if person:
                out.append({
                    "subject_kind": r["subject_kind"],
                    "subject_id": int(r["subject_id"]),
                    "status": r["status"],
                    "name": person["name"],
                })
    out.sort(key=lambda r: r["name"].lower())
    return out


def _subject_recipient(assignment, subject_kind, subject_id):
    uid = int(assignment["teacher_telegram_user_id"])
    with base.db() as conn:
        if subject_kind == "individual":
            return conn.execute(
                """
                SELECT telegram_user_id,name
                FROM student_reminder_people
                WHERE teacher_id=? AND kind='individual' AND student_id=?
                  AND active=1 AND telegram_user_id IS NOT NULL
                LIMIT 1
                """,
                (uid, int(subject_id)),
            ).fetchone()
        return conn.execute(
            """
            SELECT telegram_user_id,name
            FROM student_reminder_people
            WHERE teacher_id=? AND kind='group' AND id=?
              AND active=1 AND telegram_user_id IS NOT NULL
            LIMIT 1
            """,
            (uid, int(subject_id)),
        ).fetchone()


def _student_done_callback(aid, subject_kind, subject_id):
    code = "i" if subject_kind == "individual" else "g"
    return f"edu:hwsdone:{int(aid)}:{code}:{int(subject_id)}"


def _homework_student_text(assignment, prefix="📚 Новое домашнее задание"):
    return (
        f"{prefix}\n\n"
        f"{assignment['homework_text']}\n\n"
        f"⏰ Срок: {date.fromisoformat(assignment['due_date']).strftime('%d.%m')}"
    )


async def _send_assignment(context, assignment):
    sent = 0
    failed = 0
    total = 0
    for st in _status_rows(assignment):
        recipient = _subject_recipient(
            assignment, st["subject_kind"], st["subject_id"]
        )
        if not recipient:
            continue
        total += 1
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Я сделал(а)",
                callback_data=_student_done_callback(
                    assignment["id"], st["subject_kind"], st["subject_id"]
                ),
            )
        ]])
        result = await messaging.dispatch(
            context,
            int(assignment["teacher_telegram_user_id"]),
            int(recipient["telegram_user_id"]),
            _homework_student_text(assignment),
            recipient_name=recipient["name"],
            category="homework",
            source_key=(
                f"homework:new:{assignment['id']}:"
                f"{st['subject_kind']}:{st['subject_id']}"
            ),
            reply_markup=markup,
        )
        sent += int(result == "sent")
        failed += int(result == "failed")
        print(
            f"Homework delivery routed assignment={assignment['id']} "
            f"subject={st['subject_kind']}:{st['subject_id']} status={result}",
            flush=True,
        )
    return sent, failed, total


def _create_assignment(uid, kind, target_id, text, due):
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO teacher_homework(
                teacher_telegram_user_id,target_kind,target_id,homework_text,
                due_date,active,created_at
            ) VALUES(?,?,?,?,?,1,?)
            """,
            (int(uid), kind, int(target_id), text.strip(), due.isoformat(), now),
        )
        aid = int(cur.lastrowid)
        conn.commit()
    assignment = _assignment(aid, uid)
    _sync_statuses(assignment)
    return assignment


def _homework_menu_text(uid):
    today_local = datetime.now(schedule.tz(uid)).date()
    with base.db() as conn:
        assignments = conn.execute(
            """
            SELECT * FROM teacher_homework
            WHERE teacher_telegram_user_id=? AND active=1
            ORDER BY due_date,id DESC
            """,
            (int(uid),),
        ).fetchall()
    active = []
    debts = 0
    for a in assignments:
        statuses = _status_rows(a)
        pending = sum(1 for s in statuses if s["status"] == "pending")
        done = sum(1 for s in statuses if s["status"] == "done")
        if pending:
            active.append((a, pending, done))
            if date.fromisoformat(a["due_date"]) < today_local:
                debts += pending
    lines = ["📚 Домашнее"]
    if not active:
        lines += ["", "Активных домашних заданий нет."]
    else:
        lines += ["", f"Активных заданий: {len(active)} • просроченных работ: {debts}", ""]
        for a, pending, done in active[:10]:
            target = _target_name(uid, a["target_kind"], a["target_id"]) or "архив"
            overdue = " 🚨" if date.fromisoformat(a["due_date"]) < today_local and pending else ""
            lines.append(
                f"• до {date.fromisoformat(a['due_date']).strftime('%d.%m')} • "
                f"{target} • ✅ {done} / ⏳ {pending}{overdue}"
            )
    return "\n".join(lines), assignments


def _homework_menu_markup(uid):
    text, assignments = _homework_menu_text(uid)
    buttons = [[InlineKeyboardButton("➕ Выдать ДЗ", callback_data="edu:hw:add")]]
    shown = 0
    today_local = datetime.now(schedule.tz(uid)).date()
    debts = False
    for a in assignments:
        statuses = _status_rows(a)
        if not any(s["status"] == "pending" for s in statuses):
            continue
        target = _target_name(uid, a["target_kind"], a["target_id"]) or "архив"
        buttons.append([
            InlineKeyboardButton(
                f"📌 {date.fromisoformat(a['due_date']).strftime('%d.%m')} • {target}",
                callback_data=f"edu:hw:view:{a['id']}",
            )
        ])
        if date.fromisoformat(a["due_date"]) < today_local:
            debts = True
        shown += 1
        if shown >= 10:
            break
    if debts:
        buttons.append([InlineKeyboardButton("🚨 Показать долги", callback_data="edu:hw:debts")])
    return text, InlineKeyboardMarkup(buttons)


async def homework_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    text, kb = _homework_menu_markup(uid)
    await update.message.reply_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def homework_add_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not base.teacher(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text(
        "Кому выдать домашнее задание?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Ученику", callback_data="edu:hwk:individual")],
            [InlineKeyboardButton("👥 Группе", callback_data="edu:hwk:group")],
        ]),
    )
    return HW_KIND


async def homework_quick_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        return ConversationHandler.END
    try:
        _, _, kind, target_text = q.data.split(":")
        target_id = int(target_text)
    except Exception:
        await q.answer("Не удалось определить ученика или группу.", show_alert=True)
        return ConversationHandler.END
    name = _target_name(uid, kind, target_id)
    if not name:
        await q.answer("Ученик или группа не найдены.", show_alert=True)
        return ConversationHandler.END
    context.user_data["edu_hw_kind"] = kind
    context.user_data["edu_hw_target"] = target_id
    await q.edit_message_text(f"📚 ДЗ для {name}\n\nНапиши задание одним сообщением.")
    return HW_TEXT


async def homework_kind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    kind = q.data.rsplit(":", 1)[1]
    context.user_data["edu_hw_kind"] = kind
    if kind == "individual":
        rows = base.list_students(uid)
        buttons = [
            [InlineKeyboardButton(r["name"], callback_data=f"edu:hwt:individual:{r['id']}")]
            for r in rows[:60]
        ]
        title = "Выбери ученика:"
    else:
        rows = groups.groups(uid)
        buttons = [
            [InlineKeyboardButton(r["name"], callback_data=f"edu:hwt:group:{r['id']}")]
            for r in rows[:60]
        ]
        title = "Выбери группу:"
    if not buttons:
        await q.edit_message_text("Сначала добавь ученика или группу.")
        return ConversationHandler.END
    await q.edit_message_text(title, reply_markup=InlineKeyboardMarkup(buttons))
    return HW_TARGET


async def homework_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        _, _, kind, target_text = q.data.split(":")
        target_id = int(target_text)
    except Exception:
        return ConversationHandler.END
    name = _target_name(uid, kind, target_id)
    if not name:
        await q.edit_message_text("Ученик или группа не найдены.")
        return ConversationHandler.END
    context.user_data["edu_hw_kind"] = kind
    context.user_data["edu_hw_target"] = target_id
    await q.edit_message_text(f"📚 ДЗ для {name}\n\nНапиши задание одним сообщением.")
    return HW_TEXT


async def homework_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if len(text) < 2:
        await update.message.reply_text("Напиши текст домашнего задания.")
        return HW_TEXT
    context.user_data["edu_hw_text"] = text[:3500]
    await update.message.reply_text(
        "Когда срок сдачи?\n\n"
        "Можно написать: «завтра», «через 3 дня», «25.09» или «25.09.2026»."
    )
    return HW_DUE


async def homework_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    due = _parse_due(update.message.text, uid)
    kind = context.user_data.get("edu_hw_kind")
    target_id = context.user_data.get("edu_hw_target")
    hw_text = context.user_data.get("edu_hw_text")
    if not due:
        await update.message.reply_text(
            "Не поняла дату. Напиши, например: завтра, через 3 дня или 25.09."
        )
        return HW_DUE
    if not kind or not target_id or not hw_text or not _target_name(uid, kind, target_id):
        await update.message.reply_text("Не удалось сохранить ДЗ. Открой раздел «📚 Домашнее» и попробуй ещё раз.")
        return ConversationHandler.END
    assignment = _create_assignment(uid, kind, target_id, hw_text, due)
    sent, failed, total_linked = await _send_assignment(context, assignment)
    context.user_data.pop("edu_hw_kind", None)
    context.user_data.pop("edu_hw_target", None)
    context.user_data.pop("edu_hw_text", None)
    statuses = _status_rows(assignment)
    await update.message.reply_text(
        f"✅ Домашнее задание сохранено.\n\n"
        f"{_target_name(uid, kind, target_id)}\n"
        f"Срок: {due.strftime('%d.%m')}\n"
        f"Учитывается учеников: {len(statuses)}\n"
        f"{messaging.delivery_summary(uid, total_linked, sent, failed, singular=(kind == 'individual'))}\n\n"
        f"Если ученик ещё не привязан к ПРЕПАДМИН, ДЗ всё равно останется в твоём учёте.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


def _assignment_view(uid, aid):
    a = _assignment(aid, uid)
    if not a:
        return "Домашнее задание не найдено.", InlineKeyboardMarkup([])
    target = _target_name(uid, a["target_kind"], a["target_id"]) or "архив"
    due = date.fromisoformat(a["due_date"])
    statuses = _status_rows(a)
    lines = [
        f"📚 ДЗ • {target}",
        f"⏰ Срок: {due.strftime('%d.%m.%Y')}",
        "",
        a["homework_text"],
        "",
        "Статус:",
    ]
    buttons = []
    for st in statuses[:60]:
        icon = "✅" if st["status"] == "done" else "⏳"
        lines.append(f"{icon} {st['name']}")
        code = "i" if st["subject_kind"] == "individual" else "g"
        buttons.append([
            InlineKeyboardButton(
                f"{icon} {st['name']}",
                callback_data=f"edu:hwtoggle:{a['id']}:{code}:{st['subject_id']}",
            )
        ])
    if not statuses:
        lines.append("Участники пока не добавлены.")
    buttons += [
        [InlineKeyboardButton("🗄 Закрыть ДЗ", callback_data=f"edu:hw:archive:{a['id']}")],
        [InlineKeyboardButton("← К домашнему", callback_data="edu:hw:back")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def homework_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    aid = int(q.data.rsplit(":", 1)[1])
    text, kb = _assignment_view(uid, aid)
    await q.edit_message_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def homework_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    try:
        _, _, aid_text, code, sid_text = q.data.split(":")
        aid = int(aid_text)
        sid = int(sid_text)
        subject_kind = "individual" if code == "i" else "group_member"
    except Exception:
        raise ApplicationHandlerStop
    a = _assignment(aid, uid)
    if not a:
        raise ApplicationHandlerStop
    _sync_statuses(a)
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT status FROM teacher_homework_status
            WHERE assignment_id=? AND subject_kind=? AND subject_id=?
            """,
            (aid, subject_kind, sid),
        ).fetchone()
        if row:
            new = "pending" if row["status"] == "done" else "done"
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                UPDATE teacher_homework_status
                SET status=?,done_at=?,updated_at=?
                WHERE assignment_id=? AND subject_kind=? AND subject_id=?
                """,
                (new, now if new == "done" else None, now, aid, subject_kind, sid),
            )
            conn.commit()
    text, kb = _assignment_view(uid, aid)
    await q.edit_message_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def homework_student_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, _, aid_text, code, sid_text = q.data.split(":")
        aid = int(aid_text)
        sid = int(sid_text)
        subject_kind = "individual" if code == "i" else "group_member"
    except Exception:
        raise ApplicationHandlerStop
    a = _assignment(aid)
    if not a or not int(a["active"]):
        await q.answer("Это задание уже закрыто.", show_alert=True)
        raise ApplicationHandlerStop
    recipient = _subject_recipient(a, subject_kind, sid)
    if not recipient or int(recipient["telegram_user_id"]) != int(q.from_user.id):
        await q.answer("Это задание не привязано к твоему аккаунту.", show_alert=True)
        raise ApplicationHandlerStop
    _sync_statuses(a)
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            UPDATE teacher_homework_status
            SET status='done',done_at=?,updated_at=?
            WHERE assignment_id=? AND subject_kind=? AND subject_id=?
            """,
            (now, now, aid, subject_kind, sid),
        )
        conn.commit()
    await q.edit_message_text(
        _homework_student_text(a, prefix="✅ Домашнее отмечено выполненным") +
        "\n\nПреподаватель увидит отметку в ПРЕПАДМИН."
    )
    raise ApplicationHandlerStop


async def homework_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    aid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        conn.execute(
            "UPDATE teacher_homework SET active=0 WHERE id=? AND teacher_telegram_user_id=?",
            (aid, uid),
        )
        conn.commit()
    text, kb = _homework_menu_markup(uid)
    await q.edit_message_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def homework_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    text, kb = _homework_menu_markup(uid)
    await q.edit_message_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def homework_debts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    today_local = datetime.now(schedule.tz(uid)).date()
    with base.db() as conn:
        assignments = conn.execute(
            """
            SELECT * FROM teacher_homework
            WHERE teacher_telegram_user_id=? AND active=1 AND due_date<?
            ORDER BY due_date,id
            """,
            (uid, today_local.isoformat()),
        ).fetchall()
    lines = ["🚨 Долги по домашнему", ""]
    count = 0
    for a in assignments:
        for st in _status_rows(a):
            if st["status"] != "pending":
                continue
            count += 1
            target = _target_name(uid, a["target_kind"], a["target_id"]) or "архив"
            lines.append(
                f"• {st['name']} • {target} • срок {date.fromisoformat(a['due_date']).strftime('%d.%m')}"
            )
    if not count:
        lines.append("Просроченных работ нет 🎉")
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("← К домашнему", callback_data="edu:hw:back")
        ]]),
    )
    raise ApplicationHandlerStop


def _reminder_was_sent(aid, subject_kind, subject_id, key):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM teacher_homework_reminder_sent
            WHERE assignment_id=? AND subject_kind=? AND subject_id=? AND reminder_key=?
            """,
            (int(aid), subject_kind, int(subject_id), key),
        ).fetchone()
    return bool(row)


def _mark_reminder_sent(aid, subject_kind, subject_id, key):
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teacher_homework_reminder_sent(
                assignment_id,subject_kind,subject_id,reminder_key,sent_at
            ) VALUES(?,?,?,?,?)
            """,
            (int(aid), subject_kind, int(subject_id), key, datetime.utcnow().isoformat()),
        )
        conn.commit()


async def _deliver_homework_reminder(context, assignment, status_row, key, prefix):
    if status_row["status"] != "pending":
        return
    if _reminder_was_sent(
        assignment["id"], status_row["subject_kind"], status_row["subject_id"], key
    ):
        return
    recipient = _subject_recipient(
        assignment, status_row["subject_kind"], status_row["subject_id"]
    )
    if not recipient:
        return
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Я сделал(а)",
            callback_data=_student_done_callback(
                assignment["id"], status_row["subject_kind"], status_row["subject_id"]
            ),
        )
    ]])
    result = await messaging.dispatch(
        context,
        int(assignment["teacher_telegram_user_id"]),
        int(recipient["telegram_user_id"]),
        _homework_student_text(assignment, prefix=prefix),
        recipient_name=recipient["name"],
        category="homework_reminder",
        source_key=(
            f"homework:reminder:{assignment['id']}:"
            f"{status_row['subject_kind']}:{status_row['subject_id']}:{key}"
        ),
        reply_markup=markup,
    )
    if result != "failed":
        _mark_reminder_sent(
            assignment["id"], status_row["subject_kind"], status_row["subject_id"], key
        )
    print(
        f"Homework reminder routed assignment={assignment['id']} "
        f"subject={status_row['subject_kind']}:{status_row['subject_id']} "
        f"status={result}",
        flush=True,
    )


async def homework_reminder_tick(context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    with base.db() as conn:
        teachers = conn.execute(
            """
            SELECT telegram_user_id FROM teachers
            WHERE onboarding_completed_at IS NOT NULL
            """
        ).fetchall()
    for teacher in teachers:
        uid = int(teacher["telegram_user_id"])
        now = datetime.now(schedule.tz(uid))
        due_date = None
        prefix = None
        key_prefix = None
        if (now.hour, now.minute) >= (17, 55) and (now.hour, now.minute) < (18, 10):
            due_date = now.date() + timedelta(days=1)
            prefix = "🔔 Напоминание: ДЗ нужно сдать завтра"
            key_prefix = "tomorrow"
        elif (now.hour, now.minute) >= (11, 55) and (now.hour, now.minute) < (12, 10):
            due_date = now.date()
            prefix = "⏰ Напоминание: срок ДЗ сегодня"
            key_prefix = "today"
        else:
            continue
        with base.db() as conn:
            assignments = conn.execute(
                """
                SELECT * FROM teacher_homework
                WHERE teacher_telegram_user_id=? AND active=1 AND due_date=?
                """,
                (uid, due_date.isoformat()),
            ).fetchall()
        for a in assignments:
            key = f"{key_prefix}:{a['due_date']}"
            for st in _status_rows(a):
                await _deliver_homework_reminder(context, a, st, key, prefix)


def install(app):
    ensure_tables()
    base.MAIN_KB = _main_keyboard()

    homework_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(homework_add_begin, pattern=r"^edu:hw:add$"),
            CallbackQueryHandler(homework_quick_begin, pattern=r"^edu:hwquick:(?:individual|group):\d+$"),
        ],
        states={
            HW_KIND: [
                CallbackQueryHandler(homework_kind, pattern=r"^edu:hwk:(?:individual|group)$")
            ],
            HW_TARGET: [
                CallbackQueryHandler(homework_target, pattern=r"^edu:hwt:(?:individual|group):\d+$")
            ],
            HW_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, homework_text)
            ],
            HW_DUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, homework_due)
            ],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(homework_conversation, group=-18)

    app.add_handler(
        CallbackQueryHandler(homework_student_done, pattern=r"^edu:hwsdone:\d+:[ig]:\d+$"),
        group=-19,
    )
    app.add_handler(
        MessageHandler(filters.Regex(r"^📚 Домашнее$"), homework_menu),
        group=-17,
    )
    app.add_handler(
        MessageHandler(filters.Regex(r"^✅ Посещаемость$"), attendance_menu),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_day, pattern=r"^edu:att:day:\d{8}$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_event, pattern=r"^edu:att:event:(?:individual|group):\d+:\d{8}$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_set, pattern=r"^edu:att:set:(?:individual|group):\d+:\d{8}:(?:individual|group_member):\d+:(?:present|absent)$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_all, pattern=r"^edu:att:all:\d+:\d{8}:\d+$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_toggle, pattern=r"^edu:att:toggle:\d+:\d{8}:\d+$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(attendance_stats, pattern=r"^edu:att:stats$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(homework_view, pattern=r"^edu:hw:view:\d+$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(homework_toggle, pattern=r"^edu:hwtoggle:\d+:[ig]:\d+$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(homework_archive, pattern=r"^edu:hw:archive:\d+$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(homework_back, pattern=r"^edu:hw:back$"),
        group=-17,
    )
    app.add_handler(
        CallbackQueryHandler(homework_debts, pattern=r"^edu:hw:debts$"),
        group=-17,
    )

    if app.job_queue is not None:
        app.job_queue.run_repeating(
            homework_reminder_tick,
            interval=300,
            first=20,
            name="teacher_homework_reminders",
        )
    else:
        print("WARNING: JobQueue unavailable; homework reminders will not run", flush=True)

    print(
        "PREPODMIN learning flow ready: homework + attendance + student completion + debt reminders",
        flush=True,
    )
    return app
