import html
import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live71

live71 = run_bot_live71
live70 = live71.live70
live69 = live71.live69
live68 = live71.live68
live67 = live71.live67
live66 = live71.live66
live65 = live71.live65
live64 = live71.live64
live63 = live71.live63
live61 = live71.live61
live60 = live71.live60
live59 = live71.live59
live56 = live71.live56
live55 = live71.live55
live54 = live71.live54
live52 = live71.live52
live51 = live71.live51
live50 = live71.live50
live49 = live71.live49
live48 = live71.live48
live46 = live71.live46
live44 = live71.live44
live43 = live71.live43
live41 = live71.live41
live39 = live71.live39
live37 = live71.live37
live35 = live71.live35
live34 = live71.live34
live31 = live71.live31
live24 = live71.live24
live17 = live71.live17
live28 = live71.live28
bot = live71.bot
run_bot = live71.run_bot
live23 = live64.live23
live7 = live64.live7


def _esc(value):
    return html.escape(str(value or ""))


def _fmt_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return str(value or "")


def _today_events(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT event_type, lesson_number, event_time, topic
            FROM course_schedule
            WHERE active = 1 AND event_date = ?
            ORDER BY event_time
            """,
            (now.date().isoformat(),),
        ).fetchall()


def _next_lesson(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT lesson_number, event_date, event_time, topic
            FROM course_schedule
            WHERE active = 1 AND event_type = 'lesson'
              AND (event_date > ? OR (event_date = ? AND event_time >= ?))
            ORDER BY event_date, event_time
            LIMIT 1
            """,
            (now.date().isoformat(), now.date().isoformat(), now.strftime("%H:%M")),
        ).fetchone()


def _most_recent_started_lesson(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT lesson_number, event_date, event_time, topic
            FROM course_schedule
            WHERE active = 1 AND event_type = 'lesson' AND event_date <= ?
            ORDER BY event_date DESC, event_time DESC
            """,
            (now.date().isoformat(),),
        ).fetchall()
    for lesson_number, event_date, event_time, topic in rows:
        try:
            event_dt = datetime.strptime(
                f"{event_date} {event_time}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=bot.TIMEZONE)
        except Exception:
            continue
        if event_dt <= now:
            return lesson_number, event_date, event_time, topic
    return None


def _lesson_poll_status(lesson_number):
    if not lesson_number:
        return None
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll = conn.execute(
            """
            SELECT poll_id
            FROM lesson_day_before_reminders
            WHERE lesson_number = ? AND poll_id IS NOT NULL
            LIMIT 1
            """,
            (int(lesson_number),),
        ).fetchone()
        if not poll:
            return None

        poll_id = poll[0]
        answers = conn.execute(
            """
            SELECT telegram_user_id, option_id
            FROM lesson_poll_answers
            WHERE poll_id = ?
            """,
            (poll_id,),
        ).fetchall()
        students = conn.execute(
            """
            SELECT telegram_user_id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик')
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
            """
        ).fetchall()

    name_by_tid = {int(tid): str(name or "Ученик") for tid, name in students if tid is not None}
    yes, no, answered_linked = [], [], set()
    unknown_answers = 0
    for telegram_id, option_id in answers:
        telegram_id = int(telegram_id)
        name = name_by_tid.get(telegram_id)
        if not name:
            unknown_answers += 1
            continue
        answered_linked.add(telegram_id)
        if int(option_id) == 0:
            yes.append(name)
        elif int(option_id) == 1:
            no.append(name)

    unanswered = [
        name for telegram_id, name in students
        if int(telegram_id) not in answered_linked
    ]
    return (
        sorted(yes, key=str.lower),
        sorted(no, key=str.lower),
        sorted(unanswered, key=str.lower),
        unknown_answers,
    )


def _current_homework(now):
    lesson = _most_recent_started_lesson(now)
    if not lesson:
        return None, []
    lesson_number, event_date, event_time, topic = lesson
    done, missing = live63._scheduled_homework_status(
        lesson_number, event_date, now
    )
    return (lesson_number, event_date, event_time, topic, len(done)), missing


def _today_tasks(now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time
            FROM admin_tasks
            WHERE completed_at IS NULL AND start_date <= ?
            ORDER BY start_date, reminder_time, id
            """,
            (now.date().isoformat(),),
        ).fetchall()


