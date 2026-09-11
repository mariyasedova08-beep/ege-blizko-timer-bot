import sqlite3
from datetime import date, datetime

import run_bot_live77

live77 = run_bot_live77
live76 = live77.live76
live75 = live77.live75
live74 = live77.live74
live73 = live77.live73
live72 = live77.live72
live71 = live77.live71
live70 = live77.live70
live69 = live77.live69
live68 = live77.live68
live67 = live77.live67
live66 = live77.live66
live65 = live77.live65
live64 = live77.live64
live63 = live77.live63
live61 = live77.live61
live60 = live77.live60
live59 = live77.live59
live56 = live77.live56
live50 = live77.live50
live51 = live77.live51
live48 = live77.live48
live46 = live77.live46
live44 = live77.live44
live43 = live77.live43
live41 = live77.live41
live39 = live77.live39
live37 = live77.live37
live35 = live77.live35
live34 = live77.live34
live31 = live77.live31
live24 = live77.live24
live17 = live77.live17
live28 = live77.live28
bot = live77.bot
run_bot = live77.run_bot

PRIORITY_TASKS = (
    (
        "priority-coreapp-live-webhook-2026-09-12",
        "Проверить живой веб-хук CoreApp на реальном завершении урока",
        date(2026, 9, 12),
        "10:00",
    ),
    (
        "priority-coreapp-xlsx-history-2026-09-12",
        "Загрузить свежую XLSX-выгрузку CoreApp и проверить Лизу / урок №2",
        date(2026, 9, 12),
        "10:15",
    ),
    (
        "priority-student-cabinet-check-2026-09-12",
        "Проверить личные кабинеты у 2–3 учеников после синхронизации",
        date(2026, 9, 12),
        "12:00",
    ),
    (
        "priority-weekly-report-check-2026-09-13",
        "Проверить еженедельный отчёт ученикам после воскресной рассылки",
        date(2026, 9, 13),
        "18:15",
    ),
    (
        "priority-rotate-coreapp-secret-2026-09-14",
        "Сменить секрет CoreApp веб-хука после проверки синхронизации",
        date(2026, 9, 14),
        "11:00",
    ),
)


def seed_priority_tasks():
    live35.ensure_admin_tasks_table()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for task_key, task_text, start_date, reminder_time in PRIORITY_TASKS:
            conn.execute(
                """
                INSERT OR IGNORE INTO admin_tasks
                    (task_key, task_text, start_date, reminder_time, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_key, task_text, start_date.isoformat(), reminder_time, now),
            )
        conn.commit()


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
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
    # В live76 была временная миграция, которая на каждом рестарте снова
    # открывала задачу про Злату. Здесь её намеренно НЕ вызываем: выполненные
    # задачи теперь остаются выполненными после перезапуска бота.
    live74.ensure_notification_catchup_tables()
    live77.ensure_lesson_feedback_tables()
    seed_priority_tasks()
    live56.log_probnik_cabinet_audit()
    print("Priority admin tasks seeded", flush=True)
    print("Completed admin tasks stay completed after restart", flush=True)
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
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
