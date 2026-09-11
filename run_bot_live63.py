import sqlite3
from datetime import datetime

import run_bot_live61

live61 = run_bot_live61
live60 = live61.live60
live59 = live61.live59
live58 = live61.live58
live56 = live61.live56
live55 = live61.live55
live54 = live61.live54
live52 = live61.live52
live51 = live61.live51
live50 = live61.live50
live49 = live61.live49
live48 = live61.live48
live46 = live61.live46
live44 = live61.live44
live43 = live61.live43
live41 = live61.live41
live39 = live61.live39
live37 = live61.live37
live35 = live61.live35
live34 = live61.live34
live31 = live61.live31
live24 = live61.live24
live17 = live61.live17
bot = live61.bot
live23 = live34.live23


def _latest_scheduled_lesson(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT lesson_number, event_date, event_time, topic
            FROM course_schedule
            WHERE active = 1
              AND event_type = 'lesson'
              AND event_date <= ?
            ORDER BY event_date DESC, event_time DESC
            LIMIT 1
            """,
            (now.date().isoformat(),),
        ).fetchone()


def _scheduled_homework_status(lesson_number, lesson_date, now=None):
    now = now or datetime.now(bot.TIMEZONE)
    done_ids, done_emails = live31._target_homework_done_sets(
        int(lesson_number) + 1,
        int(lesson_number),
        datetime.strptime(lesson_date, "%Y-%m-%d").date(),
        now,
    )

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT coreapp_user_id,
                   lower(user_email),
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик')
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()

    done = []
    missing = []
    for coreapp_user_id, email, name in students:
        is_done = (
            (coreapp_user_id and str(coreapp_user_id).strip() in done_ids)
            or (email and live31._norm(email) in done_emails)
        )
        (done if is_done else missing).append(str(name or "Ученик").strip())
    return done, missing


def homework_summary_text_schedule_based():
    now = datetime.now(bot.TIMEZONE)
    lesson = _latest_scheduled_lesson(now)
    if not lesson:
        return (
            "🏠 ДЗ / CoreApp\n\n"
            "По расписанию ещё не было уроков.\n\n"
            "Для исторических завершений можно отправить свежую XLSX-выгрузку мониторинга CoreApp в личку бота."
        )

    lesson_number, event_date, event_time, topic = lesson
    done, missing = _scheduled_homework_status(lesson_number, event_date, now)
    date_text = datetime.strptime(event_date, "%Y-%m-%d").strftime("%d.%m")

    lines = [
        "🏠 ДЗ / CoreApp",
        "",
        f"Урок по расписанию: №{lesson_number} · {date_text} · {event_time}",
        f"Тема: {topic}",
        f"✅ Закрыли: {len(done)}",
        f"⏳ Пока не закрыли: {len(missing)}",
    ]
    if missing:
        lines.extend(["", "Пока не закрыли:"])
        lines.extend(f"• {name}" for name in missing)
    lines.extend([
        "",
        "Статус берётся по расписанию курса, а не по последней записи, пришедшей из CoreApp.",
        "Старые завершения догружаются свежей XLSX-выгрузкой мониторинга; новые — через webhook.",
    ])
    return "\n".join(lines)


# В кабинете Маши теперь всегда показываем последний уже состоявшийся урок по расписанию.
live23.homework_summary_text = homework_summary_text_schedule_based


if __name__ == "__main__":
    live59.ensure_coreapp_webhook_audit_table()
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
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live56.log_probnik_cabinet_audit()
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
