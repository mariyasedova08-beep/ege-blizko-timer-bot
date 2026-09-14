import threading
import teacher_product_mvp as base
import teacher_product_schedule as schedule


def main():
    base.ensure_tables()
    schedule.ensure_tables()
    threading.Thread(target=base.start_health_server, daemon=True).start()
    print("Teacher Product MVP ready: onboarding + students + schedule + transfers", flush=True)
    if not base.BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    schedule.build_app().run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
