import sqlite3
from datetime import datetime, timedelta, time

import run_bot_live73

live73 = run_bot_live73
live72 = live73.live72
live71 = live73.live71
live70 = live73.live70
live69 = live73.live69
live68 = live73.live68
live67 = live73.live67
live66 = live73.live66
live65 = live73.live65
live64 = live73.live64
live63 = live73.live63
live61 = live73.live61
live60 = live73.live60
live59 = live73.live59
live56 = live73.live56
live55 = live73.live55
live54 = live73.live54
live52 = live73.live52
live51 = live73.live51
live50 = live73.live50
live49 = live73.live49
live48 = live73.live48
live46 = live73.live46
live44 = live73.live44
live43 = live73.live43
live41 = live73.live41
live39 = live73.live39
live37 = live73.live37
live35 = live73.live35
live34 = live73.live34
live31 = live73.live31
live24 = live73.live24
live17 = live73.live17
live28 = live73.live28
bot = live73.bot
run_bot = live73.run_bot
live23 = live73.live23
live7 = live73.live7
live2 = live24.live2
live18 = live24.live18


def ensure_notification_catchup_tables():
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_catchup_state (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                enabled_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_delivery_guard (
                event_key TEXT PRIMARY KEY,
                scheduled_at TEXT NOT NULL,
                claimed_at TEXT,
                sent_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO notification_catchup_state (id, enabled_at) VALUES (1, ?)",
            (now,),
        )
        conn.commit()


def _enabled_at():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT enabled_at FROM notification_catchup_state WHERE id = 1"
        ).fetchone()
    try:
        value = datetime.fromisoformat(row[0])
        if value.tzinfo is None:
            value = value.replace(tzinfo=bot.TIMEZONE)
        return value
    except Exception:
        return datetime.now(bot.TIMEZONE)


def _scheduled(day, hhmm):
    hour, minute = map(int, hhmm.split(":", 1))
    return datetime.combine(day, time(hour, minute), tzinfo=bot.TIMEZONE)


def _already_delivered(event_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT sent_at FROM notification_delivery_guard WHERE event_key = ?",
            (event_key,),
        ).fetchone()
    return bool(row and row[0])


def _claim_delivery(event_key, scheduled_at):
    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT claimed_at, sent_at FROM notification_delivery_guard WHERE event_key = ?",
            (event_key,),
        ).fetchone()
        if row and row[1]:
            return False
        if row and row[0]:
            try:
                claimed = datetime.fromisoformat(row[0])
                if claimed.tzinfo is None:
                    claimed = claimed.replace(tzinfo=bot.TIMEZONE)
                if now - claimed < timedelta(minutes=5):
                    return False
            except Exception:
                pass
            conn.execute(
                "UPDATE notification_delivery_guard SET claimed_at = ?, scheduled_at = ? WHERE event_key = ?",
                (now.isoformat(), scheduled_at.isoformat(), event_key),
            )
            conn.commit()
            return True
        conn.execute(
            "INSERT INTO notification_delivery_guard (event_key, scheduled_at, claimed_at) VALUES (?, ?, ?)",
            (event_key, scheduled_at.isoformat(), now.isoformat()),
        )
        conn.commit()
        return True


def _release_claim(event_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "DELETE FROM notification_delivery_guard WHERE event_key = ? AND sent_at IS NULL",
            (event_key,),
        )
        conn.commit()


def _mark_delivered(event_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE notification_delivery_guard SET sent_at = ? WHERE event_key = ?",
            (datetime.now(bot.TIMEZONE).isoformat(), event_key),
        )
        conn.commit()


async def _send_once(event_key, scheduled_at, sender):
    if _already_delivered(event_key) or not _claim_delivery(event_key, scheduled_at):
        return False
    try:
        await sender()
    except Exception:
        _release_claim(event_key)
        raise
    _mark_delivered(event_key)
    return True


def _eligible(scheduled_at, now, hours):
    age = now - scheduled_at
    return scheduled_at >= _enabled_at() and timedelta(0) <= age <= timedelta(hours=hours)


# Exact-time jobs are wrapped so normal delivery and catch-up share one persistent guard.
_original_daily_countdown = bot.daily_countdown
_original_homework = bot.daily_homework_reminder
_original_lesson_reminder = run_bot.send_lesson_reminder


