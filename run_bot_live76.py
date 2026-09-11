import sqlite3

import run_bot_live75

live75 = run_bot_live75
live74 = live75.live74
live73 = live75.live73
live72 = live75.live72
live71 = live75.live71
live70 = live75.live70
live69 = live75.live69
live68 = live75.live68
live67 = live75.live67
live66 = live75.live66
live65 = live75.live65
live64 = live75.live64
live63 = live75.live63
live61 = live75.live61
live60 = live75.live60
live59 = live75.live59
live56 = live75.live56
live55 = live75.live55
live54 = live75.live54
live52 = live75.live52
live51 = live75.live51
live50 = live75.live50
live49 = live75.live49
live48 = live75.live48
live46 = live75.live46
live44 = live75.live44
live43 = live75.live43
live41 = live75.live41
live39 = live75.live39
live37 = live75.live37
live35 = live75.live35
live34 = live75.live34
live31 = live75.live31
live24 = live75.live24
live17 = live75.live17
live28 = live75.live28
bot = live75.bot
run_bot = live75.run_bot


def restore_zlata_accounting_task():
    """Вернуть задачу «Внести Злату в бухгалтерию» в активные."""
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at = NULL
            WHERE task_key = ?
            """,
            (live66.ZLATA_ACCOUNTING_TASK_KEY,),
        )
        conn.commit()
        return int(cur.rowcount or 0)


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
    live24.live18.ensure_acid_reminder_table()
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
    restored = restore_zlata_accounting_task()
    live74.ensure_notification_catchup_tables()
    print(f"Zlata accounting task restored: rows={restored}", flush=True)
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
