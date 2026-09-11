import sqlite3

import run_bot_live68

live68 = run_bot_live68
live67 = live68.live67
live66 = live68.live66
live65 = live68.live65
live64 = live68.live64
live63 = live68.live63
live61 = live68.live61
live60 = live68.live60
live59 = live68.live59
live56 = live68.live56
live55 = live68.live55
live54 = live68.live54
live52 = live68.live52
live51 = live68.live51
live50 = live68.live50
live49 = live68.live49
live48 = live68.live48
live46 = live68.live46
live44 = live68.live44
live43 = live68.live43
live41 = live68.live41
live39 = live68.live39
live37 = live68.live37
live35 = live68.live35
live34 = live68.live34
live31 = live68.live31
live24 = live68.live24
live17 = live68.live17
bot = live68.bot
run_bot = live68.run_bot
live28 = live31.live28

# Напоминания тем, кто не ответил на опрос, отправляем за 1,5 часа до события.
live28.REMIND_BEFORE_HOURS = 1.5


async def enabled_probnik_nonresponder_dm(context, now):
    probnik_date = now.date()
    if probnik_date not in run_bot.PROBNIK_DATES:
        return

    event_dt = live28._event_datetime(probnik_date, "10:00")
    if not live28._within_reminder_window(now, event_dt):
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll_row = conn.execute(
            """
            SELECT poll_id, probnik_number
            FROM probnik_polls
            WHERE probnik_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (probnik_date.isoformat(),),
        ).fetchone()
        if not poll_row:
            return

        poll_id, probnik_number = poll_row
        answered_ids = {
            int(row[0])
            for row in conn.execute(
                "SELECT telegram_user_id FROM probnik_poll_answers WHERE poll_id = ?",
                (poll_id,),
            ).fetchall()
        }
        students = live28._active_linked_students(conn)

        for telegram_user_id, _name in students:
            telegram_user_id = int(telegram_user_id)
            if telegram_user_id in answered_ids:
                continue
            event_key = probnik_date.isoformat()
            if live28._already_reminded(conn, "probnik", event_key, telegram_user_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        f"📝 Ты ещё не отметился(ась) на пробник №{probnik_number} сегодня в 10:00.\n\n"
                        "Зайди, пожалуйста, в группу курса и выбери в опросе «✅ Буду» или «❌ Не буду»."
                    ),
                )
            except Exception as exc:
                print(f"Could not send probnik poll reminder to {telegram_user_id}: {exc}")
                continue

            live28._mark_reminded(conn, "probnik", event_key, telegram_user_id)
            conn.commit()


# По обычным урокам личные напоминания уже были активны.
# Возвращаем также личные сообщения тем, кто не ответил на опрос по пробнику.
live28._remind_probnik_nonresponders = enabled_probnik_nonresponder_dm


if __name__ == "__main__":
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
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Lesson personal no-response DMs remain enabled", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
