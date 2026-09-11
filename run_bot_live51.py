import html
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live50

live50 = run_bot_live50
live49 = live50.live49
live48 = live50.live48
live47 = live50.live47
live46 = live50.live46
live45 = live50.live45
live44 = live50.live44
live43 = live50.live43
live41 = live50.live41
live39 = live50.live39
live37 = live50.live37
live35 = live50.live35
live34 = live50.live34
live31 = live50.live31
live24 = live50.live24
live17 = live50.live17
live7 = live49.live7
bot = live49.bot

MONTH_NAMES = {9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь"}
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

# Расписание переписано из календарей курса, присланных Марией 11.09.2026.
# schedule_key стабилен: при переносе урока можно менять дату/время одной записи,
# не меняя номер урока и не создавая дубликаты.
SCHEDULE = (
    ("probnik:entrance", "2026-09-02", "17:00", "probnik", None, "Входной пробник"),
    ("lesson:1", "2026-09-07", "18:30", "lesson", 1, "ПРАКТИКА №1, 2, 3"),
    ("lesson:2", "2026-09-09", "18:30", "lesson", 2, "ПРАКТИКА №4, 5"),
    ("lesson:3", "2026-09-13", "10:00", "lesson", 3, "Решение задач через уравнение химических реакций"),
    ("lesson:4", "2026-09-14", "18:30", "lesson", 4, "ПРАКТИКА №18, 19, 20, 21"),
    ("lesson:5", "2026-09-16", "18:30", "lesson", 5, "ПРАКТИКА №22, 23, 26, 27"),
    ("lesson:6", "2026-09-20", "10:00", "lesson", 6, "№28 — решение задач на примесь"),
    ("lesson:7", "2026-09-21", "18:30", "lesson", 7, "Общие свойства металлов и способы их получения"),
    ("lesson:8", "2026-09-23", "18:30", "lesson", 8, "Общие свойства неметаллов и способы их получения"),
    ("lesson:9", "2026-09-27", "10:00", "lesson", 9, "№28 — решение задач на выход продукта реакции"),
    ("lesson:10", "2026-09-28", "18:30", "lesson", 10, "ПРАКТИКА — металлы и неметаллы"),
    ("lesson:11", "2026-09-30", "18:30", "lesson", 11, "Химические свойства оксидов и способы их получения"),
    ("lesson:12", "2026-10-04", "10:00", "lesson", 12, "ПРАКТИКА №28"),
    ("lesson:13", "2026-10-05", "18:30", "lesson", 13, "ПРАКТИКА — оксиды"),
    ("lesson:14", "2026-10-07", "18:30", "lesson", 14, "Химические свойства гидроксидов и способы их получения"),
    ("lesson:15", "2026-10-11", "10:00", "lesson", 15, "Расчётные задачи на массу конечного раствора. Избыток и недостаток"),
    ("lesson:16", "2026-10-12", "18:30", "lesson", 16, "ПРАКТИКА — гидроксиды"),
    ("lesson:17", "2026-10-14", "18:30", "lesson", 17, "Химические свойства средних солей и способы их получения"),
    ("lesson:18", "2026-10-18", "10:00", "lesson", 18, "№34 — масса конечного раствора"),
    ("lesson:19", "2026-10-19", "18:30", "lesson", 19, "Химические свойства кислых, основных и комплексных солей"),
    ("lesson:20", "2026-10-21", "18:30", "lesson", 20, "ПРАКТИКА — соли"),
    ("lesson:21", "2026-10-25", "10:00", "lesson", 21, "№34 — электролиз и молярная концентрация"),
    ("lesson:22", "2026-10-26", "18:30", "lesson", 22, "Необратимый гидролиз бинарных соединений и солей. Некоторые ОВР"),
    ("lesson:23", "2026-10-28", "18:30", "lesson", 23, "ПРАКТИКА — общие свойства неорганических соединений"),
    ("probnik:1", "2026-10-31", "10:00", "probnik", None, "Пробник №1"),
    ("lesson:24", "2026-11-01", "10:00", "lesson", 24, "№34 — базовые задачи на растворимость"),
    ("lesson:25", "2026-11-02", "18:30", "lesson", 25, "ОВР с участием соединений марганца"),
    ("lesson:26", "2026-11-04", "18:30", "lesson", 26, "ОВР с участием соединений хрома"),
    ("lesson:27", "2026-11-07", "10:00", "lesson", 27, "№34 — базовые задачи на разложение"),
    ("lesson:28", "2026-11-09", "18:30", "lesson", 28, "ПРАКТИКА — марганец и хром"),
    ("lesson:29", "2026-11-11", "18:30", "lesson", 29, "РИО №6"),
    ("lesson:30", "2026-11-15", "10:00", "lesson", 30, "№34 — базовые задачи на пластинку"),
    ("lesson:31", "2026-11-16", "18:30", "lesson", 31, "РИО №6"),
    ("lesson:32", "2026-11-18", "18:30", "lesson", 32, "РИО №30"),
    ("lesson:33", "2026-11-22", "10:00", "lesson", 33, "№34 — базовые задачи на частицы"),
    ("lesson:34", "2026-11-23", "18:30", "lesson", 34, "РИО №30"),
    ("lesson:35", "2026-11-25", "18:30", "lesson", 35, "Введение в органическую химию"),
    ("probnik:2", "2026-11-28", "10:00", "probnik", None, "Пробник №2"),
    ("lesson:36", "2026-11-29", "10:00", "lesson", 36, "№34"),
    ("lesson:37", "2026-11-30", "18:30", "lesson", 37, "Классификация органических соединений"),
)


def ensure_course_schedule_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS course_schedule (
                schedule_key TEXT PRIMARY KEY,
                event_date TEXT NOT NULL,
                event_time TEXT NOT NULL,
                event_type TEXT NOT NULL,
                lesson_number INTEGER,
                topic TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        now = datetime.now(bot.TIMEZONE).isoformat()
        for key, event_date, event_time, event_type, lesson_number, topic in SCHEDULE:
            conn.execute(
                """
                INSERT OR IGNORE INTO course_schedule
                    (schedule_key, event_date, event_time, event_type, lesson_number,
                     topic, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (key, event_date, event_time, event_type, lesson_number, topic, now, now),
            )
        conn.commit()


def _schedule_rows(start_date=None, end_date=None, event_type=None, limit=None):
    clauses = ["active = 1"]
    params = []
    if start_date:
        clauses.append("event_date >= ?")
        params.append(str(start_date))
    if end_date:
        clauses.append("event_date <= ?")
        params.append(str(end_date))
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    sql = (
        "SELECT schedule_key, event_date, event_time, event_type, lesson_number, topic "
        "FROM course_schedule WHERE " + " AND ".join(clauses) +
        " ORDER BY event_date, event_time"
    )
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(sql, params).fetchall()


def _events_on(day):
    return _schedule_rows(start_date=day.isoformat(), end_date=day.isoformat())


def _next_lesson(day=None):
    day = day or datetime.now(bot.TIMEZONE).date()
    rows = _schedule_rows(start_date=day.isoformat(), event_type="lesson", limit=1)
    return rows[0] if rows else None


def _format_date(value):
    dt = datetime.strptime(value, "%Y-%m-%d")
    return f"{WEEKDAYS[dt.weekday()]} {dt.strftime('%d.%m')}"


def _event_line(row):
    _key, event_date, event_time, event_type, lesson_number, topic = row
    when = f"{_format_date(event_date)} · {event_time}"
    if event_type == "lesson":
        return f"📚 {when} — урок №{lesson_number}\n   {topic}"
    return f"📝 {when} — {topic}"


def schedule_text(month=None):
    now = datetime.now(bot.TIMEZONE)
    if month in (9, 10, 11):
        start = f"2026-{month:02d}-01"
        end = f"2026-{month:02d}-31"
        rows = _schedule_rows(start_date=start, end_date=end)
        title = f"📅 Расписание · {MONTH_NAMES[month]} 2026"
    else:
        rows = _schedule_rows(start_date=now.date().isoformat(), limit=10)
        title = "📅 Ближайшие занятия"
    lines = [title, ""]
    if not rows:
        lines.append("Пока расписание на этот период не загружено.")
    else:
        lines.extend(_event_line(row) for row in rows)
    lines.extend(["", "Если занятие переносится, в кабинете будет показано обновлённое время и дата."])
    return "\n\n".join(lines)


def schedule_markup():
    rows = [
        [
            InlineKeyboardButton("Сентябрь", callback_data="triv:studentcab:schedule:9"),
            InlineKeyboardButton("Октябрь", callback_data="triv:studentcab:schedule:10"),
            InlineKeyboardButton("Ноябрь", callback_data="triv:studentcab:schedule:11"),
        ],
        [InlineKeyboardButton("Ближайшие", callback_data="triv:studentcab:schedule")],
        [InlineKeyboardButton("← В мой кабинет", callback_data="triv:studentcab:home")],
    ]
    contact = live49._contact_button()
    if contact:
        rows.append([contact])
    return InlineKeyboardMarkup(rows)


# Добавляем расписание в личный кабинет ученика.
_original_student_home_markup = live49._student_home_markup


def student_home_markup_with_schedule():
    base = _original_student_home_markup()
    rows = [list(row) for row in base.inline_keyboard]
    insert_at = 1 if rows else 0
    rows.insert(insert_at, [InlineKeyboardButton("📅 Расписание", callback_data="triv:studentcab:schedule")])
    return InlineKeyboardMarkup(rows)


live49._student_home_markup = student_home_markup_with_schedule

_original_student_home_text = live49._student_home_text


def student_home_text_with_next_lesson(student):
    text = _original_student_home_text(student)
    row = _next_lesson()
    if not row:
        return text
    _key, event_date, event_time, _event_type, lesson_number, topic = row
    block = (
        f"\n\n📅 Ближайший урок: №{lesson_number} · {_format_date(event_date)} · {event_time}\n"
        f"Тема: {topic}"
    )
    marker = "\n\nВыбирай раздел ниже 👇"
    if marker in text:
        return text.replace(marker, block + marker)
    return text + block


live49._student_home_text = student_home_text_with_next_lesson


# В ежедневном таймере в день занятия показываем время и тему.
_original_countdown_text = bot.get_countdown_text


def countdown_text_with_schedule():
    text = _original_countdown_text()
    rows = _events_on(datetime.now(bot.TIMEZONE).date())
    if not rows:
        return text
    blocks = []
    for row in rows:
        _key, _event_date, event_time, event_type, lesson_number, topic = row
        safe_topic = html.escape(str(topic))
        if event_type == "lesson":
            blocks.append(
                f"📚 <b>Сегодня на курсе</b>\n"
                f"Урок №{lesson_number} · <b>{event_time}</b>\n"
                f"{safe_topic}"
            )
        else:
            blocks.append(f"📝 <b>Сегодня</b> · <b>{event_time}</b>\n{safe_topic}")
    return text + "\n\n" + "\n\n".join(blocks)


bot.get_countdown_text = countdown_text_with_schedule


_previous_trivial_callback = live7.trivial_callback


async def combined_trivial_callback_with_schedule(update, context):
    data = str(update.callback_query.data or "") if update.callback_query else ""
    if data == "triv:studentcab:schedule" or data.startswith("triv:studentcab:schedule:"):
        await update.callback_query.answer()
        # Расписание курса не содержит персональных данных, но показываем его
        # только ученикам с привязанным Telegram и Марии в тестовом режиме.
        student = live49._student_by_telegram(update.effective_user.id)
        if not student and not bot.user_is_admin(update):
            await update.callback_query.edit_message_text(
                "📅 Расписание станет доступно после привязки Telegram к записи ученика."
            )
            return
        month = None
        if data.count(":") >= 3:
            try:
                month = int(data.rsplit(":", 1)[-1])
            except Exception:
                month = None
        await update.callback_query.edit_message_text(
            schedule_text(month), reply_markup=schedule_markup()
        )
        return
    await _previous_trivial_callback(update, context)


live7.trivial_callback = combined_trivial_callback_with_schedule


_previous_test = bot.test


async def test_with_schedule_preview(update, context):
    is_schedule = bool(context.args) and context.args[0].lower() in {"schedule", "расписание", "timetable"}
    if not is_schedule:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    await update.message.reply_text(
        "🧪 ТЕСТ — расписание видишь только ты. Ученикам ничего не отправлено.\n\n"
        + schedule_text(),
        reply_markup=schedule_markup(),
    )
    today_rows = _events_on(datetime.now(bot.TIMEZONE).date())
    if today_rows:
        await update.message.reply_text(
            "🧪 Так сегодня будет выглядеть дополнительный блок в таймере:\n\n"
            + countdown_text_with_schedule().split("\n\n")[-1],
            parse_mode="HTML",
        )


bot.test = test_with_schedule_preview


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    ensure_course_schedule_table()
    live24.main()
