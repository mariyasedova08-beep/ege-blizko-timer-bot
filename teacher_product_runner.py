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


def main():
    base.ensure_tables()
    schedule.ensure_tables()
    groups.ensure_tables()
    reminders.ensure_tables()
    student_reminders.ensure_tables()
    student_messaging.ensure_tables()
    payments.ensure_tables()
    subscriptions.ensure_tables()
    today_actions.ensure_tables()
    tasks.ensure_tables()
    availability_slots.ensure_tables()
    learning.ensure_tables()
    cancellations.ensure_tables()
    courses.ensure_tables()
    reports.ensure_tables()
    webapp.install_server()
    threading.Thread(target=base.start_health_server, daemon=True).start()
    print("Teacher Product MVP ready: schedule + reminders + payments + subscriptions + today-actions + tomorrow + availability-slots + homework + attendance + group-members + courses + reports + student-messaging + tasks + private voice beta", flush=True)
    if not base.BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    openai_diag.run()
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
    group_members.install(app)
    cancellations.install(app)
    courses.install(app)
    reports.install(app)
    student_messaging.install(app)
    webapp.install(app)
    student_webapp.install(app)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
