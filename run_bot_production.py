"""Production entrypoint for EGE БЛИЗКО.

Keeps all existing runtime patches, verifies the teacher survey before adding
post-verification features, then starts the same live90 application stack.
"""
import payment_name_aliases  # noqa: F401
import payment_delivery_hook  # noqa: F401
import payment_student_ui  # noqa: F401
import parent_cabinet  # noqa: F401
import parent_schema_compat  # noqa: F401
import parent_admin_ui  # noqa: F401
import parent_test_ui  # noqa: F401
import parent_invite_campaign  # noqa: F401
import parent_forward_to_student  # noqa: F401
import parent_home_button  # noqa: F401

import run_bot_live90 as live90


def main():
    # This check intentionally runs before nonmetals wraps survey-adjacent routers.
    live90.verify_teacher_survey_wiring()

    # Compatibility alias: live60 already exposes the live15 module used by the
    # existing metals/oxides metrics, while live79 does not export it directly.
    live90.live79.live15 = live90.live79.live60.live15

    import nonmetals_trainer
    nonmetals_trainer.install()

    live90.live79.live71.ensure_molar_access_tables()
    live90.live79.live70.ensure_health_tables()
    live90.live79.live59.ensure_coreapp_webhook_audit_table()
    live90.live79.live31.live25.ensure_lesson_day_before_table()
    live90.live79.live31.live24.ensure_probnik_poll_tables()
    live90.live79.live28.ensure_unanswered_reminder_tables()
    live90.live79.live31.live30.live3.ensure_attendance_tables()
    live90.live79.live31.live30.ensure_auto_attendance_table()
    live90.live79.live31.ensure_personal_homework_reminder_table()
    live90.live79.live17.ensure_acid_tables()
    live90.live79.live24.live18.ensure_acid_reminder_table()
    live90.live79.live34.ensure_attention_tables()
    live90.live79.live35.ensure_admin_tasks_table()
    live90.live79.ensure_task_sections()
    live90.live79.live73.ensure_admin_task_view_state()
    live90.live79.live35.seed_monday_task()
    live90.live79.live37.update_monday_task_text()
    live90.live79.live39.seed_probnik_return_task()
    live90.live79.live41.ensure_weekly_report_tables()
    live90.live79.live41.seed_current_trainers()
    live90.live79.live48.ensure_metals_tables()
    live90.live79.live48.register_metals_trainer()
    live90.live79.live60.ensure_oxides_tables()
    live90.live79.live60.register_oxides_trainer()
    nonmetals_trainer.ensure_nonmetals_tables()
    nonmetals_trainer.register_nonmetals_trainer()
    live90.live79.live43.ensure_probnik_analysis_tables()
    live90.live79.live44.enable_probnik_analysis_now()
    live90.live79.live46.ensure_monthly_auto_report_table()
    live90.live79.live50.seed_molar_mass_task()
    live90.live79.live51.ensure_course_schedule_table()
    live90.live79.live66.seed_zlata_accounting_task()
    live90.live79.live67.ensure_individual_students_table()
    live90.live79.live71.complete_molar_mass_task()
    live90.live79.live74.ensure_notification_catchup_tables()
    live90.live79.live77.ensure_lesson_feedback_tables()
    live90.live79.live78.seed_priority_tasks()
    live90.live84.seed_teacher_product_tasks()
    live90.live85.ensure_payment_tables()
    live90.payment_schedule.ensure_payment_plans()
    live90.ensure_teacher_survey_tables()
    live90.live79.live56.log_probnik_cabinet_audit()

    print("Teacher survey ready: 10 questions, anonymous admin summary", flush=True)
    print("Payment tracking ready: grade 11 Excel import, admin preview only", flush=True)
    print("Teacher product first five tasks seeded", flush=True)
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
    print(f"Oxides trainer ready: questions={len(live90.live79.live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print(f"Nonmetals trainer ready: questions={len(nonmetals_trainer.NONMETALS_BANK)}", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)

    live90.live79.live24.main()


if __name__ == "__main__":
    main()
