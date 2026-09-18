"""Read-only reports, auto summaries and attention zone for PREPODMIN."""
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_student_reminders as student_reminders
import teacher_product_learning as learning
import teacher_product_payments as payments
import teacher_product_subscriptions as subscriptions
import teacher_product_cancellations as cancellations
import teacher_product_courses as courses


def ensure_tables():
    learning.ensure_tables()
    subscriptions.ensure_tables()
    cancellations.ensure_tables()
    courses.ensure_tables()
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_report_settings (
                teacher_telegram_user_id INTEGER PRIMARY KEY,
                weekly_enabled INTEGER NOT NULL DEFAULT 0,
                monthly_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teacher_report_delivery (
                teacher_telegram_user_id INTEGER NOT NULL,
                report_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id, report_key)
            );
            """
        )
        conn.commit()


def _today(uid):
    return datetime.now(schedule.tz(uid)).date()


def _range(uid, days=30):
    end = _today(uid)
    return end - timedelta(days=max(1, int(days)) - 1), end


def _pct(part, total):
    return "—" if not total else f"{round(100 * int(part) / int(total))}%"


def _attendance(uid, kind, subject_id, start, end):
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT status,COUNT(*) AS c
            FROM teacher_attendance
            WHERE teacher_telegram_user_id=? AND subject_kind=? AND subject_id=?
              AND lesson_date>=? AND lesson_date<=?
            GROUP BY status
            """,
            (int(uid), kind, int(subject_id), start.isoformat(), end.isoformat()),
        ).fetchall()
    out = {"present": 0, "absent": 0}
    for row in rows:
        if row["status"] in out:
            out[row["status"]] = int(row["c"] or 0)
    out["total"] = out["present"] + out["absent"]
    return out


def _homework(uid, kind, subject_id, start=None, end=None, overdue=False):
    where = ["h.teacher_telegram_user_id=?", "hs.subject_kind=?", "hs.subject_id=?"]
    params = [int(uid), kind, int(subject_id)]
    if start:
        where.append("h.due_date>=?")
        params.append(start.isoformat())
    if end:
        where.append("h.due_date<=?")
        params.append(end.isoformat())
    if overdue:
        where += ["h.active=1", "h.due_date<?", "hs.status='pending'"]
        params.append(_today(uid).isoformat())
    with base.db() as conn:
        rows = conn.execute(
            f"""
            SELECT hs.status,COUNT(*) AS c
            FROM teacher_homework_status hs
            JOIN teacher_homework h ON h.id=hs.assignment_id
            WHERE {' AND '.join(where)}
            GROUP BY hs.status
            """,
            tuple(params),
        ).fetchall()
    out = {"done": 0, "pending": 0}
    for row in rows:
        if row["status"] in out:
            out[row["status"]] = int(row["c"] or 0)
    out["total"] = out["done"] + out["pending"]
    return out


def _payment(uid, sid):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT payment_type,next_due_date,active,lessons_total,lessons_remaining
            FROM student_payment_plans
            WHERE teacher_telegram_user_id=? AND student_id=?
            """,
            (int(uid), int(sid)),
        ).fetchone()
    if not row or not int(row["active"] or 0):
        return "⚪ не настроено", False
    if row["payment_type"] == "package":
        total = int(row["lessons_total"] or 0)
        left = int(row["lessons_remaining"] or 0)
        return (
            ("🔴 абонемент закончился", True)
            if left <= 0 else
            (f"🎟 осталось {left}/{total} занятий", False)
        )
    try:
        due = date.fromisoformat(row["next_due_date"])
    except Exception:
        return "⚪ дата не настроена", False
    today = _today(uid)
    if due < today:
        return f"🔴 просрочено {(today-due).days} дн.", True
    if due == today:
        return "🟠 оплата сегодня", False
    return f"🟢 оплачено до {due.strftime('%d.%m')}", False


def _individual(uid, sid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name FROM students WHERE id=? AND teacher_telegram_user_id=? AND active=1",
            (int(sid), int(uid)),
        ).fetchone()


def _member(uid, pid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.id,p.name,p.group_id,g.name AS group_name
            FROM student_reminder_people p
            JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.id=? AND p.teacher_id=? AND p.kind='group'
              AND p.active=1 AND g.active=1
            """,
            (int(pid), int(uid)),
        ).fetchone()


