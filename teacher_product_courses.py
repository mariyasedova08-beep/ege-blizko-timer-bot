"""Courses as a lightweight container for PREPODMIN.

A course links existing groups and/or individual students. It never duplicates
schedule, homework, attendance, payments or Telegram linkage.
"""
from datetime import date, datetime
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_group_members as group_members

COURSE_NAME, COURSE_PERIOD = range(810, 812)


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_courses_teacher
            ON teacher_courses(teacher_telegram_user_id, active, name);

            CREATE TABLE IF NOT EXISTS teacher_course_groups (
                course_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY(course_id, group_id)
            );

            CREATE TABLE IF NOT EXISTS teacher_course_students (
                course_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY(course_id, student_id)
            );
            """
        )
        conn.commit()


def courses(uid):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT id,name,start_date,end_date
            FROM teacher_courses
            WHERE teacher_telegram_user_id=? AND active=1
            ORDER BY lower(name),id
            """,
            (int(uid),),
        ).fetchall()


def get_course(uid, cid):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT * FROM teacher_courses
            WHERE id=? AND teacher_telegram_user_id=? AND active=1
            """,
            (int(cid), int(uid)),
        ).fetchone()


def course_groups(uid, cid):
    if not get_course(uid, cid):
        return []
    with base.db() as conn:
        return conn.execute(
            """
            SELECT g.id,g.name
            FROM teacher_course_groups cg
            JOIN teacher_groups g ON g.id=cg.group_id
            WHERE cg.course_id=? AND g.teacher_telegram_user_id=? AND g.active=1
            ORDER BY lower(g.name)
            """,
            (int(cid), int(uid)),
        ).fetchall()


def course_students(uid, cid):
    if not get_course(uid, cid):
        return []
    with base.db() as conn:
        return conn.execute(
            """
            SELECT s.id,s.name,s.contact
            FROM teacher_course_students cs
            JOIN students s ON s.id=cs.student_id
            WHERE cs.course_id=? AND s.teacher_telegram_user_id=? AND s.active=1
            ORDER BY lower(s.name)
            """,
            (int(cid), int(uid)),
        ).fetchall()


def _group_member_count(uid, gids):
    if not gids:
        return 0
    placeholders = ",".join("?" for _ in gids)
    with base.db() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM student_reminder_people
            WHERE teacher_id=? AND kind='group' AND active=1
              AND group_id IN ({placeholders})
            """,
            (int(uid), *[int(g) for g in gids]),
        ).fetchone()
    return int(row["c"] or 0)


def _period_text(row):
    start = row["start_date"]
    end = row["end_date"]
    if not start and not end:
        return "период не указан"
    try:
        a = date.fromisoformat(start).strftime("%d.%m.%Y") if start else "…"
        b = date.fromisoformat(end).strftime("%d.%m.%Y") if end else "…"
        return f"{a} — {b}"
    except Exception:
        return "период не указан"


def _people_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Индивидуальные", callback_data="people:individual")],
        [InlineKeyboardButton("👥 Группы", callback_data="people:groups")],
        [InlineKeyboardButton("📚 Курсы", callback_data="course:list")],
    ])


async def people_menu(update, context):
    if not base.teacher(update.effective_user.id):
        raise ApplicationHandlerStop
    await update.effective_message.reply_text(
        "👥 Ученики, группы и курсы\n\n"
        "Курс объединяет уже существующие группы и индивидуальных учеников — "
        "ничего повторно заводить не нужно.",
        reply_markup=_people_markup(),
    )
    raise ApplicationHandlerStop


async def people_back(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "👥 Ученики, группы и курсы\n\nВыбери раздел.",
        reply_markup=_people_markup(),
    )
    raise ApplicationHandlerStop


def _list_markup(uid):
    rows = courses(uid)
    buttons = [
        [InlineKeyboardButton(f"📚 {r['name']}", callback_data=f"course:view:{r['id']}")]
        for r in rows[:50]
    ]
    buttons.append([InlineKeyboardButton("➕ Создать курс", callback_data="course:add")])
    buttons.append([InlineKeyboardButton("⬅️ К ученикам и группам", callback_data="people:back")])
    return InlineKeyboardMarkup(buttons)


async def list_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    rows = courses(uid)
    text = (
        f"📚 Курсы: {len(rows)}\n\n"
        "Курс — это контейнер над группами и индивидуальными учениками. "
        "Расписание, ДЗ и посещаемость остаются общими."
        if rows else
        "📚 Курсы\n\nПока курсов нет. Создай первый и подключи к нему существующие группы или учеников."
    )
    await q.edit_message_text(text, reply_markup=_list_markup(uid))
    raise ApplicationHandlerStop


