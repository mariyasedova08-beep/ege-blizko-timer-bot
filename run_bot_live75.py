import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live74

live74 = run_bot_live74
live73 = live74.live73
live72 = live74.live72
live71 = live74.live71
live70 = live74.live70
live69 = live74.live69
live68 = live74.live68
live67 = live74.live67
live66 = live74.live66
live65 = live74.live65
live64 = live74.live64
live63 = live74.live63
live61 = live74.live61
live60 = live74.live60
live59 = live74.live59
live56 = live74.live56
live55 = live74.live55
live54 = live74.live54
live52 = live74.live52
live51 = live74.live51
live50 = live74.live50
live49 = live74.live49
live48 = live74.live48
live46 = live74.live46
live44 = live74.live44
live43 = live74.live43
live41 = live74.live41
live39 = live74.live39
live37 = live74.live37
live35 = live74.live35
live34 = live74.live34
live31 = live74.live31
live24 = live74.live24
live17 = live74.live17
live28 = live74.live28
bot = live74.bot
run_bot = live74.run_bot
live23 = live74.live23
live7 = live74.live7
live2 = live24.live2
live18 = live24.live18

TRAFFIC_HOMEWORK_RED = 2
TRAFFIC_ABSENCE_RED = 2
TRAFFIC_PROBNIK_RED = 60
TRAFFIC_PROBNIK_YELLOW = 70
TRAFFIC_ACTIVITY_DAYS = 7


def complete_zlata_accounting_task():
    """Мария подтвердила, что первая активная задача уже выполнена."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at = COALESCE(completed_at, ?)
            WHERE task_key = ?
            """,
            (
                datetime.now(bot.TIMEZONE).isoformat(),
                live66.ZLATA_ACCOUNTING_TASK_KEY,
            ),
        )
        conn.commit()


def _attendance_absences(conn, student_id):
    rows = conn.execute(
        """
        SELECT ar.status
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.lesson_number = ar.lesson_number
        WHERE ar.student_id = ? AND s.finalized = 1
        ORDER BY s.lesson_date DESC
        LIMIT 4
        """,
        (int(student_id),),
    ).fetchall()
    return sum(1 for (status,) in rows if status == "absent")


def _homework_missing(conn, student_row, now):
    _student_id, _display, _user_name, email, coreapp_user_id, _telegram_id = student_row
    expected = live34._overdue_homework_lesson_numbers(now.date())
    if not expected:
        return 0

    submissions = conn.execute(
        """
        SELECT user_id, lower(user_email), lesson_id, lesson_name
        FROM homework_submissions
        WHERE (coalesce(user_id, '') != '' AND user_id = ?)
           OR (coalesce(user_email, '') != '' AND lower(user_email) = lower(?))
        """,
        (str(coreapp_user_id or ""), str(email or "")),
    ).fetchall()

    done = set()
    dates = run_bot.COURSE_LESSON_DATES
    for lesson_number in expected:
        previous_date = dates[lesson_number - 1]
        target_number = lesson_number + 1
        for _uid, _mail, lesson_id, lesson_name in submissions:
            if live31._submission_explicitly_matches(
                lesson_id,
                lesson_name,
                target_number,
                lesson_number,
                previous_date,
            ):
                done.add(lesson_number)
                break
    return max(0, len(expected) - len(done))


def _latest_probnik_score(student_row):
    try:
        row = live56.latest_probnik_for_student(student_row)
    except Exception:
        return None
    if not row:
        return None
    try:
        return float(row[3])
    except Exception:
        return None


def _table_exists(conn, table_name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone())