async def tracked_daily_countdown(context):
    now = datetime.now(bot.TIMEZONE)
    key = f"countdown:{now.date().isoformat()}"
    due = _scheduled(now.date(), "09:00")
    async def sender():
        await _original_daily_countdown(context)
    if bot.os.getenv("CHAT_ID"):
        await _send_once(key, due, sender)


async def tracked_homework(context):
    now = datetime.now(bot.TIMEZONE)
    key = f"homework-group:{now.date().isoformat()}"
    due = _scheduled(now.date(), "19:00")
    async def sender():
        await _original_homework(context)
    if bot.os.getenv("CHAT_ID"):
        await _send_once(key, due, sender)


def _lesson_for_day(day):
    try:
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            return conn.execute(
                """
                SELECT lesson_number, event_time, topic
                FROM course_schedule
                WHERE active = 1 AND event_type = 'lesson' AND event_date = ?
                ORDER BY event_time LIMIT 1
                """,
                (day.isoformat(),),
            ).fetchone()
    except Exception:
        return None


async def tracked_lesson_reminder(context):
    now = datetime.now(bot.TIMEZONE)
    row = _lesson_for_day(now.date())
    if not row:
        await _original_lesson_reminder(context)
        return
    lesson_number, event_time, _topic = row
    due = _scheduled(now.date(), event_time) - timedelta(minutes=30)
    key = f"lesson-reminder:{now.date().isoformat()}:{lesson_number}"
    async def sender():
        await _original_lesson_reminder(context)
    if bot.os.getenv("CHAT_ID"):
        await _send_once(key, due, sender)


def _probnik_kind_for_day(day):
    for probnik_date in run_bot.PROBNIK_DATES:
        if day == probnik_date - timedelta(days=2):
            return probnik_date, "thursday"
        if day == probnik_date - timedelta(days=1):
            return probnik_date, "friday"
    return None, None


async def tracked_probnik_daily(context):
    now = datetime.now(bot.TIMEZONE)
    probnik_date, kind = _probnik_kind_for_day(now.date())
    if not probnik_date:
        return
    key = f"probnik-{kind}:{probnik_date.isoformat()}"
    due = _scheduled(now.date(), "10:00")
    async def sender():
        ok, error = await run_bot.send_probnik_bundle(context, probnik_date, kind)
        if not ok:
            raise RuntimeError(error or "probnik bundle not sent")
    await _send_once(key, due, sender)


async def tracked_probnik_saturday(context):
    now = datetime.now(bot.TIMEZONE)
    if now.date() not in run_bot.PROBNIK_DATES:
        return
    key = f"probnik-saturday:{now.date().isoformat()}"
    due = _scheduled(now.date(), "09:30")
    async def sender():
        ok, error = await live2.send_probnik_saturday_reminder(context, now.date())
        if not ok:
            raise RuntimeError(error or "probnik saturday reminder not sent")
    await _send_once(key, due, sender)


bot.daily_countdown = tracked_daily_countdown
bot.daily_homework_reminder = tracked_homework
run_bot.send_lesson_reminder = tracked_lesson_reminder
run_bot.probnik_daily_reminder = tracked_probnik_daily
live2.probnik_saturday_reminder = tracked_probnik_saturday


async def _catchup_countdown(context, now):
    due = _scheduled(now.date(), "09:00")
    if not _eligible(due, now, 12) or not bot.os.getenv("CHAT_ID"):
        return
    key = f"countdown:{now.date().isoformat()}"
    async def sender():
        await _original_daily_countdown(context)
    if await _send_once(key, due, sender):
        print(f"Catch-up sent {key}", flush=True)


async def _catchup_homework(context, now):
    # Existing JobQueue days=(0,2,6) means Sunday, Tuesday, Saturday.
    if now.weekday() not in {1, 5, 6}:
        return
    due = _scheduled(now.date(), "19:00")
    if not _eligible(due, now, 5) or not bot.os.getenv("CHAT_ID"):
        return
    key = f"homework-group:{now.date().isoformat()}"
    async def sender():
        await _original_homework(context)
    if await _send_once(key, due, sender):
        print(f"Catch-up sent {key}", flush=True)


