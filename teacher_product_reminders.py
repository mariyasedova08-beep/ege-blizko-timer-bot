from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_multiday as multiday

OFFSETS = [1440, 120, 60, 15]
OFFSET_LABELS = {
    1440: "за 24 часа",
    120: "за 2 часа",
    60: "за 1 час",
    15: "за 15 минут",
}


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_reminder_settings (
                teacher_telegram_user_id INTEGER PRIMARY KEY,
                minutes_1440 INTEGER NOT NULL DEFAULT 1,
                minutes_120 INTEGER NOT NULL DEFAULT 0,
                minutes_60 INTEGER NOT NULL DEFAULT 1,
                minutes_15 INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lesson_reminder_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                offset_minutes INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(
                    teacher_telegram_user_id,
                    lesson_kind,
                    schedule_slot_id,
                    occurrence_key,
                    offset_minutes
                )
            );
            CREATE INDEX IF NOT EXISTS idx_lesson_reminder_teacher
            ON lesson_reminder_sent(teacher_telegram_user_id, sent_at);
            """
        )
        conn.commit()

    # Student delivery is opt-in and has its own settings and deduplication.
    import teacher_product_student_reminders as student_reminders
    student_reminders.ensure_tables()


def ensure_settings(uid):
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teacher_reminder_settings(
                teacher_telegram_user_id, minutes_1440, minutes_120,
                minutes_60, minutes_15, updated_at
            ) VALUES(?,1,0,1,0,?)
            """,
            (int(uid), now),
        )
        conn.commit()


def get_settings(uid):
    ensure_settings(uid)
    with base.db() as conn:
        return conn.execute(
            "SELECT * FROM teacher_reminder_settings WHERE teacher_telegram_user_id=?",
            (int(uid),),
        ).fetchone()


def setting_column(minutes):
    if int(minutes) not in OFFSETS:
        raise ValueError("unsupported reminder offset")
    return f"minutes_{int(minutes)}"


def toggle_setting(uid, minutes):
    column = setting_column(minutes)
    ensure_settings(uid)
    with base.db() as conn:
        row = conn.execute(
            f"SELECT {column} AS value FROM teacher_reminder_settings WHERE teacher_telegram_user_id=?",
            (int(uid),),
        ).fetchone()
        new_value = 0 if int(row["value"]) else 1
        conn.execute(
            f"UPDATE teacher_reminder_settings SET {column}=?, updated_at=? WHERE teacher_telegram_user_id=?",
            (new_value, datetime.utcnow().isoformat(), int(uid)),
        )
        conn.commit()
    return bool(new_value)


def reminder_keyboard(uid):
    row = get_settings(uid)
    buttons = []
    for minutes in OFFSETS:
        enabled = bool(row[setting_column(minutes)])
        prefix = "✅" if enabled else "▫️"
        buttons.append([
            InlineKeyboardButton(
                f"{prefix} {OFFSET_LABELS[minutes]}",
                callback_data=f"rem:toggle:{minutes}",
            )
        ])
    import teacher_product_student_reminders as student_reminders
    buttons.append([InlineKeyboardButton(
        ("✅" if student_reminders.enabled(uid) else "▫️") + " Ученикам: за 24 часа и за 1 час",
        callback_data="srem:toggle",
    )])
    buttons.append([InlineKeyboardButton("👥 Привязать учеников / ответы", callback_data="srem:people")])
    buttons.append([InlineKeyboardButton("💬 Режим сообщений ученикам", callback_data="smsg:settings")])
    return InlineKeyboardMarkup(buttons)


def reminder_text(uid):
    row = get_settings(uid)
    enabled = [OFFSET_LABELS[m] for m in OFFSETS if bool(row[setting_column(m)])]
    if enabled:
        status = "\n".join(f"• {x}" for x in enabled)
    else:
        status = "• выключены"
    import teacher_product_student_messaging as messaging
    return (
        "🔔 Напоминания о занятиях\n\n"
        "ПРЕПАДМИН берёт занятия прямо из твоего расписания. "
        "Если занятие перенесено, напоминание придёт уже на новую дату и время.\n\n"
        "Сейчас включены:\n"
        f"{status}\n\n"
        f"💬 Глобальный режим сообщений: {messaging.MODES[messaging.get_mode(uid)][0]}\n\n"
        "Напоминания ученикам включаются отдельно как правило расписания, "
        "а способ отправки определяется глобальным режимом сообщений. "
        "Ученик получает сообщение только после привязки к боту.\n\n"
        "Нажми на вариант ниже, чтобы включить или выключить его."
    )