async def add_begin(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "➕ Новый курс\n\nКак он называется?\nНапример: ЕГЭ 11 класс 2026/27"
    )
    return COURSE_NAME


async def add_name(update, context):
    name = str(update.message.text or "").strip()
    if len(name) < 2 or len(name) > 120 or name.startswith("/"):
        await update.message.reply_text("Напиши короткое название курса обычным текстом.")
        return COURSE_NAME
    context.user_data["course_name"] = name
    await update.message.reply_text(
        "Укажи период одним сообщением:\n"
        "01.09.2026–31.05.2027\n\n"
        "Или напиши «без периода»."
    )
    return COURSE_PERIOD


def _parse_period(text):
    raw = str(text or "").strip().lower().replace("—", "-").replace("–", "-")
    if raw in {"без периода", "нет", "-", "не указывать"}:
        return None, None
    parts = [p.strip() for p in raw.split("-") if p.strip()]
    if len(parts) != 2:
        return False
    parsed = []
    for value in parts:
        ok = None
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                ok = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                pass
        if not ok:
            return False
        parsed.append(ok)
    if parsed[1] < parsed[0]:
        return False
    return parsed[0], parsed[1]


async def add_period(update, context):
    period = _parse_period(update.message.text)
    if period is False:
        await update.message.reply_text(
            "Не поняла период. Напиши, например: 01.09.2026–31.05.2027\n"
            "Или «без периода»."
        )
        return COURSE_PERIOD
    name = context.user_data.pop("course_name", None)
    if not name:
        await update.message.reply_text("Создание сбилось. Открой «📚 Курсы» и попробуй ещё раз.")
        return ConversationHandler.END
    start, end = period
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO teacher_courses(
                teacher_telegram_user_id,name,start_date,end_date,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                int(update.effective_user.id), name,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
                now, now,
            ),
        )
        cid = int(cur.lastrowid)
        conn.commit()
    await update.message.reply_text(
        f"✅ Курс «{name}» создан.\n\nТеперь подключи к нему существующие группы и/или индивидуальных учеников.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📚 Открыть курс", callback_data=f"course:view:{cid}")
        ]]),
    )
    return ConversationHandler.END


def _course_card_text(uid, course):
    gs = course_groups(uid, course["id"])
    students = course_students(uid, course["id"])
    members = _group_member_count(uid, [g["id"] for g in gs])
    total = members + len(students)
    lines = [
        f"📚 {course['name']}",
        f"Период: {_period_text(course)}",
        "",
        f"👥 Групп: {len(gs)}",
        f"👤 Индивидуальных: {len(students)}",
        f"🧑‍🎓 Учеников внутри: {total}",
    ]
    if gs:
        lines += ["", "Группы:"] + [f"• {g['name']}" for g in gs[:12]]
    if students:
        lines += ["", "Индивидуальные:"] + [f"• {s['name']}" for s in students[:12]]
    return "\n".join(lines)


def _course_card_markup(cid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Подключить группы", callback_data=f"course:groups:{cid}")],
        [InlineKeyboardButton("👤 Подключить индивидуальных", callback_data=f"course:students:{cid}")],
        [InlineKeyboardButton("📊 Отчёт по курсу", callback_data=f"report:course:{cid}")],
        [InlineKeyboardButton("🗑 Архивировать курс", callback_data=f"course:archive:{cid}")],
        [InlineKeyboardButton("⬅️ К курсам", callback_data="course:list")],
    ])


async def course_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    cid = int(q.data.rsplit(":", 1)[1])
    course = get_course(uid, cid)
    if not course:
        await q.edit_message_text("Курс не найден.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        _course_card_text(uid, course),
        reply_markup=_course_card_markup(cid),
    )
    raise ApplicationHandlerStop