def _stats(uid, kind, subject_id, start, end, payment_sid=None):
    att = _attendance(uid, kind, subject_id, start, end)
    hw = _homework(uid, kind, subject_id, start, end)
    overdue = _homework(uid, kind, subject_id, overdue=True)["pending"]
    pay_text, pay_problem = ("", False)
    if payment_sid is not None:
        pay_text, pay_problem = _payment(uid, payment_sid)
    return {
        "att": att, "hw": hw, "overdue": overdue,
        "pay_text": pay_text, "pay_problem": pay_problem,
    }


def _subject_text(uid, kind, subject_id, name, subtitle="", payment_sid=None):
    start, end = _range(uid, 30)
    st = _stats(uid, kind, subject_id, start, end, payment_sid)
    att, hw = st["att"], st["hw"]
    lines = [
        f"👤 {name}",
        subtitle,
        f"Период: {start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        "",
        "✅ Посещаемость",
        f"• был(а): {att['present']}",
        f"• пропустил(а): {att['absent']}",
        f"• посещаемость: {_pct(att['present'], att['total'])}",
        "",
        "📚 Домашнее",
        f"• выполнено: {hw['done']}/{hw['total']}",
        f"• выполнение: {_pct(hw['done'], hw['total'])}",
        f"• просрочено сейчас: {st['overdue']}",
    ]
    if payment_sid is not None:
        lines += ["", "💳 Оплата", f"• {st['pay_text']}"]
    return "\n".join(x for x in lines if x != "")