async def reminders_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(reminder_text(uid), reply_markup=reminder_keyboard(uid))


async def reminders_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    minutes = int(q.data.rsplit(":", 1)[1])
    toggle_setting(q.from_user.id, minutes)
    await q.edit_message_text(
        reminder_text(q.from_user.id),
        reply_markup=reminder_keyboard(q.from_user.id),
    )


def _event_dt(uid, d, time_text):
    h, m = map(int, time_text.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=schedule.tz(uid))


def _individual_events(uid, now, horizon_hours=25):
    horizon = now + timedelta(hours=horizon_hours)
    today = now.date()
    search_start = today - timedelta(days=8)
    search_end = today + timedelta(days=8)
    slots = schedule.slots(uid)
    if not slots:
        return []

    with base.db() as conn:
        move_rows = conn.execute(
            """
            SELECT schedule_slot_id, original_date, new_date, new_time
            FROM schedule_moves
            WHERE teacher_telegram_user_id=?
              AND ((original_date>=? AND original_date<=?) OR (new_date>=? AND new_date<=?))
            """,
            (int(uid), search_start.isoformat(), search_end.isoformat(), today.isoformat(), search_end.isoformat()),
        ).fetchall()
    moves = {(int(r["schedule_slot_id"]), r["original_date"]): r for r in move_rows}

    out = []
    for s in slots:
        d = search_start
        while d <= search_end:
            if d.weekday() == int(s["weekday"]):
                key = (int(s["id"]), d.isoformat())
                move = moves.get(key)
                if move:
                    event_date = date.fromisoformat(move["new_date"])
                    event_time = move["new_time"]
                    occurrence_key = d.isoformat()
                    moved = True
                else:
                    event_date = d
                    event_time = s["time_text"]
                    occurrence_key = d.isoformat()
                    moved = False
                event_dt = _event_dt(uid, event_date, event_time)
                if now <= event_dt <= horizon:
                    out.append({
                        "kind": "individual",
                        "slot_id": int(s["id"]),
                        "person_id": int(s["student_id"]),
                        "occurrence_key": occurrence_key,
                        "name": s["student_name"],
                        "event_dt": event_dt,
                        "moved": moved,
                    })
            d += timedelta(days=1)
        for (slot_id, original), move in moves.items():
            if slot_id != s["id"] or search_start.isoformat() <= original <= search_end.isoformat():
                continue
            event_dt = _event_dt(uid, date.fromisoformat(move["new_date"]), move["new_time"])
            if now <= event_dt <= horizon:
                out.append({"kind": "individual", "slot_id": s["id"], "person_id": s["student_id"],
                            "occurrence_key": original, "name": s["student_name"],
                            "event_dt": event_dt, "moved": True})
    return out


def _group_events(uid, now, horizon_hours=25):
    horizon = now + timedelta(hours=horizon_hours)
    today = now.date()
    search_start = today - timedelta(days=8)
    search_end = today + timedelta(days=8)
    slots = groups.group_slots(uid)
    if not slots:
        return []

    with base.db() as conn:
        move_rows = conn.execute(
            """
            SELECT schedule_slot_id, original_date, new_date, new_time
            FROM group_schedule_moves
            WHERE teacher_telegram_user_id=?
              AND ((original_date>=? AND original_date<=?) OR (new_date>=? AND new_date<=?))
            """,
            (int(uid), search_start.isoformat(), search_end.isoformat(), today.isoformat(), search_end.isoformat()),
        ).fetchall()
    moves = {(int(r["schedule_slot_id"]), r["original_date"]): r for r in move_rows}

    out = []
    for s in slots:
        d = search_start
        while d <= search_end:
            if d.weekday() == int(s["weekday"]):
                key = (int(s["id"]), d.isoformat())
                move = moves.get(key)
                if move:
                    event_date = date.fromisoformat(move["new_date"])
                    event_time = move["new_time"]
                    occurrence_key = d.isoformat()
                    moved = True
                else:
                    event_date = d
                    event_time = s["time_text"]
                    occurrence_key = d.isoformat()
                    moved = False
                event_dt = _event_dt(uid, event_date, event_time)
                if now <= event_dt <= horizon:
                    out.append({
                        "kind": "group",
                        "slot_id": int(s["id"]),
                        "person_id": int(s["group_id"]),
                        "occurrence_key": occurrence_key,
                        "name": s["group_name"],
                        "event_dt": event_dt,
                        "moved": moved,
                    })
            d += timedelta(days=1)
        for (slot_id, original), move in moves.items():
            if slot_id != s["id"] or search_start.isoformat() <= original <= search_end.isoformat():
                continue
            event_dt = _event_dt(uid, date.fromisoformat(move["new_date"]), move["new_time"])
            if now <= event_dt <= horizon:
                out.append({"kind": "group", "slot_id": s["id"], "person_id": s["group_id"],
                            "occurrence_key": original, "name": s["group_name"],
                            "event_dt": event_dt, "moved": True})
    return out