def _trainer_schedule_today(now):
    rows = []

    if now.weekday() == 4:  # пятница
        try:
            friday_time, _last_sent = live7.get_friday_settings()
        except Exception:
            friday_time = "16:00"
        rows.append((friday_time, "🧫 Тривиальные названия"))

    if now.weekday() == 5 and now.date().isoformat() <= "2027-05-29":
        rows.append(("14:00", "🧪 Кислоты и кислотные остатки"))

    if now.weekday() == 0:
        rows.append(("11:00", "🧪 Классификация оксидов"))

    if live48.METALS_CAMPAIGN_START <= now.date() <= live48.METALS_CAMPAIGN_END:
        rows.append(("18:00", "⚙️ Металлы"))

    return sorted(rows)


def _is_last_day(day):
    return (day + timedelta(days=1)).month != day.month


def _probnik_mailings(now):
    rows = []
    today = now.date()
    for index, probnik_date in enumerate(run_bot.PROBNIK_DATES, start=1):
        if today == probnik_date - timedelta(days=2):
            rows.append(("10:00", f"📝 Пробник №{index}: сообщение за 2 дня"))
        elif today == probnik_date - timedelta(days=1):
            rows.append(("10:00", f"📝 Пробник №{index}: напоминание + опрос"))
        elif today == probnik_date:
            rows.append(("с 08:30", f"✉️ Личные напоминания неответившим на пробник №{index}"))
            rows.append(("09:30", f"📝 Пробник №{index}: утреннее напоминание"))
    return rows


def _mailings_today(now, events):
    rows = [("09:00", "⏰ Ежедневный таймер курса")]

    # Общая домашка — воскресенье, вторник и суббота.
    if now.weekday() in {1, 5, 6}:
        rows.append(("19:00", "🏠 Общее напоминание про ДЗ"))

    for event_type, lesson_number, event_time, _topic in events:
        if event_type != "lesson":
            continue
        try:
            reminder = (
                datetime.strptime(event_time, "%H:%M") - timedelta(minutes=30)
            ).strftime("%H:%M")
        except Exception:
            reminder = "за 30 мин"
        rows.append((reminder, f"🎓 Напоминание об уроке №{lesson_number}"))

    tomorrow = now.date() + timedelta(days=1)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        tomorrow_lesson = conn.execute(
            """
            SELECT lesson_number
            FROM course_schedule
            WHERE active = 1 AND event_type = 'lesson' AND event_date = ?
            ORDER BY event_time LIMIT 1
            """,
            (tomorrow.isoformat(),),
        ).fetchone()
    if tomorrow_lesson:
        rows.append(("после 18:00", f"📣 Анонс + опрос к уроку №{tomorrow_lesson[0]}"))
        rows.append(("21:00", f"✉️ Личные напоминания по ДЗ к уроку №{tomorrow_lesson[0]}"))

    if now.weekday() == 6:
        rows.append(("18:00", "📊 Еженедельные отчёты ученикам"))
        rows.append(("20:30", "🚨 Проверка зоны внимания"))

    if _is_last_day(now.date()):
        rows.append(("20:00", "📅 Итоги месяца: тебе, ученикам и родителям"))

    rows.extend(_probnik_mailings(now))
    return rows


def _joined_names(names):
    return ", ".join(_esc(name) for name in names) if names else "—"


