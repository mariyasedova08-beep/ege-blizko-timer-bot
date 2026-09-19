"""Kulechki rewards for EGE BLIZKO admin cabinet.

Manual practice awards are stored as a ledger, so Maria can safely award
past lessons and toggle accidental awards off.
"""
import html
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import ege_admin_webapp as admin_app

bot = admin_app.bot
live23 = admin_app.live23
live34 = admin_app.live34
run_bot = admin_app.live79.run_bot

_INSTALLED = False
_previous_markup = None
_previous_callback = None


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kulechki_awards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                month_key TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL,
                points INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL,
                lesson_number INTEGER,
                lesson_date TEXT,
                awarded_at TEXT NOT NULL,
                metadata_json TEXT,
                UNIQUE(student_id, source_type, source_key)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_kulechki_awards_month
            ON kulechki_awards(month_key, student_id, source_type)
            """
        )
        conn.commit()


def _student_rows():
    return live34._student_rows()


def _student_name(student_id):
    sid = int(student_id)
    for row in _student_rows():
        if int(row[0]) == sid:
            return live34._shown_name(row)
    return f"Ученик #{sid}"


def _lesson_date(lesson_number):
    number = int(lesson_number)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT event_date
            FROM course_schedule
            WHERE active=1 AND event_type='lesson' AND lesson_number=?
            ORDER BY event_date DESC
            LIMIT 1
            """,
            (number,),
        ).fetchone()
    if row and row[0]:
        try:
            return datetime.fromisoformat(str(row[0])).date()
        except Exception:
            pass
    dates = tuple(getattr(run_bot, "COURSE_LESSON_DATES", ()) or ())
    if 1 <= number <= len(dates):
        return dates[number - 1]
    return None


def _past_lessons(limit=24):
    today = datetime.now(bot.TIMEZONE).date()
    items = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            rows = conn.execute(
                """
                SELECT lesson_number,event_date,topic
                FROM course_schedule
                WHERE active=1
                  AND event_type='lesson'
                  AND event_date<=?
                  AND lesson_number IS NOT NULL
                ORDER BY event_date DESC, lesson_number DESC
                LIMIT ?
                """,
                (today.isoformat(), int(limit)),
            ).fetchall()
        except Exception:
            rows = []
    seen = set()
    for number, date_text, topic in rows:
        number = int(number)
        if number in seen:
            continue
        seen.add(number)
        try:
            day = datetime.fromisoformat(str(date_text)).date()
        except Exception:
            continue
        items.append(
            {
                "lesson_number": number,
                "date": day,
                "topic": str(topic or ""),
            }
        )

    if not items:
        dates = tuple(getattr(run_bot, "COURSE_LESSON_DATES", ()) or ())
        for index, day in reversed(list(enumerate(dates, 1))):
            if day <= today:
                items.append({"lesson_number": index, "date": day, "topic": ""})
            if len(items) >= limit:
                break
    return items


def _practice_source_key(lesson_number, lesson_date):
    return f"practice:{int(lesson_number)}:{lesson_date.isoformat()}"


def _practice_awarded_ids(lesson_number):
    day = _lesson_date(lesson_number)
    if not day:
        return set()
    key = _practice_source_key(lesson_number, day)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_id
            FROM kulechki_awards
            WHERE source_type='practice' AND source_key=?
            """,
            (key,),
        ).fetchall()
    return {int(row[0]) for row in rows}


def _toggle_practice(student_id, lesson_number):
    sid = int(student_id)
    lesson_number = int(lesson_number)
    day = _lesson_date(lesson_number)
    if not day:
        return False, "Не нашла дату урока."
    source_key = _practice_source_key(lesson_number, day)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        exists = conn.execute(
            """
            SELECT id
            FROM kulechki_awards
            WHERE student_id=? AND source_type='practice' AND source_key=?
            LIMIT 1
            """,
            (sid, source_key),
        ).fetchone()
        if exists:
            conn.execute(
                "DELETE FROM kulechki_awards WHERE id=?",
                (int(exists[0]),),
            )
            conn.commit()
            return False, "Кулёчек снят"
        conn.execute(
            """
            INSERT INTO kulechki_awards(
                student_id,month_key,source_type,source_key,points,title,
                lesson_number,lesson_date,awarded_at
            ) VALUES(?,?,?,?,1,?,?,?,?,?)
            """.replace("?,?,?,?,1,?,?,?,?,?", "?,?,?,?,1,?,?,?,?"),
            (
                sid,
                day.strftime("%Y-%m"),
                "practice",
                source_key,
                f"Практический урок №{lesson_number}",
                lesson_number,
                day.isoformat(),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()
    return True, "🐶 Кулёчек выдан"


def _month_key():
    return datetime.now(bot.TIMEZONE).strftime("%Y-%m")


def _month_summary(month_key=None):
    month_key = month_key or _month_key()
    students = _student_rows()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_id,source_type,SUM(points)
            FROM kulechki_awards
            WHERE month_key=?
            GROUP BY student_id,source_type
            """,
            (month_key,),
        ).fetchall()
    by_student = {}
    for sid, source_type, points in rows:
        by_student.setdefault(int(sid), {})[str(source_type)] = int(points or 0)

    items = []
    for student in students:
        sid = int(student[0])
        cats = by_student.get(sid, {})
        total = sum(cats.values())
        items.append(
            {
                "id": sid,
                "name": live34._shown_name(student),
                "practice": int(cats.get("practice", 0)),
                "homework": int(cats.get("homework_on_time", 0)),
                "final": int(cats.get("final_80", 0)),
                "trainer": int(cats.get("trainer_3", 0)),
                "probnik": int(cats.get("probnik_60", 0)),
                "total": int(total),
            }
        )
    items.sort(key=lambda x: x["name"].casefold())
    return items