def _was_sent(uid, event, offset):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM lesson_reminder_sent
            WHERE teacher_telegram_user_id=? AND lesson_kind=?
              AND schedule_slot_id=? AND occurrence_key=? AND offset_minutes=?
            """,
            (
                int(uid), event["kind"], int(event["slot_id"]),
                event["occurrence_key"], int(offset),
            ),
        ).fetchone()
    return bool(row)


def _mark_sent(uid, event, offset):
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO lesson_reminder_sent(
                teacher_telegram_user_id, lesson_kind, schedule_slot_id,
                occurrence_key, offset_minutes, sent_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                int(uid), event["kind"], int(event["slot_id"]),
                event["occurrence_key"], int(offset), datetime.utcnow().isoformat(),
            ),
        )
        # Keep the dedupe table small.
        cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
        conn.execute("DELETE FROM lesson_reminder_sent WHERE sent_at<?", (cutoff,))
        conn.commit()


def _format_reminder(event, offset):
    dt = event["event_dt"]
    if offset == 1440:
        lead = "через 24 часа"
    elif offset == 120:
        lead = "через 2 часа"
    elif offset == 60:
        lead = "через 1 час"
    else:
        lead = "через 15 минут"
    icon = "👥" if event["kind"] == "group" else "👤"
    moved = "\n↪️ Это занятие было перенесено." if event["moved"] else ""
    return (
        f"🔔 Напоминание: занятие {lead}\n\n"
        f"{icon} {event['name']}\n"
        f"📅 {schedule.DAY_NAMES_FULL[dt.weekday()]}, {dt.strftime('%d.%m')}\n"
        f"🕒 {dt.strftime('%H:%M')}"
        f"{moved}"
    )


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()
    import teacher_product_student_reminders as student_reminders
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT t.telegram_user_id AS teacher_telegram_user_id, rs.minutes_1440,
                   rs.minutes_120, rs.minutes_60, rs.minutes_15
            FROM teachers t
            LEFT JOIN teacher_reminder_settings rs ON rs.teacher_telegram_user_id=t.telegram_user_id
            WHERE t.onboarding_completed_at IS NOT NULL
            """
        ).fetchall()

    for settings in rows:
        uid = int(settings["teacher_telegram_user_id"])
        now = datetime.now(schedule.tz(uid))
        events = _individual_events(uid, now) + _group_events(uid, now)
        if not events:
            continue
        if student_reminders.enabled(uid):
            for event in events:
                await student_reminders.deliver(context, uid, event, now)
        for offset in OFFSETS:
            if not bool(settings[setting_column(offset)] or 0):
                continue
            for event in events:
                target = event["event_dt"] - timedelta(minutes=offset)
                seconds_after_target = (now - target).total_seconds()
                # Job runs every minute; allow a small delivery window for deploys/network jitter.
                if 0 <= seconds_after_target < 150 and not _was_sent(uid, event, offset):
                    try:
                        await context.bot.send_message(uid, _format_reminder(event, offset))
                        _mark_sent(uid, event, offset)
                    except Exception as exc:
                        print(f"Reminder send failed uid={uid}: {type(exc).__name__}: {exc}", flush=True)


ORIGINAL_ENHANCED_STUB = schedule.enhanced_stub


async def reminder_enhanced_stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔔 Напоминания":
        return await reminders_menu_message(update, context)
    return await ORIGINAL_ENHANCED_STUB(update, context)


def build_app():
    ensure_tables()
    multiday.apply()
    schedule.enhanced_stub = reminder_enhanced_stub
    app = multiday.groups.build_app()
    app.add_handler(CallbackQueryHandler(reminders_toggle, pattern=r"^rem:toggle:(?:1440|120|60|15)$"))
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_reminders, interval=60, first=10, name="teacher_lesson_reminders")
    else:
        print("WARNING: JobQueue unavailable; lesson reminders will not run", flush=True)
    return app