def _trainer_sessions_7d(conn, telegram_id, now):
    if telegram_id is None:
        return None
    try:
        if (now.date() - run_bot.COURSE_START_DATE).days < TRAFFIC_ACTIVITY_DAYS:
            return None
    except Exception:
        pass

    since = (now - timedelta(days=TRAFFIC_ACTIVITY_DAYS)).isoformat()
    total = 0
    for table_name in (
        "trivial_sessions",
        "acid_sessions",
        "metals_sessions",
        "oxides_sessions",
    ):
        if not _table_exists(conn, table_name):
            continue
        try:
            value = conn.execute(
                f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE telegram_user_id = ?
                  AND finished_at IS NOT NULL
                  AND finished_at >= ?
                """,
                (int(telegram_id), since),
            ).fetchone()[0]
            total += int(value or 0)
        except Exception:
            continue
    return total


def _student_traffic(student_row, now, conn):
    student_id, display_name, _user_name, _email, _coreapp_id, telegram_id = student_row
    hard = []
    soft = []

    missing_hw = _homework_missing(conn, student_row, now)
    if missing_hw >= TRAFFIC_HOMEWORK_RED:
        hard.append(f"{missing_hw} ДЗ")
    elif missing_hw == 1:
        soft.append("1 ДЗ")

    absences = _attendance_absences(conn, student_id)
    if absences >= TRAFFIC_ABSENCE_RED:
        hard.append(f"{absences} пропуска")
    elif absences == 1:
        soft.append("1 пропуск")

    score = _latest_probnik_score(student_row)
    if score is not None:
        shown = int(score) if score.is_integer() else round(score, 1)
        if score < TRAFFIC_PROBNIK_RED:
            hard.append(f"низкий пробник {shown}")
        elif score < TRAFFIC_PROBNIK_YELLOW:
            soft.append(f"пробник {shown}")

    activity = _trainer_sessions_7d(conn, telegram_id, now)
    if activity == 0:
        soft.append("нет активности")

    if hard:
        status = "red"
        reasons = hard + soft
    elif len(soft) >= 2:
        status = "red"
        reasons = soft
    elif soft:
        status = "yellow"
        reasons = soft
    else:
        status = "green"
        reasons = ["всё хорошо"]

    return {
        "status": status,
        "name": str(display_name or "Ученик").strip(),
        "reasons": reasons,
    }


def traffic_light_text():
    now = datetime.now(bot.TIMEZONE)
    rows = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for student in live34._student_rows():
            rows.append(_student_traffic(student, now, conn))

    order = {"red": 0, "yellow": 1, "green": 2}
    emoji = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
    rows.sort(key=lambda item: (order[item["status"]], item["name"].lower()))

    counts = {
        key: sum(1 for item in rows if item["status"] == key)
        for key in ("green", "yellow", "red")
    }

    lines = [
        "🚦 СВЕТОФОР ГРУППЫ",
        "",
        f"🟢 {counts['green']}   🟡 {counts['yellow']}   🔴 {counts['red']}",
        "",
    ]
    if not rows:
        lines.append("Пока нет активных учеников.")
    else:
        for item in rows:
            lines.append(
                f"{emoji[item['status']]} {item['name']} — "
                + " · ".join(item["reasons"])
            )

    lines.extend([
        "",
        "🔴 2+ ДЗ, 2+ пропуска, пробник <60 или сразу несколько сигналов",
        "🟡 1 ДЗ, 1 пропуск, пробник 60–69 или нет активности 7 дней",
        "🟢 значимых сигналов сейчас нет",
        "",
        f"Обновлено: {now.strftime('%d.%m.%Y %H:%M:%S')}",
    ])
    return "\n".join(lines)


def _traffic_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="cab:traffic")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_traffic():
    base = _previous_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:traffic"
        for row in rows
        for button in row
    ):
        rows.insert(
            max(0, len(rows) - 1),
            [InlineKeyboardButton("🚦 Светофор группы", callback_data="cab:traffic")],
        )
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_traffic

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_traffic(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    if str(query.data or "") == "cab:traffic":
        await query.answer("Обновлено")
        try:
            await query.edit_message_text(
                traffic_light_text(),
                reply_markup=_traffic_markup(),
            )
        except Exception as exc:
            if "Message is not modified" not in str(exc):
                raise
        return
    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_traffic


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
    live18.ensure_acid_reminder_table()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live73.ensure_admin_task_view_state()
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
    complete_zlata_accounting_task()
    live74.ensure_notification_catchup_tables()
    print("Completed admin task will no longer be reminded", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
