"""Single-occurrence lesson cancellations for PREPODMIN.

A cancellation removes only one concrete occurrence from the actual schedule.
The weekly template remains intact. Cancellations are respected by Today/Tomorrow,
availability slots, attendance, package write-offs, teacher/student reminders and
schedule previews. Linked students receive an immediate cancellation message.
"""
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_today as today
import teacher_product_reminders as reminders
import teacher_product_student_reminders as student_reminders

_installed = False
_patched = False

_original_individual_today = None
_original_group_today = None
_original_individual_reminder_events = None
_original_group_reminder_events = None
_original_schedule_upcoming = None
_original_group_upcoming = None
_original_current_start = None


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_lesson_cancellations (
                teacher_telegram_user_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL CHECK(lesson_kind IN ('individual','group')),
                schedule_slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                actual_date TEXT NOT NULL,
                actual_time TEXT NOT NULL,
                cancelled_at TEXT NOT NULL,
                PRIMARY KEY(
                    teacher_telegram_user_id,
                    lesson_kind,
                    schedule_slot_id,
                    occurrence_key
                )
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_lesson_cancellations_actual
            ON teacher_lesson_cancellations(
                teacher_telegram_user_id, actual_date, actual_time
            );
            """
        )
        conn.commit()


def is_cancelled(uid, kind, slot_id, occurrence_key):
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM teacher_lesson_cancellations
            WHERE teacher_telegram_user_id=?
              AND lesson_kind=?
              AND schedule_slot_id=?
              AND occurrence_key=?
            LIMIT 1
            """,
            (int(uid), str(kind), int(slot_id), str(occurrence_key)),
        ).fetchone()
    return bool(row)


def _save_cancel(uid, event):
    ensure_tables()
    now = datetime.now(schedule.tz(uid)).isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teacher_lesson_cancellations(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,
                occurrence_key,actual_date,actual_time,cancelled_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                int(uid),
                event["kind"],
                int(event["slot_id"]),
                event["occurrence_key"],
                event["actual_date"].isoformat(),
                event["actual_time"],
                now,
            ),
        )
        conn.commit()


def _slot(uid, kind, slot_id):
    return (
        schedule.slot(uid, slot_id)
        if kind == "individual"
        else groups.group_slot(uid, slot_id)
    )