def _toggle_markup(uid, cid, kind):
    if kind == "group":
        all_rows = groups.groups(uid)
        linked = {int(r["id"]) for r in course_groups(uid, cid)}
        prefix = "course:gtoggle"
        icon = "👥"
    else:
        all_rows = base.list_students(uid)
        linked = {int(r["id"]) for r in course_students(uid, cid)}
        prefix = "course:stoggle"
        icon = "👤"
    buttons = []
    for row in all_rows[:60]:
        mark = "✅" if int(row["id"]) in linked else "▫️"
        buttons.append([
            InlineKeyboardButton(
                f"{mark} {icon} {row['name']}",
                callback_data=f"{prefix}:{cid}:{row['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("✅ Готово", callback_data=f"course:view:{cid}")])
    return InlineKeyboardMarkup(buttons)


async def link_groups(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    cid = int(q.data.rsplit(":", 1)[1])
    if not get_course(uid, cid):
        await q.edit_message_text("Курс не найден.")
        raise ApplicationHandlerStop
    rows = groups.groups(uid)
    text = (
        "👥 Группы курса\n\nНажимай на группы, которые входят в курс. Изменения сохраняются сразу."
        if rows else
        "👥 Группы курса\n\nСначала создай хотя бы одну группу."
    )
    await q.edit_message_text(text, reply_markup=_toggle_markup(uid, cid, "group"))
    raise ApplicationHandlerStop


async def link_students(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    cid = int(q.data.rsplit(":", 1)[1])
    if not get_course(uid, cid):
        await q.edit_message_text("Курс не найден.")
        raise ApplicationHandlerStop
    rows = base.list_students(uid)
    text = (
        "👤 Индивидуальные ученики курса\n\nНажимай на учеников, которые входят в курс. Изменения сохраняются сразу."
        if rows else
        "👤 Индивидуальные ученики курса\n\nСначала добавь хотя бы одного индивидуального ученика."
    )
    await q.edit_message_text(text, reply_markup=_toggle_markup(uid, cid, "student"))
    raise ApplicationHandlerStop


def _toggle_link(uid, cid, item_id, kind):
    if not get_course(uid, cid):
        return False
    now = datetime.utcnow().isoformat()
    table = "teacher_course_groups" if kind == "group" else "teacher_course_students"
    column = "group_id" if kind == "group" else "student_id"
    with base.db() as conn:
        exists = conn.execute(
            f"SELECT 1 FROM {table} WHERE course_id=? AND {column}=?",
            (int(cid), int(item_id)),
        ).fetchone()
        if exists:
            conn.execute(
                f"DELETE FROM {table} WHERE course_id=? AND {column}=?",
                (int(cid), int(item_id)),
            )
        else:
            conn.execute(
                f"INSERT INTO {table}(course_id,{column},added_at) VALUES(?,?,?)",
                (int(cid), int(item_id), now),
            )
        conn.commit()
    return True


async def toggle_group(update, context):
    q = update.callback_query
    await q.answer("Сохранено")
    _, _, cid, gid = q.data.split(":")
    uid = int(q.from_user.id)
    _toggle_link(uid, int(cid), int(gid), "group")
    await q.edit_message_reply_markup(reply_markup=_toggle_markup(uid, int(cid), "group"))
    raise ApplicationHandlerStop


async def toggle_student(update, context):
    q = update.callback_query
    await q.answer("Сохранено")
    _, _, cid, sid = q.data.split(":")
    uid = int(q.from_user.id)
    _toggle_link(uid, int(cid), int(sid), "student")
    await q.edit_message_reply_markup(reply_markup=_toggle_markup(uid, int(cid), "student"))
    raise ApplicationHandlerStop


async def archive_course(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    cid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        conn.execute(
            "UPDATE teacher_courses SET active=0,updated_at=? WHERE id=? AND teacher_telegram_user_id=?",
            (datetime.utcnow().isoformat(), cid, uid),
        )
        conn.commit()
    await q.edit_message_text(
        "✅ Курс архивирован. Группы, ученики, расписание и вся история остались на месте.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ К курсам", callback_data="course:list")
        ]]),
    )
    raise ApplicationHandlerStop


def install(app):
    ensure_tables()
    app.add_handler(
        MessageHandler(filters.Regex(r"^👥 Ученики и группы$"), people_menu),
        group=-23,
    )
    app.add_handler(CallbackQueryHandler(people_back, pattern=r"^people:back$"), group=-23)
    app.add_handler(CallbackQueryHandler(list_view, pattern=r"^course:list$"), group=-23)
    app.add_handler(CallbackQueryHandler(course_view, pattern=r"^course:view:\d+$"), group=-23)
    app.add_handler(CallbackQueryHandler(link_groups, pattern=r"^course:groups:\d+$"), group=-23)
    app.add_handler(CallbackQueryHandler(link_students, pattern=r"^course:students:\d+$"), group=-23)
    app.add_handler(CallbackQueryHandler(toggle_group, pattern=r"^course:gtoggle:\d+:\d+$"), group=-23)
    app.add_handler(CallbackQueryHandler(toggle_student, pattern=r"^course:stoggle:\d+:\d+$"), group=-23)
    app.add_handler(CallbackQueryHandler(archive_course, pattern=r"^course:archive:\d+$"), group=-23)
    app.add_handler(
        ConversationHandler(
            entry_points=[CallbackQueryHandler(add_begin, pattern=r"^course:add$")],
            states={
                COURSE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
                COURSE_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_period)],
            },
            fallbacks=[],
            per_message=False,
        ),
        group=-23,
    )
    print("PREPODMIN courses ready: lightweight container over groups + individual students", flush=True)
    return app
