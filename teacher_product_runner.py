import threading
import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_multiday as multiday
import teacher_product_reminders as reminders
import teacher_product_payments as payments
import teacher_product_today as today
import teacher_product_tasks as tasks


def main():
    base.ensure_tables()
    schedule.ensure_tables()
    groups.ensure_tables()
    reminders.ensure_tables()
    payments.ensure_tables()
    tasks.ensure_tables()
    threading.Thread(target=base.start_health_server, daemon=True).start()
    print("Teacher Product MVP ready: schedule + reminders + payments + today + tasks + voice-ready", flush=True)
    if not base.BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    tasks.build_app().run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
