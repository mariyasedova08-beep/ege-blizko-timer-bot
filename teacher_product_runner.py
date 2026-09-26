import warnings

# python-telegram-bot emits this advisory for callback-based conversations.
# It is not a runtime failure; hide only this exact warning so real errors stay visible.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False'.*",
)

import threading
import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_multiday as multiday
import teacher_product_reminders as reminders
import teacher_product_payments as payments
import teacher_product_today as today
import teacher_product_tomorrow as tomorrow
import teacher_product_slots as availability_slots
import teacher_product_slots_clarity as slots_clarity
import teacher_product_learning as learning
import teacher_product_group_members as group_members
import teacher_product_tasks as tasks
import teacher_product_voice_beta as voice_beta
import teacher_product_openai_diag as openai_diag
import teacher_product_subscriptions as subscriptions
import teacher_product_today_actions as today_actions
import teacher_product_student_reminders as student_reminders
import teacher_product_student_messaging as student_messaging
import teacher_product_transfer_button as transfer_button
import teacher_product_transfer_enhancements as transfer_enhancements
import teacher_product_cancellations as cancellations
import teacher_product_courses as courses
import teacher_product_reports as reports
import teacher_product_webapp as webapp
import teacher_product_student_webapp as student_webapp
import teacher_product_feedback as feedback
import teacher_product_onboarding as onboarding
import teacher_product_reset as reset
import teacher_product_help as help_guide
import teacher_product_group_payments as group_payments
import teacher_product_pilot_selftest as pilot_selftest
import teacher_product_persistence_probe as persistence_probe
import teacher_product_boot_tests as boot_tests
import teacher_product_materials as materials


def main():
    base.ensure_tables()
    schedule.ensure_tables()
    groups.ensure_tables()
    reminders.ensure_tables()
    student_reminders.ensure_tables()
    student_messaging.ensure_tables()
    payments.ensure_tables()
    group_payments.ensure_tables()
    subscriptions.ensure_tables()
    today_actions.ensure_tables()
    tasks.ensure_tables()
    availability_slots.ensure_tables()
    learning.ensure_tables()
    cancellations.ensure_tables()
    courses.ensure_tables()
    reports.ensure_tables()
    feedback.ensure_tables()
    materials.ensure_tables()
    group_payments.selftest()
    pilot_selftest.run()
    boot_tests.run()
    persistence_probe.check()
    webapp.install_server()
    threading.Thread(target=base.start_health_server, daemon=True).start()
    print("PREPADMIN pilot checks passed: schedule + reminders + payments + group-payments + homework + attendance + reports + WebApps + feedback + materials; voice disabled for pilot", flush=True)
    if not base.BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    openai_diag.run()
    onboarding.patch()
    transfer_enhancements.patch()
    app = voice_beta.build_app()
    transfer_button.install(app)
    transfer_enhancements.install(app)
    student_reminders.install(app)
    subscriptions.install(app)
    today_actions.install(app)
    tomorrow.install(app)
    availability_slots.install(app)
    slots_clarity.install()
    learning.install(app)
    group_payments.install(app)
    group_members.install(app)
    cancellations.install(app)
    courses.install(app)
    reports.install(app)
    student_messaging.install(app)
    webapp.install(app)
    feedback.install(app)
    student_webapp.install(app)
    reset.install(app)
    # Install last: several feature modules rebuild MAIN_KB while installing.
    # The setup button must be added after the final product keyboard exists.
    onboarding.install(app)
    # Install after onboarding so the final keyboard contains both setup and help.
    help_guide.install(app)
    # Install last so the final reply keyboard contains the Materials button.
    materials.install(app)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