def _month_label(month_key=None):
    month_key = month_key or _month_key()
    try:
        year, month = [int(x) for x in month_key.split("-")]
        names = {
            1:"январь",2:"февраль",3:"март",4:"апрель",5:"май",6:"июнь",
            7:"июль",8:"август",9:"сентябрь",10:"октябрь",11:"ноябрь",12:"декабрь"
        }
        return f"{names[month]} {year}"
    except Exception:
        return month_key


def _kulechki_menu_text():
    month = _month_key()
    items = _month_summary(month)
    manual = sum(item["practice"] for item in items)
    total = sum(item["total"] for item in items)
    return (
        "🐶 <b>Кулёчки</b>\n\n"
        f"Месяц: <b>{_month_label(month)}</b>\n"
        f"Всего уже записано: <b>{total}</b> 🐶\n"
        f"Из них за практические уроки: <b>{manual}</b>\n\n"
        "Для прошлых практических уроков нажми «➕ Выдать за прошлый урок». "
        "Повторное нажатие на ребёнка снимает ошибочно выданного Кулёчка."
    )


def _kulechki_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Сводка месяца", callback_data="cab:kule:summary")],
        [InlineKeyboardButton("➕ Выдать за прошлый урок", callback_data="cab:kule:lessons")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _summary_text():
    items = _month_summary()
    lines = [
        "🐶 <b>Кулёчки — " + html.escape(_month_label()) + "</b>",
        "",
        "Сейчас здесь уже учитываются выданные тобой Кулёчки за практические уроки.",
        "Автоматические категории будут попадать в тот же счётчик.",
        "",
    ]
    for item in items:
        lines.append(
            f"<b>{html.escape(item['name'])}</b> — {item['total']} 🐶"
            f" · практика {item['practice']}"
        )
    return "\n".join(lines)


def _lesson_picker_markup():
    rows = []
    for item in _past_lessons():
        number = item["lesson_number"]
        day = item["date"]
        count = len(_practice_awarded_ids(number))
        label = f"№{number} · {day.strftime('%d.%m')} · 🐶 {count}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"cab:kule:lesson:{number}")
        ])
    rows.append([InlineKeyboardButton("← К Кулёчкам", callback_data="cab:kulechki")])
    return InlineKeyboardMarkup(rows)


def _lesson_award_markup(lesson_number):
    awarded = _practice_awarded_ids(lesson_number)
    rows = []
    for student in _student_rows():
        sid = int(student[0])
        name = live34._shown_name(student)
        icon = "🐶" if sid in awarded else "⬜"
        label = f"{icon} {name}"
        if len(label) > 52:
            label = label[:51] + "…"
        rows.append([
            InlineKeyboardButton(
                label,
                callback_data=f"cab:kule:toggle:{int(lesson_number)}:{sid}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            "✅ Готово",
            callback_data=f"cab:kule:done:{int(lesson_number)}",
        )
    ])
    rows.append([InlineKeyboardButton("← К прошлым урокам", callback_data="cab:kule:lessons")])
    return InlineKeyboardMarkup(rows)