def _group_report(uid, gid):
    group = groups.get_group(uid, gid)
    if not group:
        return None, None
    start, end = _range(uid, 30)
    members = student_reminders._members(uid, gid)
    lines = [
        f"👥 {group['name']}",
        f"Период: {start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        f"Учеников: {len(members)}",
        "",
    ]
    buttons = []
    present = absent = done = hw_total = overdue = 0
    for m in members[:60]:
        st = _stats(uid, "group_member", int(m["id"]), start, end)
        a, h = st["att"], st["hw"]
        present += a["present"]
        absent += a["absent"]
        done += h["done"]
        hw_total += h["total"]
        overdue += st["overdue"]
        flags = []
        if a["absent"] >= 2:
            flags.append(f"❌ {a['absent']} проп.")
        if st["overdue"]:
            flags.append(f"📚 долг {st['overdue']}")
        tail = " • " + ", ".join(flags) if flags else ""
        lines.append(
            f"• {m['name']}: посещ. {_pct(a['present'], a['total'])} • "
            f"ДЗ {_pct(h['done'], h['total'])}{tail}"
        )
        buttons.append([
            InlineKeyboardButton(f"👤 {m['name']}", callback_data=f"report:gmember:{m['id']}")
        ])
    if members:
        lines += [
            "",
            "Итого",
            f"• посещаемость: {_pct(present, present + absent)}",
            f"• выполнение ДЗ: {_pct(done, hw_total)}",
            f"• просроченных ДЗ сейчас: {overdue}",
        ]
    else:
        lines.append("В группе пока нет учеников.")
    buttons.append([InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _course_subjects(uid, cid):
    gs = courses.course_groups(uid, cid)
    indiv = [int(s["id"]) for s in courses.course_students(uid, cid)]
    gids = [int(g["id"]) for g in gs]
    members = []
    if gids:
        placeholders = ",".join("?" for _ in gids)
        with base.db() as conn:
            rows = conn.execute(
                f"""
                SELECT id FROM student_reminder_people
                WHERE teacher_id=? AND kind='group' AND active=1
                  AND group_id IN ({placeholders})
                """,
                (int(uid), *gids),
            ).fetchall()
        members = [int(r["id"]) for r in rows]
    return indiv, members, gs


def _all_subjects(uid):
    indiv = [int(s["id"]) for s in base.list_students(uid)]
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT p.id
            FROM student_reminder_people p
            JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.teacher_id=? AND p.kind='group' AND p.active=1 AND g.active=1
            """,
            (int(uid),),
        ).fetchall()
    return indiv, [int(r["id"]) for r in rows]


def _aggregate(uid, indiv, members, start, end):
    out = {
        "present": 0, "absent": 0, "done": 0, "hw_total": 0,
        "overdue": 0, "payment_issues": 0, "learners": len(indiv) + len(members),
    }
    for sid in indiv:
        st = _stats(uid, "individual", sid, start, end, sid)
        out["present"] += st["att"]["present"]
        out["absent"] += st["att"]["absent"]
        out["done"] += st["hw"]["done"]
        out["hw_total"] += st["hw"]["total"]
        out["overdue"] += st["overdue"]
        out["payment_issues"] += int(st["pay_problem"])
    for pid in members:
        st = _stats(uid, "group_member", pid, start, end)
        out["present"] += st["att"]["present"]
        out["absent"] += st["att"]["absent"]
        out["done"] += st["hw"]["done"]
        out["hw_total"] += st["hw"]["total"]
        out["overdue"] += st["overdue"]
    return out


def course_report_text(uid, cid, days=30):
    course = courses.get_course(uid, cid)
    if not course:
        return None
    start, end = _range(uid, days)
    indiv, members, gs = _course_subjects(uid, cid)
    a = _aggregate(uid, indiv, members, start, end)
    lines = [
        f"📚 {course['name']}",
        f"📊 Отчёт • {start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        "",
        f"🧑‍🎓 Учеников: {a['learners']}",
        f"👥 Групп: {len(gs)}",
        f"✅ Посещаемость: {_pct(a['present'], a['present'] + a['absent'])}",
        f"📚 Выполнение ДЗ: {_pct(a['done'], a['hw_total'])}",
        f"🚨 Просроченных ДЗ сейчас: {a['overdue']}",
    ]
    if indiv:
        lines.append(f"💳 Проблем с оплатой у индивидуальных: {a['payment_issues']}")
    if not a["learners"]:
        lines += ["", "Подключи к курсу группы или учеников — отчёт заполнится автоматически."]
    return "\n".join(lines)


def teacher_report_between(uid, start, end, title="📊 Общий отчёт"):
    indiv, members = _all_subjects(uid)
    a = _aggregate(uid, indiv, members, start, end)
    with base.db() as conn:
        marked = int(conn.execute(
            """
            SELECT COUNT(*) AS c FROM (
              SELECT DISTINCT lesson_kind,schedule_slot_id,lesson_date
              FROM teacher_attendance
              WHERE teacher_telegram_user_id=? AND lesson_date>=? AND lesson_date<=?
            )
            """,
            (int(uid), start.isoformat(), end.isoformat()),
        ).fetchone()["c"] or 0)
        cancelled = int(conn.execute(
            """
            SELECT COUNT(*) AS c FROM teacher_lesson_cancellations
            WHERE teacher_telegram_user_id=? AND actual_date>=? AND actual_date<=?
            """,
            (int(uid), start.isoformat(), end.isoformat()),
        ).fetchone()["c"] or 0)
        mi = int(conn.execute(
            "SELECT COUNT(*) AS c FROM schedule_moves WHERE teacher_telegram_user_id=? AND new_date>=? AND new_date<=?",
            (int(uid), start.isoformat(), end.isoformat()),
        ).fetchone()["c"] or 0)
        mg = int(conn.execute(
            "SELECT COUNT(*) AS c FROM group_schedule_moves WHERE teacher_telegram_user_id=? AND new_date>=? AND new_date<=?",
            (int(uid), start.isoformat(), end.isoformat()),
        ).fetchone()["c"] or 0)
    return "\n".join([
        f"{title} • {start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        "",
        f"🧑‍🎓 Активных учеников: {a['learners']}",
        f"✅ Занятий с отмеченной посещаемостью: {marked}",
        f"↪️ Переносов: {mi + mg}",
        f"❌ Отмен: {cancelled}",
        "",
        f"✅ Средняя посещаемость: {_pct(a['present'], a['present'] + a['absent'])}",
        f"📚 Выполнение ДЗ: {_pct(a['done'], a['hw_total'])}",
        f"🚨 Просроченных ДЗ сейчас: {a['overdue']}",
        f"💳 Проблем с оплатой: {a['payment_issues']}",
    ])


def teacher_report_text(uid, days=30):
    start, end = _range(uid, days)
    return teacher_report_between(uid, start, end)


def attention_rows(uid):
    start, end = _range(uid, 30)
    result = []
    for s in base.list_students(uid):
        sid = int(s["id"])
        st = _stats(uid, "individual", sid, start, end, sid)
        reasons = []
        if st["att"]["absent"] >= 2:
            reasons.append(f"{st['att']['absent']} пропуска")
        if st["overdue"] >= 2:
            reasons.append(f"{st['overdue']} долга по ДЗ")
        if st["pay_problem"]:
            reasons.append("оплата")
        if reasons:
            result.append((s["name"], "👤", reasons, f"report:student:{sid}"))
    with base.db() as conn:
        members = conn.execute(
            """
            SELECT p.id,p.name,g.name AS group_name
            FROM student_reminder_people p
            JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.teacher_id=? AND p.kind='group' AND p.active=1 AND g.active=1
            """,
            (int(uid),),
        ).fetchall()
    for m in members:
        pid = int(m["id"])
        st = _stats(uid, "group_member", pid, start, end)
        reasons = []
        if st["att"]["absent"] >= 2:
            reasons.append(f"{st['att']['absent']} пропуска")
        if st["overdue"] >= 2:
            reasons.append(f"{st['overdue']} долга по ДЗ")
        if reasons:
            result.append((m["name"], f"👥 {m['group_name']}", reasons, f"report:gmember:{pid}"))
    result.sort(key=lambda x: (-len(x[2]), x[0].lower()))
    return result


def attention_text(uid):
    rows = attention_rows(uid)
    lines = [
        "🚨 Зона внимания",
        "",
        "Критерии MVP: 2+ пропуска за 30 дней, 2+ просроченных ДЗ или проблема с оплатой.",
        "",
    ]
    if not rows:
        lines.append("Сейчас явных сигналов нет 🎉")
    else:
        lines.append(f"Требуют внимания: {len(rows)}")
        for name, scope, reasons, _ in rows[:30]:
            lines.append(f"• {name} · {scope}: {', '.join(reasons)}")
    return "\n".join(lines), rows


def _menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 По ученику", callback_data="report:students")],
        [InlineKeyboardButton("👥 По группе", callback_data="report:groups")],
        [InlineKeyboardButton("📚 По курсу", callback_data="report:courses")],
        [InlineKeyboardButton("🧑‍🏫 Мой общий", callback_data="report:teacher:30")],
        [InlineKeyboardButton("🚨 Зона внимания", callback_data="report:attention")],
        [InlineKeyboardButton("🔔 Автосводки", callback_data="report:auto")],
    ])


async def reports_menu(update, context):
    if not base.teacher(update.effective_user.id):
        raise ApplicationHandlerStop
    await update.message.reply_text(
        "📊 Отчёты\n\nПРЕПОДМИН собирает их сам из уже внесённых данных.",
        reply_markup=_menu_markup(),
    )
    raise ApplicationHandlerStop


async def menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📊 Отчёты\n\nВыбери отчёт.", reply_markup=_menu_markup())
    raise ApplicationHandlerStop


async def students_picker(update, context):
    q = update.callback_query
    await q.answer()
    buttons = [
        [InlineKeyboardButton(f"👤 {s['name']}", callback_data=f"report:student:{s['id']}")]
        for s in base.list_students(q.from_user.id)[:60]
    ]
    buttons.append([InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")])
    await q.edit_message_text("👤 Выбери ученика.", reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


async def student_report(update, context):
    q = update.callback_query
    await q.answer()
    uid, sid = int(q.from_user.id), int(q.data.rsplit(":", 1)[1])
    row = _individual(uid, sid)
    if not row:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        _subject_text(uid, "individual", sid, row["name"], payment_sid=sid),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ К ученикам", callback_data="report:students")],
            [InlineKeyboardButton("📊 К отчётам", callback_data="report:menu")],
        ]),
    )
    raise ApplicationHandlerStop


async def groups_picker(update, context):
    q = update.callback_query
    await q.answer()
    buttons = [
        [InlineKeyboardButton(f"👥 {g['name']}", callback_data=f"report:group:{g['id']}")]
        for g in groups.groups(q.from_user.id)[:60]
    ]
    buttons.append([InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")])
    await q.edit_message_text("👥 Выбери группу.", reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


async def group_report(update, context):
    q = update.callback_query
    await q.answer()
    text, kb = _group_report(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    if not text:
        await q.edit_message_text("Группа не найдена.")
    else:
        await q.edit_message_text(text[:3900], reply_markup=kb)
    raise ApplicationHandlerStop


async def group_member_report(update, context):
    q = update.callback_query
    await q.answer()
    uid, pid = int(q.from_user.id), int(q.data.rsplit(":", 1)[1])
    row = _member(uid, pid)
    if not row:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        _subject_text(uid, "group_member", pid, row["name"], f"👥 {row['group_name']}"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ К группе", callback_data=f"report:group:{row['group_id']}")],
            [InlineKeyboardButton("📊 К отчётам", callback_data="report:menu")],
        ]),
    )
    raise ApplicationHandlerStop


async def courses_picker(update, context):
    q = update.callback_query
    await q.answer()
    rows = courses.courses(q.from_user.id)
    buttons = [
        [InlineKeyboardButton(f"📚 {c['name']}", callback_data=f"report:course:{c['id']}")]
        for c in rows[:50]
    ]
    buttons.append([InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")])
    text = "📚 Выбери курс." if rows else "📚 Сначала создай курс в разделе «👥 Ученики и группы»."
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


async def course_report(update, context):
    q = update.callback_query
    await q.answer()
    uid, cid = int(q.from_user.id), int(q.data.rsplit(":", 1)[1])
    text = course_report_text(uid, cid)
    if not text:
        await q.edit_message_text("Курс не найден.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 К курсу", callback_data=f"course:view:{cid}")],
            [InlineKeyboardButton("📊 К отчётам", callback_data="report:menu")],
        ]),
    )
    raise ApplicationHandlerStop


async def teacher_report(update, context):
    q = update.callback_query
    await q.answer()
    days = int(q.data.rsplit(":", 1)[1])
    await q.edit_message_text(
        teacher_report_text(q.from_user.id, days),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("7 дней", callback_data="report:teacher:7"),
                InlineKeyboardButton("30 дней", callback_data="report:teacher:30"),
            ],
            [InlineKeyboardButton("🚨 Зона внимания", callback_data="report:attention")],
            [InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")],
        ]),
    )
    raise ApplicationHandlerStop


async def attention_view(update, context):
    q = update.callback_query
    await q.answer()
    text, rows = attention_text(q.from_user.id)
    buttons = [
        [InlineKeyboardButton(f"{scope} {name}", callback_data=callback)]
        for name, scope, reasons, callback in rows[:25]
    ]
    buttons.append([InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")])
    await q.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop


def _settings(uid):
    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teacher_report_settings(
                teacher_telegram_user_id,weekly_enabled,monthly_enabled,updated_at
            ) VALUES(?,0,0,?)
            """,
            (int(uid), now),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM teacher_report_settings WHERE teacher_telegram_user_id=?",
            (int(uid),),
        ).fetchone()


def _auto_text(uid):
    s = _settings(uid)
    return (
        "🔔 Автоматические сводки\n\n"
        f"{'✅' if s['weekly_enabled'] else '▫️'} Недельная — воскресенье, 19:00\n"
        f"{'✅' if s['monthly_enabled'] else '▫️'} Месячная — 1-го числа, 10:00\n\n"
        "По умолчанию обе выключены."
    )


def _auto_markup(uid):
    s = _settings(uid)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            ("✅" if s["weekly_enabled"] else "▫️") + " Недельная",
            callback_data="report:auto:weekly",
        )],
        [InlineKeyboardButton(
            ("✅" if s["monthly_enabled"] else "▫️") + " Месячная",
            callback_data="report:auto:monthly",
        )],
        [InlineKeyboardButton("⬅️ К отчётам", callback_data="report:menu")],
    ])