async def _catchup_lesson(context, now):
    row = _lesson_for_day(now.date())
    if not row or not bot.os.getenv("CHAT_ID"):
        return
    lesson_number, event_time, topic = row
    start_at = _scheduled(now.date(), event_time)
    due = start_at - timedelta(minutes=30)
    if due < _enabled_at() or not (due <= now < start_at):
        return
    key = f"lesson-reminder:{now.date().isoformat()}:{lesson_number}"
    minutes = max(1, int((start_at - now).total_seconds() // 60))
    async def sender():
        await context.bot.send_message(
            chat_id=int(bot.os.getenv("CHAT_ID")),
            message_thread_id=bot.get_target_thread_id(),
            text=(
                f"Начинаем уже через {minutes} мин 💗\n\n"
                f"Урок №{lesson_number} · {event_time}\n"
                f"{topic}"
            ),
        )
    if await _send_once(key, due, sender):
        print(f"Catch-up sent {key}", flush=True)


async def _catchup_probnik(context, now):
    probnik_date, kind = _probnik_kind_for_day(now.date())
    if probnik_date:
        due = _scheduled(now.date(), "10:00")
        if _eligible(due, now, 12):
            key = f"probnik-{kind}:{probnik_date.isoformat()}"
            async def sender():
                ok, error = await run_bot.send_probnik_bundle(context, probnik_date, kind)
                if not ok:
                    raise RuntimeError(error or "probnik bundle not sent")
            if await _send_once(key, due, sender):
                print(f"Catch-up sent {key}", flush=True)

    if now.date() in run_bot.PROBNIK_DATES:
        due = _scheduled(now.date(), "09:30")
        # Do not send a stale "today at 10:00" reminder after the mock exam has started.
        if due >= _enabled_at() and due <= now < _scheduled(now.date(), "10:00"):
            key = f"probnik-saturday:{now.date().isoformat()}"
            async def sender_sat():
                ok, error = await live2.send_probnik_saturday_reminder(context, now.date())
                if not ok:
                    raise RuntimeError(error or "probnik saturday reminder not sent")
            if await _send_once(key, due, sender_sat):
                print(f"Catch-up sent {key}", flush=True)


def _latest_weekday(now, weekday, hhmm):
    day = now.date() - timedelta(days=(now.weekday() - weekday) % 7)
    due = _scheduled(day, hhmm)
    if due > now:
        day -= timedelta(days=7)
        due = _scheduled(day, hhmm)
    return day, due


async def _catchup_trivial(context, now):
    friday_time, last_sent = live7.get_friday_settings()
    day, due = _latest_weekday(now, 4, friday_time)
    # Existing last_sent is already persistent, so this also recovers today's missed message
    # immediately on the first rollout of catch-up protection.
    if now - due > timedelta(hours=8) or last_sent == day.isoformat():
        return
    if await live7.send_trivial_announcement(context):
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                "UPDATE trivial_settings SET last_friday_sent = ?, updated_at = ? WHERE id = 1",
                (day.isoformat(), datetime.now(bot.TIMEZONE).isoformat()),
            )
            conn.commit()
        print(f"Catch-up sent trivial:{day.isoformat()}", flush=True)


async def _catchup_acid(context, now):
    day, due = _latest_weekday(now, 5, live18.ACID_REMINDER_TIME)
    if not _eligible(due, now, 10):
        return
    if day > live18.ACID_REMINDER_END or live18.get_last_acid_reminder_date() == day.isoformat():
        return
    if await live18.send_acid_saturday_reminder(context):
        live18.set_last_acid_reminder_date(day.isoformat())
        print(f"Catch-up sent acid:{day.isoformat()}", flush=True)


async def _catchup_oxides(context, now):
    day, due = _latest_weekday(now, live60.OXIDES_REMINDER_WEEKDAY, "11:00")
    if not _eligible(due, now, 12):
        return
    key = day.isoformat()
    if live60._weekly_already_sent(key):
        return
    if await live60.send_oxides_announcement(context):
        live60._mark_weekly_sent(key)
        print(f"Catch-up sent oxides:{key}", flush=True)


async def _catchup_metals(context, now):
    day = now.date()
    if not (live48.METALS_CAMPAIGN_START <= day <= live48.METALS_CAMPAIGN_END):
        return
    due = _scheduled(day, "18:00")
    if not _eligible(due, now, 6):
        return
    key = day.isoformat()
    if live48._campaign_already_sent(key):
        return
    if await live48.send_metals_announcement(context, day):
        live48._mark_campaign_sent(key)
        print(f"Catch-up sent metals:{key}", flush=True)


async def _catchup_weekly_reports(context, now):
    day, due = _latest_weekday(now, live41.WEEKLY_REPORT_WEEKDAY, "18:00")
    if not _eligible(due, now, 18):
        return
    report_now = due
    markup = await live41._weekly_report_markup(context)
    for student_row in live34._student_rows():
        student_id = int(student_row[0])
        telegram_id = student_row[5]
        if telegram_id is None or live41._already_sent(student_id, report_now):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=live41.weekly_report_text(student_row, report_now),
                reply_markup=markup,
            )
        except Exception as exc:
            print(f"Weekly catch-up failed student={student_id}: {type(exc).__name__}", flush=True)
            continue
        live41._mark_sent(student_id, report_now)
        print(f"Catch-up sent weekly-report:{day.isoformat()}:{student_id}", flush=True)


