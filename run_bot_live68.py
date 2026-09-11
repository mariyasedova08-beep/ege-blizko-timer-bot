from datetime import timedelta

import run_bot_live67

live67 = run_bot_live67
live66 = live67.live66
live65 = live67.live65
live64 = live67.live64
live63 = live67.live63
live61 = live67.live61
live60 = live67.live60
live59 = live67.live59
live56 = live67.live56
live55 = live67.live55
live54 = live67.live54
live52 = live67.live52
live51 = live67.live51
live50 = live67.live50
live49 = live67.live49
live48 = live67.live48
live46 = live67.live46
live44 = live67.live44
live43 = live67.live43
live41 = live67.live41
live39 = live67.live39
live37 = live67.live37
live35 = live67.live35
live34 = live67.live34
live31 = live67.live31
live24 = live67.live24
live17 = live67.live17
bot = live67.bot
run_bot = live34.run_bot
live2 = live24.live2


async def enabled_probnik_daily_reminder(context):
    """Restore only the scheduled group reminders around a mock exam.

    Friday still gets the existing attendance poll because live24 wraps
    run_bot.send_probnik_bundle. Probnik attention/parent escalation stays paused.
    """
    today = bot.today_moscow()
    for probnik_date in run_bot.PROBNIK_DATES:
        if today == probnik_date - timedelta(days=2):
            await run_bot.send_probnik_bundle(context, probnik_date, "thursday")
            return
        if today == probnik_date - timedelta(days=1):
            await run_bot.send_probnik_bundle(context, probnik_date, "friday")
            return


async def enabled_probnik_saturday_reminder(context):
    today = bot.today_moscow()
    if today in run_bot.PROBNIK_DATES:
        await live2.send_probnik_saturday_reminder(context, today)


# live39 paused these two scheduled group reminders. Turn them back on only.
# We intentionally keep the personal non-responder DMs, parent/attention probnik
# logic and evening admin summary in their current state.
run_bot.probnik_daily_reminder = enabled_probnik_daily_reminder
live2.probnik_saturday_reminder = enabled_probnik_saturday_reminder


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
    live66.seed_zlata_accounting_task()
    live56.log_probnik_cabinet_audit()
    live67.ensure_individual_students_table()
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs remain paused", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