def _lesson_award_text(lesson_number):
    day = _lesson_date(lesson_number)
    awarded = _practice_awarded_ids(lesson_number)
    date_text = day.strftime("%d.%m.%Y") if day else "дата не найдена"
    return (
        f"🐶 <b>Практический урок №{int(lesson_number)}</b>\n"
        f"{date_text}\n\n"
        f"Сейчас Кулёчек получили: <b>{len(awarded)}</b> из {len(_student_rows())}.\n\n"
        "Нажми на ребёнка, которому хочешь выдать Кулёчка. "
        "Нажмёшь повторно — награда снимется."
    )


async def _send_chunks(message, text, parse_mode="HTML"):
    rest = str(text or "")
    while rest:
        if len(rest) <= 3800:
            await message.reply_text(rest, parse_mode=parse_mode)
            return
        cut = rest.rfind("\n", 0, 3800)
        if cut < 1:
            cut = 3800
        await message.reply_text(rest[:cut], parse_mode=parse_mode)
        rest = rest[cut:].lstrip("\n")


def _cabinet_markup():
    base = _previous_markup()
    rows = [list(row) for row in base.inline_keyboard]
    rows = [
        [
            b for b in row
            if getattr(b, "callback_data", None) not in {"cab:finalhw", "cab:kulechki"}
        ]
        for row in rows
    ]
    rows = [row for row in rows if row]

    insert_at = 1 if rows else 0
    rows.insert(
        insert_at,
        [
            InlineKeyboardButton("📚 Итоговые ДЗ", callback_data="cab:finalhw"),
            InlineKeyboardButton("🐶 Кулёчки", callback_data="cab:kulechki"),
        ],
    )
    return InlineKeyboardMarkup(rows)


async def _cabinet_callback(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:finalhw":
        await query.answer()
        await _send_chunks(query.message, admin_app._final_homework_bot_text())
        return

    if data == "cab:kulechki":
        await query.answer()
        await query.edit_message_text(
            _kulechki_menu_text(),
            parse_mode="HTML",
            reply_markup=_kulechki_menu_markup(),
        )
        return

    if data == "cab:kule:summary":
        await query.answer()
        await query.edit_message_text(
            _summary_text(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Выдать за прошлый урок", callback_data="cab:kule:lessons")],
                [InlineKeyboardButton("← К Кулёчкам", callback_data="cab:kulechki")],
            ]),
        )
        return

    if data == "cab:kule:lessons":
        await query.answer()
        await query.edit_message_text(
            "🐶 <b>За какой прошлый урок выдать Кулёчков?</b>\n\n"
            "Выбери урок. Справа уже показано, скольким детям ты выдала награду за него.",
            parse_mode="HTML",
            reply_markup=_lesson_picker_markup(),
        )
        return

    if data.startswith("cab:kule:lesson:"):
        await query.answer()
        try:
            lesson_number = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        await query.edit_message_text(
            _lesson_award_text(lesson_number),
            parse_mode="HTML",
            reply_markup=_lesson_award_markup(lesson_number),
        )
        return

    if data.startswith("cab:kule:toggle:"):
        parts = data.split(":")
        try:
            lesson_number = int(parts[-2])
            student_id = int(parts[-1])
        except Exception:
            await query.answer("Не получилось определить ученика", show_alert=True)
            return
        awarded, status = _toggle_practice(student_id, lesson_number)
        await query.answer(status)
        await query.edit_message_text(
            _lesson_award_text(lesson_number),
            parse_mode="HTML",
            reply_markup=_lesson_award_markup(lesson_number),
        )
        print(
            f"EGE kulechki practice toggle lesson={lesson_number} student={student_id} awarded={int(awarded)}",
            flush=True,
        )
        return

    if data.startswith("cab:kule:done:"):
        await query.answer("Сохранено ✅")
        try:
            lesson_number = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        awarded = _practice_awarded_ids(lesson_number)
        await query.edit_message_text(
            f"✅ <b>Урок №{lesson_number} сохранён</b>\n\n"
            f"Кулёчков выдано: <b>{len(awarded)}</b>.\n"
            "Эти награды уже попали в месяц самого урока.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🐶 Другой прошлый урок", callback_data="cab:kule:lessons")],
                [InlineKeyboardButton("📊 Сводка месяца", callback_data="cab:kule:summary")],
                [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
            ]),
        )
        return

    await _previous_callback(update, context)


def install():
    global _INSTALLED, _previous_markup, _previous_callback
    if _INSTALLED:
        return
    _INSTALLED = True
    ensure_tables()
    _previous_markup = live23.cabinet_markup
    _previous_callback = live23.cabinet_callback
    live23.cabinet_markup = _cabinet_markup
    live23.cabinet_callback = _cabinet_callback

    print(
        "EGE Kulechki ready: cabinet buttons + retroactive practice awards",
        flush=True,
    )