async def _catchup_attention(context, now):
    day, due = _latest_weekday(now, live34.CHILD_ALERT_WEEKDAY, live34.CHILD_ALERT_AFTER)
    if not _eligible(due, now, 12):
        return
    # The original function has its own per-student seven-day deduplication.
    await live34.send_weekly_child_alerts(context, due)


async def _catchup_monthly(context, now):
    first_this_month = now.date().replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    current_is_last = (now.date() + timedelta(days=1)).month != now.month
    if current_is_last and now.time() >= live46.MONTHLY_REPORT_AFTER:
        report_day = now.date()
    else:
        report_day = last_prev
    due = _scheduled(report_day, live46.MONTHLY_REPORT_AFTER.strftime("%H:%M"))
    if not _eligible(due, now, 24):
        return

    year, month = report_day.year, report_day.month
    month_key = live46._month_key(year, month)
    admin_id = bot.get_admin_id()
    if admin_id and not live46._sent(month_key, "admin", admin_id, 0):
        try:
            await live46._send_long(
                context,
                admin_id,
                "📅 АВТОМАТИЧЕСКИЙ ИТОГ МЕСЯЦА\n\n" + live46.live15.monthly_report_text(year, month),
            )
        except Exception as exc:
            print(f"Monthly admin catch-up failed: {type(exc).__name__}", flush=True)
        else:
            live46._mark_sent(month_key, "admin", admin_id, 0)

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = live46.live15._active_students(conn)
    markup = live46._contact_markup()
    for student in students:
        student_id = int(student[0])
        telegram_id = student[4]
        if telegram_id is not None and not live46._sent(month_key, "student", telegram_id, student_id):
            try:
                await context.bot.send_message(
                    chat_id=int(telegram_id),
                    text=live46._student_text(student, year, month),
                    reply_markup=markup,
                )
            except Exception:
                pass
            else:
                live46._mark_sent(month_key, "student", telegram_id, student_id)
        for parent_id in live46._parent_ids(student_id):
            if live46._sent(month_key, "parent", parent_id, student_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=int(parent_id),
                    text=live46._parent_text(student, year, month),
                    reply_markup=markup,
                )
            except Exception:
                continue
            live46._mark_sent(month_key, "parent", parent_id, student_id)


async def restart_catchup_tick(context):
    now = datetime.now(bot.TIMEZONE)
    checks = (
        _catchup_countdown,
        _catchup_homework,
        _catchup_lesson,
        _catchup_probnik,
        _catchup_trivial,
        _catchup_acid,
        _catchup_oxides,
        _catchup_metals,
        _catchup_weekly_reports,
        _catchup_attention,
        _catchup_monthly,
    )
    for check in checks:
        try:
            await check(context, now)
        except Exception as exc:
            print(f"Catch-up check {check.__name__} failed: {type(exc).__name__}: {exc}", flush=True)


_previous_everything_tick = live7.friday_trivial_tick


async def combined_tick_with_restart_catchup(context):
    try:
        await _previous_everything_tick(context)
    finally:
        await restart_catchup_tick(context)


live7.friday_trivial_tick = combined_tick_with_restart_catchup


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
    live18.ensure_acid_reminder_table()
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
    ensure_notification_catchup_tables()
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
