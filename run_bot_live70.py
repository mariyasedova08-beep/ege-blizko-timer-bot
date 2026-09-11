import sqlite3
from datetime import datetime, timedelta

import run_bot_live69

live69 = run_bot_live69
live68 = live69.live68
live67 = live69.live67
live66 = live69.live66
live65 = live69.live65
live64 = live69.live64
live63 = live69.live63
live61 = live69.live61
live60 = live69.live60
live59 = live69.live59
live56 = live69.live56
live55 = live69.live55
live54 = live69.live54
live52 = live69.live52
live51 = live69.live51
live50 = live69.live50
live49 = live69.live49
live48 = live69.live48
live46 = live69.live46
live44 = live69.live44
live43 = live69.live43
live41 = live69.live41
live39 = live69.live39
live37 = live69.live37
live35 = live69.live35
live34 = live69.live34
live31 = live69.live31
live24 = live69.live24
live17 = live69.live17
bot = live69.bot
run_bot = live69.run_bot
live28 = live69.live28

HEARTBEAT_KEY = "telegram-bot-heartbeat"
ERROR_COOLDOWN_MINUTES = 30
RECOVERY_GAP_MINUTES = 10


def ensure_health_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_health_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_error_alerts (
                error_key TEXT PRIMARY KEY,
                last_alert_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _read_state(key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            "SELECT state_value, updated_at FROM bot_health_state WHERE state_key = ? LIMIT 1",
            (key,),
        ).fetchone()


def _write_state(key, value):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO bot_health_state (state_key, state_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                state_value = excluded.state_value,
                updated_at = excluded.updated_at
            """,
            (key, str(value or ""), now),
        )
        conn.commit()


def _should_alert_error(error_key, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT last_alert_at FROM bot_error_alerts WHERE error_key = ? LIMIT 1",
            (error_key,),
        ).fetchone()
        if row and row[0]:
            try:
                previous = datetime.fromisoformat(row[0])
                if previous.tzinfo is None:
                    previous = previous.replace(tzinfo=bot.TIMEZONE)
                if now - previous < timedelta(minutes=ERROR_COOLDOWN_MINUTES):
                    return False
            except Exception:
                pass
        conn.execute(
            """
            INSERT INTO bot_error_alerts (error_key, last_alert_at)
            VALUES (?, ?)
            ON CONFLICT(error_key) DO UPDATE SET last_alert_at = excluded.last_alert_at
            """,
            (error_key, now.isoformat()),
        )
        conn.commit()
    return True


async def _heartbeat(context):
    _write_state(HEARTBEAT_KEY, "ok")


async def _error_handler(update, context):
    error = getattr(context, "error", None)
    error_name = type(error).__name__ if error is not None else "UnknownError"
    now = datetime.now(bot.TIMEZONE)
    print(f"BOT ERROR CAPTURED: {error_name}", flush=True)

    if not _should_alert_error(error_name, now):
        return

    admin_id = bot.get_admin_id()
    if not admin_id:
        return
    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "⚠️ <b>ЕГЭ БЛИЗКО · техническое уведомление</b>\n\n"
                f"Бот зафиксировал внутреннюю ошибку: <b>{error_name}</b>.\n"
                "Она записана в технических логах. Автоматический внешний контроль проверит сервис и, если причина очевидна, исправит её.\n\n"
                "Одинаковая ошибка повторно не присылается 30 минут, чтобы не спамить."
            ),
            parse_mode="HTML",
        )
    except Exception as notify_error:
        print(f"Could not send admin error alert: {type(notify_error).__name__}", flush=True)


async def _post_init(application):
    application.add_error_handler(_error_handler)

    previous = _read_state(HEARTBEAT_KEY)
    now = datetime.now(bot.TIMEZONE)
    if previous and previous[1]:
        try:
            last_seen = datetime.fromisoformat(previous[1])
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=bot.TIMEZONE)
            gap = now - last_seen
        except Exception:
            gap = timedelta(0)
        if gap >= timedelta(minutes=RECOVERY_GAP_MINUTES):
            admin_id = bot.get_admin_id()
            if admin_id:
                try:
                    minutes = max(1, round(gap.total_seconds() / 60))
                    await application.bot.send_message(
                        chat_id=int(admin_id),
                        text=(
                            "✅ <b>ЕГЭ БЛИЗКО · бот снова работает</b>\n\n"
                            f"Был зафиксирован перерыв в работе примерно {minutes} мин. "
                            "Сервис снова запущен и отвечает."
                        ),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    print(f"Could not send recovery alert: {type(exc).__name__}", flush=True)

    _write_state(HEARTBEAT_KEY, "ok")
    if application.job_queue:
        application.job_queue.run_repeating(_heartbeat, interval=60, first=60)
    print("Health monitoring and admin error alerts ready", flush=True)


_original_builder = bot.Application.builder


def _builder_with_health_monitoring(*args, **kwargs):
    builder = _original_builder(*args, **kwargs)
    return builder.post_init(_post_init)


bot.Application.builder = staticmethod(_builder_with_health_monitoring)


if __name__ == "__main__":
    ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
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
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