def _move(uid, kind, slot_id, occurrence_key):
    table = "schedule_moves" if kind == "individual" else "group_schedule_moves"
    with base.db() as conn:
        return conn.execute(
            f"""
            SELECT original_date,new_date,new_time
            FROM {table}
            WHERE teacher_telegram_user_id=?
              AND schedule_slot_id=?
              AND original_date=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(uid), int(slot_id), occurrence_key),
        ).fetchone()


def _event_from_occurrence(uid, kind, slot_id, occurrence_key):
    row = _slot(uid, kind, slot_id)
    if not row:
        return None
    try:
        original_date = date.fromisoformat(str(occurrence_key))
    except Exception:
        return None

    move = _move(uid, kind, slot_id, original_date.isoformat())
    actual_date = date.fromisoformat(move["new_date"]) if move else original_date
    actual_time = move["new_time"] if move else row["time_text"]
    moved = bool(move)

    if kind == "individual":
        name = row["student_name"]
        person_id = int(row["student_id"])
    else:
        name = row["group_name"]
        person_id = int(row["group_id"])

    return {
        "kind": kind,
        "slot_id": int(slot_id),
        "person_id": person_id,
        "name": name,
        "occurrence_key": original_date.isoformat(),
        "original_date": original_date,
        "original_time": row["time_text"],
        "actual_date": actual_date,
        "actual_time": actual_time,
        "moved": moved,
    }


def _move_rows(uid, kind, start_day, end_day):
    table = "schedule_moves" if kind == "individual" else "group_schedule_moves"
    with base.db() as conn:
        return conn.execute(
            f"""
            SELECT schedule_slot_id,original_date,new_date,new_time
            FROM {table}
            WHERE teacher_telegram_user_id=?
              AND (
                    (original_date>=? AND original_date<=?)
                 OR (new_date>=? AND new_date<=?)
              )
            ORDER BY new_date,new_time,id
            """,
            (
                int(uid),
                start_day.isoformat(),
                end_day.isoformat(),
                start_day.isoformat(),
                end_day.isoformat(),
            ),
        ).fetchall()


def _upcoming_occurrences(uid, kind=None, days=45):
    now = datetime.now(schedule.tz(uid))
    start_day = now.date()
    end_day = start_day + timedelta(days=int(days))
    end_dt = datetime.combine(
        end_day,
        datetime.max.time().replace(microsecond=0),
        tzinfo=schedule.tz(uid),
    )
    result = []
    seen = set()

    kinds = [kind] if kind in {"individual", "group"} else ["individual", "group"]
    for current_kind in kinds:
        slot_rows = schedule.slots(uid) if current_kind == "individual" else groups.group_slots(uid)
        moves = _move_rows(uid, current_kind, start_day, end_day)

        for slot_row in slot_rows:
            d = start_day
            while d <= end_day:
                if d.weekday() == int(slot_row["weekday"]):
                    key = (current_kind, int(slot_row["id"]), d.isoformat())
                    event = _event_from_occurrence(
                        uid, current_kind, int(slot_row["id"]), d.isoformat()
                    )
                    if event:
                        event_dt = datetime.combine(
                            event["actual_date"],
                            datetime.strptime(event["actual_time"], "%H:%M").time(),
                            tzinfo=schedule.tz(uid),
                        )
                        if (
                            now <= event_dt <= end_dt
                            and not is_cancelled(
                                uid, current_kind, event["slot_id"], event["occurrence_key"]
                            )
                        ):
                            result.append(event)
                            seen.add(key)
                d += timedelta(days=1)

        # Include lessons moved into the visible window from an older/farther
        # occurrence that wasn't scanned as a regular date above.
        for move in moves:
            key = (
                current_kind,
                int(move["schedule_slot_id"]),
                str(move["original_date"]),
            )
            if key in seen:
                continue
            event = _event_from_occurrence(
                uid,
                current_kind,
                int(move["schedule_slot_id"]),
                str(move["original_date"]),
            )
            if not event:
                continue
            try:
                event_dt = datetime.combine(
                    event["actual_date"],
                    datetime.strptime(event["actual_time"], "%H:%M").time(),
                    tzinfo=schedule.tz(uid),
                )
            except Exception:
                continue
            if not (now <= event_dt <= end_dt):
                continue
            if is_cancelled(uid, current_kind, event["slot_id"], event["occurrence_key"]):
                continue
            result.append(event)
            seen.add(key)

    result.sort(
        key=lambda e: (
            e["actual_date"],
            e["actual_time"],
            e["kind"],
            str(e["name"]).lower(),
        )
    )
    return result


def _occurrence_for_today_event(uid, kind, event, day):
    if not event.get("moved"):
        return day.isoformat()
    table = "schedule_moves" if kind == "individual" else "group_schedule_moves"
    with base.db() as conn:
        row = conn.execute(
            f"""
            SELECT original_date
            FROM {table}
            WHERE teacher_telegram_user_id=?
              AND schedule_slot_id=?
              AND new_date=?
              AND new_time=?
            ORDER BY
              CASE WHEN original_date=? THEN 0 ELSE 1 END,
              id DESC
            LIMIT 1
            """,
            (
                int(uid),
                int(event["slot_id"]),
                day.isoformat(),
                event["time"],
                day.isoformat(),
            ),
        ).fetchone()
    return row["original_date"] if row else day.isoformat()


def _filter_today(uid, kind, day, events):
    out = []
    for event in events:
        occurrence_key = _occurrence_for_today_event(uid, kind, event, day)
        if is_cancelled(uid, kind, event["slot_id"], occurrence_key):
            continue
        out.append(event)
    return out


def _individual_today_filtered(uid, day):
    return _filter_today(
        uid,
        "individual",
        day,
        _original_individual_today(uid, day),
    )


def _group_today_filtered(uid, day):
    return _filter_today(
        uid,
        "group",
        day,
        _original_group_today(uid, day),
    )


def _individual_reminder_events_filtered(uid, now, horizon_hours=25):
    return [
        event
        for event in _original_individual_reminder_events(uid, now, horizon_hours)
        if not is_cancelled(
            uid, "individual", event["slot_id"], event["occurrence_key"]
        )
    ]


def _group_reminder_events_filtered(uid, now, horizon_hours=25):
    return [
        event
        for event in _original_group_reminder_events(uid, now, horizon_hours)
        if not is_cancelled(
            uid, "group", event["slot_id"], event["occurrence_key"]
        )
    ]


def _schedule_upcoming_filtered(uid, days=14):
    return [
        (
            event["actual_date"],
            event["actual_time"],
            event["name"],
            event["moved"],
        )
        for event in _upcoming_occurrences(uid, "individual", days)
    ]


def _group_upcoming_filtered(uid, days=14):
    return [
        (
            event["actual_date"],
            event["actual_time"],
            event["name"],
            event["moved"],
        )
        for event in _upcoming_occurrences(uid, "group", days)
    ]


def _current_start_filtered(person, message):
    if is_cancelled(
        person["teacher_id"],
        message["lesson_kind"],
        message["slot_id"],
        message["occurrence_key"],
    ):
        return None
    return _original_current_start(person, message)


def patch_runtime():
    global _patched
    global _original_individual_today, _original_group_today
    global _original_individual_reminder_events, _original_group_reminder_events
    global _original_schedule_upcoming, _original_group_upcoming
    global _original_current_start

    if _patched:
        return

    _original_individual_today = today._individual_today
    _original_group_today = today._group_today
    _original_individual_reminder_events = reminders._individual_events
    _original_group_reminder_events = reminders._group_events
    _original_schedule_upcoming = schedule.upcoming
    _original_group_upcoming = groups.group_upcoming
    _original_current_start = student_reminders.current_start

    today._individual_today = _individual_today_filtered
    today._group_today = _group_today_filtered
    reminders._individual_events = _individual_reminder_events_filtered
    reminders._group_events = _group_reminder_events_filtered
    schedule.upcoming = _schedule_upcoming_filtered
    groups.group_upcoming = _group_upcoming_filtered
    student_reminders.current_start = _current_start_filtered
    _patched = True


def _main_keyboard_with_cancel():
    rows = [list(row) for row in base.MAIN_KB.keyboard]
    rows = [
        [
            button
            for button in row
            if button.text not in {"↪️ Перенести занятие", "❌ Отменить занятие"}
        ]
        for row in rows
    ]
    rows = [row for row in rows if row]
    schedule_row = next(
        (
            i
            for i, row in enumerate(rows)
            if any(button.text == "📅 Расписание" for button in row)
        ),
        2,
    )
    rows.insert(
        schedule_row + 1,
        ["↪️ Перенести занятие", "❌ Отменить занятие"],
    )
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _kind_icon(kind):
    return "👤" if kind == "individual" else "👥"


def _callback_kind(kind):
    return "i" if kind == "individual" else "g"


def _kind_from_callback(value):
    return "individual" if value == "i" else "group" if value == "g" else None


def _event_label(event):
    label = (
        f"{_kind_icon(event['kind'])} {event['name']} • "
        f"{event['actual_date'].strftime('%d.%m')} {event['actual_time']}"
    )
    if event["moved"]:
        label += (
            f" ↪️ с {event['original_date'].strftime('%d.%m')} "
            f"{event['original_time']}"
        )
    return label[:120]


def _cancel_keyboard(uid):
    events = _upcoming_occurrences(uid, None, 45)[:40]
    rows = []
    for event in events:
        compact = event["original_date"].strftime("%Y%m%d")
        rows.append([
            InlineKeyboardButton(
                _event_label(event),
                callback_data=(
                    f"cancel:pick:{_callback_kind(event['kind'])}:"
                    f"{event['slot_id']}:{compact}"
                ),
            )
        ])
    return events, InlineKeyboardMarkup(rows) if rows else None


async def cancellation_menu(update, context):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    events, markup = _cancel_keyboard(uid)
    if not events:
        await update.message.reply_text(
            "❌ Отмена занятия\n\nНа ближайшие 45 дней занятий для отмены нет.",
            reply_markup=base.MAIN_KB,
        )
        raise ApplicationHandlerStop
    await update.message.reply_text(
        "❌ Отменить одно занятие\n\n"
        "Выбери конкретный урок. Регулярное расписание не изменится.",
        reply_markup=markup,
    )
    raise ApplicationHandlerStop


async def cancellation_pick(update, context):
    q = update.callback_query
    await q.answer()
    parts = str(q.data).split(":")
    if len(parts) != 5:
        raise ApplicationHandlerStop
    kind = _kind_from_callback(parts[2])
    try:
        slot_id = int(parts[3])
        occurrence_key = datetime.strptime(parts[4], "%Y%m%d").date().isoformat()
    except Exception:
        kind = None
    if not kind:
        await q.edit_message_text("Не удалось определить занятие. Открой отмену ещё раз.")
        raise ApplicationHandlerStop

    event = _event_from_occurrence(q.from_user.id, kind, slot_id, occurrence_key)
    if not event:
        await q.edit_message_text("Занятие не найдено. Возможно, расписание уже изменилось.")
        raise ApplicationHandlerStop
    if is_cancelled(q.from_user.id, kind, slot_id, occurrence_key):
        await q.edit_message_text("Это занятие уже отменено.")
        raise ApplicationHandlerStop

    moved_line = ""
    if event["moved"]:
        moved_line = (
            f"\n↪️ Было перенесено с "
            f"{event['original_date'].strftime('%d.%m')} {event['original_time']}."
        )
    compact = event["original_date"].strftime("%Y%m%d")
    await q.edit_message_text(
        "❌ Подтверди отмену\n\n"
        f"{_kind_icon(kind)} {event['name']}\n"
        f"📅 {event['actual_date'].strftime('%d.%m.%Y')}\n"
        f"🕒 {event['actual_time']}"
        f"{moved_line}\n\n"
        "Отменится только это занятие. Следующие регулярные уроки останутся.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ Да, отменить",
                    callback_data=f"cancel:do:{_callback_kind(kind)}:{slot_id}:{compact}",
                )
            ],
            [InlineKeyboardButton("← Не отменять", callback_data="cancel:back")],
        ]),
    )
    raise ApplicationHandlerStop


async def _notify_students(context, uid, event):
    recipients = student_reminders.recipients(
        uid,
        {
            "kind": event["kind"],
            "person_id": event["person_id"],
        },
    )
    sent = 0
    failed = 0
    for person in recipients:
        lines = [
            f"❌ {person['name']}, занятие отменено.",
            "",
            f"📅 {event['actual_date'].strftime('%d.%m.%Y')}",
            f"🕒 {event['actual_time']}",
        ]
        if event["kind"] == "group":
            lines.insert(2, f"👥 Группа: {event['name']}")
        if event["moved"]:
            lines.append("↪️ Это было перенесённое занятие.")
        lines += ["", "Следующее регулярное занятие остаётся по расписанию."]
        try:
            await context.bot.send_message(
                chat_id=int(person["telegram_user_id"]),
                text="\n".join(lines),
            )
            sent += 1
        except Exception as exc:
            failed += 1
            print(
                f"Cancellation notification failed person={person['id']}: "
                f"{type(exc).__name__}",
                flush=True,
            )
    return sent, failed, len(recipients)


async def cancellation_apply(update, context):
    q = update.callback_query
    await q.answer()
    parts = str(q.data).split(":")
    if len(parts) != 5:
        raise ApplicationHandlerStop
    kind = _kind_from_callback(parts[2])
    try:
        slot_id = int(parts[3])
        occurrence_key = datetime.strptime(parts[4], "%Y%m%d").date().isoformat()
    except Exception:
        kind = None
    if not kind:
        await q.edit_message_text("Не удалось определить занятие.")
        raise ApplicationHandlerStop

    event = _event_from_occurrence(q.from_user.id, kind, slot_id, occurrence_key)
    if not event:
        await q.edit_message_text("Занятие не найдено. Возможно, расписание уже изменилось.")
        raise ApplicationHandlerStop

    already = is_cancelled(q.from_user.id, kind, slot_id, occurrence_key)
    if not already:
        _save_cancel(q.from_user.id, event)

    sent, failed, total = (0, 0, 0)
    if not already:
        sent, failed, total = await _notify_students(
            context, q.from_user.id, event
        )

    if total == 0:
        delivery = "📨 Telegram учеников не привязан — уведомления отправлять некому."
    elif failed == 0:
        delivery = (
            "📨 Ученик уведомлён."
            if event["kind"] == "individual"
            else f"📨 Ученики уведомлены: {sent}."
        )
    else:
        delivery = f"⚠️ Уведомления: отправлено {sent}, не доставлено {failed}."

    status = "ℹ️ Это занятие уже было отменено." if already else "✅ Занятие отменено."
    await q.edit_message_text(
        f"{status}\n\n"
        f"{_kind_icon(kind)} {event['name']}\n"
        f"📅 {event['actual_date'].strftime('%d.%m.%Y')} в {event['actual_time']}\n\n"
        "Регулярное расписание сохранено. Этот интервал теперь считается свободным.\n"
        "Отменённый урок не попадёт в напоминания, посещаемость и списание занятия.\n\n"
        f"{delivery}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отменить другое", callback_data="cancel:back")
        ]]),
    )
    print(
        f"PREPODMIN lesson cancelled kind={kind} slot={slot_id} "
        f"occurrence={occurrence_key} notified={sent} failed={failed}",
        flush=True,
    )
    raise ApplicationHandlerStop


async def cancellation_back(update, context):
    q = update.callback_query
    await q.answer()
    events, markup = _cancel_keyboard(q.from_user.id)
    if not events:
        await q.edit_message_text("На ближайшие 45 дней занятий для отмены нет.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        "❌ Отменить одно занятие\n\n"
        "Выбери конкретный урок. Регулярное расписание не изменится.",
        reply_markup=markup,
    )
    raise ApplicationHandlerStop


def install(app):
    global _installed
    if _installed:
        return app
    ensure_tables()
    patch_runtime()
    base.MAIN_KB = _main_keyboard_with_cancel()

    app.add_handler(
        MessageHandler(filters.Regex(r"^❌ Отменить занятие$"), cancellation_menu),
        group=-22,
    )
    app.add_handler(
        CallbackQueryHandler(
            cancellation_pick,
            pattern=r"^cancel:pick:[ig]:\d+:\d{8}$",
        ),
        group=-22,
    )
    app.add_handler(
        CallbackQueryHandler(
            cancellation_apply,
            pattern=r"^cancel:do:[ig]:\d+:\d{8}$",
        ),
        group=-22,
    )
    app.add_handler(
        CallbackQueryHandler(cancellation_back, pattern=r"^cancel:back$"),
        group=-22,
    )

    _installed = True
    print(
        "PREPODMIN single-occurrence cancellations ready: "
        "individual + group + student notifications + free-slot recovery",
        flush=True,
    )
    return app