async def auto_view(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(_auto_text(q.from_user.id), reply_markup=_auto_markup(q.from_user.id))
    raise ApplicationHandlerStop


async def auto_toggle(update, context):
    q = update.callback_query
    uid = int(q.from_user.id)
    column = "weekly_enabled" if q.data.endswith("weekly") else "monthly_enabled"
    _settings(uid)
    with base.db() as conn:
        current = int(conn.execute(
            f"SELECT {column} AS v FROM teacher_report_settings WHERE teacher_telegram_user_id=?",
            (uid,),
        ).fetchone()["v"])
        conn.execute(
            f"UPDATE teacher_report_settings SET {column}=?,updated_at=? WHERE teacher_telegram_user_id=?",
            (0 if current else 1, datetime.utcnow().isoformat(), uid),
        )
        conn.commit()
    await q.answer("Сохранено")
    await q.edit_message_text(_auto_text(uid), reply_markup=_auto_markup(uid))
    raise ApplicationHandlerStop


def _sent(uid, key):
    with base.db() as conn:
        return bool(conn.execute(
            "SELECT 1 FROM teacher_report_delivery WHERE teacher_telegram_user_id=? AND report_key=?",
            (int(uid), key),
        ).fetchone())


def _mark_sent(uid, key):
    with base.db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO teacher_report_delivery(teacher_telegram_user_id,report_key,sent_at) VALUES(?,?,?)",
            (int(uid), key, datetime.utcnow().isoformat()),
        )
        conn.commit()


