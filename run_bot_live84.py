import sqlite3
from datetime import date, datetime

import run_bot_live79

live79 = run_bot_live79
bot = live79.bot


TEACHER_PRODUCT_TASKS = (
    (
        "teacher-product-target-audience-2026-09-12",
        "Описать целевого пользователя универсального бота: преподаватель групп ЕГЭ/ОГЭ, его главные рутинные задачи и проблемы",
        date(2026, 9, 12),
        "10:00",
    ),
    (
        "teacher-product-five-interviews-2026-09-14",
        "Провести 5 коротких интервью с преподавателями и записать, за какие функции бота они готовы платить",
        date(2026, 9, 14),
        "10:00",
    ),
    (
        "teacher-product-survey-30-50-2026-09-15",
        "Добрать опрос преподавателей минимум до 30 завершённых анкет, цель — 50, и обновить статистику по главным болям",
        date(2026, 9, 15),
        "10:00",
    ),
    (
        "teacher-product-schedule-mvp-2026-09-16",
        "Спроектировать модуль «Расписание и переносы» как ядро продукта: создание занятий, перенос, отмена, свободные окна и уведомления ученикам",
        date(2026, 9, 16),
        "10:00",
    ),
    (
        "teacher-product-mvp-scope-2026-09-17",
        "Утвердить состав MVP универсального бота: курсы, группы, расписание, ученики, ДЗ, посещаемость, напоминания, отчёты и задачи",
        date(2026, 9, 17),
        "10:00",
    ),
    (
        "teacher-product-notification-modes-2026-09-18",
        "Спроектировать режимы сообщений ученикам: автоматически по правилам / сначала черновик / только вручную / полностью выключено",
        date(2026, 9, 18),
        "10:00",
    ),
    (
        "teacher-product-pilot-rules-2026-09-19",
        "Определить формат пилота: длительность, условия участия и 3 показателя успеха для преподавателя",
        date(2026, 9, 19),
        "10:00",
    ),
    (
        "teacher-product-results-dashboard-2026-09-20",
        "Собрать макет единого экрана результатов преподавателя: ученики, ДЗ, пробники, посещаемость, тренажёры и кому сейчас нужно внимание",
        date(2026, 9, 20),
        "10:00",
    ),
    (
        "teacher-product-recruit-pilots-2026-09-21",
        "Пригласить 3 преподавателей в закрытый пилот универсального бота",
        date(2026, 9, 21),
        "10:00",
    ),
    (
        "teacher-product-price-test-2026-09-22",
        "Проверить ценовую гипотезу на преподавателях: базовый тариф 490 ₽ и тариф с автоматизациями 790–990 ₽ в месяц",
        date(2026, 9, 22),
        "10:00",
    ),
    (
        "teacher-product-onboarding-2026-09-24",
        "Продумать онбординг нового преподавателя так, чтобы базовую настройку бота можно было пройти за 10–15 минут",
        date(2026, 9, 24),
        "10:00",
    ),
    (
        "teacher-product-positioning-offer-2026-09-26",
        "Собрать оффер продукта вокруг позиционирования «Персональный администратор преподавателя в Telegram»: ты преподаёшь — бот занимается организацией",
        date(2026, 9, 26),
        "10:00",
    ),
)


def seed_teacher_product_tasks():
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for task_key, task_text, start_date, reminder_time in TEACHER_PRODUCT_TASKS:
            conn.execute(
                """
                INSERT OR IGNORE INTO admin_tasks
                    (task_key, task_text, start_date, reminder_time, created_at, task_kind)
                VALUES (?, ?, ?, ?, ?, 'task')
                """,
                (task_key, task_text, start_date.isoformat(), reminder_time, now),
            )
        # The target-audience task was completed on 12 Sep: the ICP was built
        # from the teacher survey and saved as the working product portrait.
        conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at = COALESCE(completed_at, ?)
            WHERE task_key = ?
            """,
            (now, "teacher-product-target-audience-2026-09-12"),
        )
        conn.commit()


if __name__ == "__main__":
    live79.live71.ensure_molar_access_tables()
    live79.live70.ensure_health_tables()
    live79.live59.ensure_coreapp_webhook_audit_table()
    live79.live31.live25.ensure_lesson_day_before_table()
    live79.live31.live24.ensure_probnik_poll_tables()
    live79.live28.ensure_unanswered_reminder_tables()
    live79.live31.live30.live3.ensure_attendance_tables()
    live79.live31.live30.ensure_auto_attendance_table()
    live79.live31.ensure_personal_homework_reminder_table()
    live79.live17.ensure_acid_tables()
    live79.live24.live18.ensure_acid_reminder_table()
    live79.live34.ensure_attention_tables()
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    live79.live73.ensure_admin_task_view_state()
    live79.live35.seed_monday_task()
    live79.live37.update_monday_task_text()
    live79.live39.seed_probnik_return_task()
    live79.live41.ensure_weekly_report_tables()
    live79.live41.seed_current_trainers()
    live79.live48.ensure_metals_tables()
    live79.live48.register_metals_trainer()
    live79.live60.ensure_oxides_tables()
    live79.live60.register_oxides_trainer()
    live79.live43.ensure_probnik_analysis_tables()
    live79.live44.enable_probnik_analysis_now()
    live79.live46.ensure_monthly_auto_report_table()
    live79.live50.seed_molar_mass_task()
    live79.live51.ensure_course_schedule_table()
    live79.live66.seed_zlata_accounting_task()
    live79.live67.ensure_individual_students_table()
    live79.live71.complete_molar_mass_task()
    live79.live74.ensure_notification_catchup_tables()
    live79.live77.ensure_lesson_feedback_tables()
    live79.live78.seed_priority_tasks()
    seed_teacher_product_tasks()
    live79.live56.log_probnik_cabinet_audit()
    print("Teacher product survey-driven tasks seeded", flush=True)
    print("Admin tasks separated: active / completed / content / technical", flush=True)
    print("Admin current-task table shows first seven tasks", flush=True)
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
    print(f"Oxides trainer ready: questions={len(live79.live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live79.live24.main()
