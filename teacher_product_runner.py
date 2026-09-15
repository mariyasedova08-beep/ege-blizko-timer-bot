import threading
import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_multiday as multiday
import teacher_product_reminders as reminders
import teacher_product_payments as payments
import teacher_product_today as today
import teacher_product_tasks as tasks
import teacher_product_voice_beta as voice_beta
import teacher_product_openai_diag as openai_diag
import teacher_product_subscriptions as subscriptions
import teacher_product_today_actions as today_actions


def main():
    base.ensure_tables()
    schedule.ensure_tables()
    groups.ensure_tables()
    reminders.ensure_tables()
    payments.ensure_tables()
    subscriptions.ensure_tables()
    today_actions.ensure_tables()
    tasks.ensure_tables()
    threading.Thread(target=base.start_health_server, daemon=True).start()
    print("Teacher Product MVP ready: schedule + reminders + payments + subscriptions + today-actions + tasks + private voice beta", flush=True)
    if not base.BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    openai_diag.run()
    app = voice_beta.build_app()
    subscriptions.install(app)
    today_actions.install(app)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