def _previous_month(day):
    first = day.replace(day=1)
    end = first - timedelta(days=1)
    return end.replace(day=1), end


async def automatic_tick(context):
    ensure_tables()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT t.telegram_user_id,s.weekly_enabled,s.monthly_enabled
            FROM teachers t JOIN teacher_report_settings s
              ON s.teacher_telegram_user_id=t.telegram_user_id
            WHERE t.onboarding_completed_at IS NOT NULL
              AND (s.weekly_enabled=1 OR s.monthly_enabled=1)
            """
        ).fetchall()
    for row in rows:
        uid = int(row["telegram_user_id"])
        now = datetime.now(schedule.tz(uid))
        if row["weekly_enabled"] and now.weekday() == 6 and now.hour == 19 and now.minute < 15:
            key = f"weekly:{now.date().isoformat()}"
            if not _sent(uid, key):
                try:
                    start = now.date() - timedelta(days=6)
                    await context.bot.send_message(uid, teacher_report_between(uid, start, now.date(), "📊 Недельная сводка"))
                    _mark_sent(uid, key)
                except Exception as exc:
                    print(f"Weekly report failed uid={uid}: {type(exc).__name__}", flush=True)
        if row["monthly_enabled"] and now.day == 1 and now.hour == 10 and now.minute < 15:
            start, end = _previous_month(now.date())
            key = f"monthly:{start.strftime('%Y-%m')}"
            if not _sent(uid, key):
                try:
                    await context.bot.send_message(uid, teacher_report_between(uid, start, end, f"📊 Месячная сводка · {start.strftime('%m.%Y')}"))
                    _mark_sent(uid, key)
                except Exception as exc:
                    print(f"Monthly report failed uid={uid}: {type(exc).__name__}", flush=True)


def _keyboard():
    rows = [list(row) for row in base.MAIN_KB.keyboard]
    rows = [[b for b in row if b.text != "📊 Отчёты"] for row in rows]
    rows = [r for r in rows if r]
    idx = next(
        (i for i, row in enumerate(rows) if any(b.text == "✅ Задачи" for b in row)),
        3,
    )
    rows.insert(idx + 1, ["📊 Отчёты"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def install(app):
    ensure_tables()
    base.MAIN_KB = _keyboard()
    app.add_handler(MessageHandler(filters.Regex(r"^📊 Отчёты$"), reports_menu), group=-24)
    for pattern, handler in (
        (r"^report:menu$", menu_callback),
        (r"^report:students$", students_picker),
        (r"^report:student:\d+$", student_report),
        (r"^report:groups$", groups_picker),
        (r"^report:group:\d+$", group_report),
        (r"^report:gmember:\d+$", group_member_report),
        (r"^report:courses$", courses_picker),
        (r"^report:course:\d+$", course_report),
        (r"^report:teacher:(?:7|30)$", teacher_report),
        (r"^report:attention$", attention_view),
        (r"^report:auto$", auto_view),
        (r"^report:auto:(?:weekly|monthly)$", auto_toggle),
    ):
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern), group=-24)
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            automatic_tick,
            interval=600,
            first=45,
            name="prepodmin_automatic_reports",
        )
    print(
        "PREPODMIN reports ready: student + group + course + teacher + attention + weekly/monthly summaries",
        flush=True,
    )
    return app