def today_text(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    events = _today_events(now)
    tasks = _today_tasks(now)
    trainers = _trainer_schedule_today(now)
    mailings = _mailings_today(now, events)

    lines = [
        "📍 <b>Сегодня</b>",
        f"{now.strftime('%d.%m.%Y')} · {now.strftime('%H:%M')}",
        "",
    ]

    lessons = [row for row in events if row[0] == "lesson"]
    if lessons:
        for _event_type, lesson_number, event_time, topic in lessons:
            lines.extend([
                f"🎓 <b>Урок №{lesson_number} · {_esc(event_time)}</b>",
                f"Тема: {_esc(topic)}",
            ])
            poll = _lesson_poll_status(lesson_number)
            if poll:
                yes, no, unanswered, unknown_answers = poll
                lines.append(f"✅ Будут ({len(yes)}): {_joined_names(yes)}")
                lines.append(f"❌ Не будут ({len(no)}): {_joined_names(no)}")
                lines.append(f"❔ Не ответили ({len(unanswered)}): {_joined_names(unanswered)}")
                if unknown_answers:
                    lines.append(f"🔗 Ответов от непривязанных аккаунтов: {unknown_answers}")
            else:
                lines.append("🗳 Опрос по этому уроку пока не создан.")
            lines.append("")
    else:
        lines.append("🎓 <b>Сегодня урока нет.</b>")
        next_lesson = _next_lesson(now)
        if next_lesson:
            lesson_number, event_date, event_time, topic = next_lesson
            lines.extend([
                f"Ближайший: №{lesson_number} · {_esc(_fmt_date(event_date))} · {_esc(event_time)}",
                f"Тема: {_esc(topic)}",
            ])
            poll = _lesson_poll_status(lesson_number)
            if poll:
                yes, no, unanswered, _unknown_answers = poll
                lines.append(
                    f"Опрос: ✅ {len(yes)} · ❌ {len(no)} · ❔ {len(unanswered)}"
                )
        lines.append("")

    homework, missing = _current_homework(now)
    lines.append("🏠 <b>ДЗ / CoreApp</b>")
    if homework:
        lesson_number, event_date, _event_time, _topic, done_count = homework
        lines.append(
            f"После урока №{lesson_number} · {_esc(_fmt_date(event_date))}: "
            f"✅ {done_count} · ⏳ {len(missing)}"
        )
        if missing:
            lines.extend(f"• {_esc(name)}" for name in missing)
        else:
            lines.append("✅ Все закрыли.")
    else:
        lines.append("Пока нет урока, по которому нужно показывать ДЗ.")
    lines.append("")

    lines.append("📣 <b>Рассылки сегодня</b>")
    if mailings:
        lines.extend(f"• {_esc(when)} — {_esc(title)}" for when, title in mailings)
    else:
        lines.append("• Дополнительных рассылок сегодня нет.")
    lines.append("")

    lines.append("🧪 <b>Тренажёры сегодня</b>")
    if trainers:
        lines.extend(f"• {_esc(when)} — {_esc(title)}" for when, title in trainers)
    else:
        lines.append("• Автоматической отправки тренажёров сегодня нет.")
    lines.append("")

    lines.append("🗒 <b>Твои задачи на сегодня</b>")
    if tasks:
        for _task_id, task_text, start_date, reminder_time in tasks:
            start_label = "сегодня" if start_date == now.date().isoformat() else f"с {_fmt_date(start_date)}"
            lines.append(
                f"• {_esc(task_text)} · {_esc(start_label)} · {_esc(reminder_time)}"
            )
    else:
        lines.append("✅ Активных задач на сегодня нет.")

    return "\n".join(lines)


def _complete_task(task_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT task_text FROM admin_tasks WHERE id = ? LIMIT 1",
            (int(task_id),),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at = COALESCE(completed_at, ?)
            WHERE id = ?
            """,
            (datetime.now(bot.TIMEZONE).isoformat(), int(task_id)),
        )
        conn.commit()
        return row[0]


def today_markup(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    rows = [[InlineKeyboardButton("🔄 Обновить", callback_data="cab:today")]]

    for task_id, task_text, _start_date, _reminder_time in _today_tasks(now)[:6]:
        label = str(task_text or "Задача")
        if len(label) > 28:
            label = label[:25] + "…"
        rows.append([
            InlineKeyboardButton(
                f"✅ {label}",
                callback_data=f"cab:todaytaskdone:{int(task_id)}",
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton("🏠 ДЗ / CoreApp", callback_data="cab:homework"),
            InlineKeyboardButton("🎓 Посещение", callback_data="cab:attendance"),
        ],
        [
            InlineKeyboardButton("🗒 Задачи", callback_data="cab:tasks"),
            InlineKeyboardButton("← В кабинет", callback_data="cab:back"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_today():
    base = _previous_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:today"
        for row in rows for button in row
    ):
        rows.insert(0, [InlineKeyboardButton("📍 Сегодня", callback_data="cab:today")])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_today

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_today(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:today":
        await query.answer()
        await query.edit_message_text(
            today_text(),
            parse_mode="HTML",
            reply_markup=today_markup(),
        )
        return

    if data.startswith("cab:todaytaskdone:"):
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            await query.answer("Не получилось определить задачу")
            return
        task_text = _complete_task(task_id)
        await query.answer("Выполнено ✅" if task_text else "Задача не найдена")
        await query.edit_message_text(
            today_text(),
            parse_mode="HTML",
            reply_markup=today_markup(),
        )
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_today


if __name__ == "__main__":
    live71.ensure_molar_access_tables()
    live70.ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
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
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live66.seed_zlata_accounting_task()
    live56.log_probnik_cabinet_audit()
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
