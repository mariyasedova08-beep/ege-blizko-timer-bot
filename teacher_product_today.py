from datetime import date, datetime

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_payments as payments


def _individual_today(uid, today):
    events = []
    with base.db() as conn:
        slots = conn.execute(
            """
            SELECT ss.id, ss.student_id, ss.time_text, s.name AS student_name
            FROM schedule_slots ss
            JOIN students s ON s.id=ss.student_id
            WHERE ss.teacher_telegram_user_id=?
              AND ss.active=1 AND s.active=1 AND ss.weekday=?
            ORDER BY ss.time_text, lower(s.name)
            """,
            (int(uid), int(today.weekday())),
        ).fetchall()

        move_rows = conn.execute(
            """
            SELECT schedule_slot_id, original_date, new_date, new_time
            FROM schedule_moves
            WHERE teacher_telegram_user_id=?
              AND (original_date=? OR new_date=?)
            """,
            (int(uid), today.isoformat(), today.isoformat()),
        ).fetchall()
        moves_by_original = {
            int(r["schedule_slot_id"]): r
            for r in move_rows
            if r["original_date"] == today.isoformat()
        }

        for s in slots:
            move = moves_by_original.get(int(s["id"]))
            if move:
                if move["new_date"] != today.isoformat():
                    continue
                time_text = move["new_time"]
                moved = True
            else:
                time_text = s["time_text"]
                moved = False
            events.append({
                "kind": "individual",
                "slot_id": int(s["id"]),
                "student_id": int(s["student_id"]),
                "name": s["student_name"],
                "time": time_text,
                "moved": moved,
            })

        moved_in = conn.execute(
            """
            SELECT sm.schedule_slot_id, sm.new_time, ss.student_id, s.name AS student_name
            FROM schedule_moves sm
            JOIN schedule_slots ss ON ss.id=sm.schedule_slot_id
            JOIN students s ON s.id=ss.student_id
            WHERE sm.teacher_telegram_user_id=?
              AND sm.new_date=? AND sm.original_date<>?
              AND ss.active=1 AND s.active=1
            """,
            (int(uid), today.isoformat(), today.isoformat()),
        ).fetchall()
        for r in moved_in:
            events.append({
                "kind": "individual",
                "slot_id": int(r["schedule_slot_id"]),
                "student_id": int(r["student_id"]),
                "name": r["student_name"],
                "time": r["new_time"],
                "moved": True,
            })
    return events


def _group_today(uid, today):
    events = []
    with base.db() as conn:
        slots = conn.execute(
            """
            SELECT gs.id, gs.group_id, gs.time_text, g.name AS group_name
            FROM group_schedule_slots gs
            JOIN teacher_groups g ON g.id=gs.group_id
            WHERE gs.teacher_telegram_user_id=?
              AND gs.active=1 AND g.active=1 AND gs.weekday=?
            ORDER BY gs.time_text, lower(g.name)
            """,
            (int(uid), int(today.weekday())),
        ).fetchall()

        move_rows = conn.execute(
            """
            SELECT schedule_slot_id, original_date, new_date, new_time
            FROM group_schedule_moves
            WHERE teacher_telegram_user_id=?
              AND (original_date=? OR new_date=?)
            """,
            (int(uid), today.isoformat(), today.isoformat()),
        ).fetchall()
        moves_by_original = {
            int(r["schedule_slot_id"]): r
            for r in move_rows
            if r["original_date"] == today.isoformat()
        }

        for s in slots:
            move = moves_by_original.get(int(s["id"]))
            if move:
                if move["new_date"] != today.isoformat():
                    continue
                time_text = move["new_time"]
                moved = True
            else:
                time_text = s["time_text"]
                moved = False
            events.append({
                "kind": "group",
                "slot_id": int(s["id"]),
                "group_id": int(s["group_id"]),
                "name": s["group_name"],
                "time": time_text,
                "moved": moved,
            })

        moved_in = conn.execute(
            """
            SELECT gm.schedule_slot_id, gm.new_time, gs.group_id, g.name AS group_name
            FROM group_schedule_moves gm
            JOIN group_schedule_slots gs ON gs.id=gm.schedule_slot_id
            JOIN teacher_groups g ON g.id=gs.group_id
            WHERE gm.teacher_telegram_user_id=?
              AND gm.new_date=? AND gm.original_date<>?
              AND gs.active=1 AND g.active=1
            """,
            (int(uid), today.isoformat(), today.isoformat()),
        ).fetchall()
        for r in moved_in:
            events.append({
                "kind": "group",
                "slot_id": int(r["schedule_slot_id"]),
                "group_id": int(r["group_id"]),
                "name": r["group_name"],
                "time": r["new_time"],
                "moved": True,
            })
    return events


def _payment_line(uid, student_id, today):
    with base.db() as conn:
        plan = conn.execute(
            """
            SELECT payment_type, amount_rub, next_due_date, active
            FROM student_payment_plans
            WHERE teacher_telegram_user_id=? AND student_id=?
            """,
            (int(uid), int(student_id)),
        ).fetchone()
        latest = conn.execute(
            """
            SELECT paid_at FROM student_payment_history
            WHERE teacher_telegram_user_id=? AND student_id=?
            ORDER BY paid_at DESC LIMIT 1
            """,
            (int(uid), int(student_id)),
        ).fetchone()

    if not plan:
        return "💳 ⚪ оплата не настроена"

    if not int(plan["active"]):
        if latest:
            paid_at = datetime.fromisoformat(latest["paid_at"]).date()
            return f"💳 ✅ разовая оплата получена {paid_at.strftime('%d.%m')}"
        return "💳 ⚪ активной оплаты нет"

    due = date.fromisoformat(plan["next_due_date"])
    if due < today:
        days = (today - due).days
        return f"💳 🔴 просрочено на {days} дн."
    if due == today:
        return "💳 🟠 срок оплаты сегодня"
    if plan["payment_type"] == "monthly":
        return f"💳 ✅ оплата актуальна • следующая {due.strftime('%d.%m')}"
    return f"💳 🟡 разовая оплата до {due.strftime('%d.%m')}"


def _summary(uid, events, today):
    overdue = 0
    due_today = 0
    not_set = 0
    seen_students = set()
    for event in events:
        if event["kind"] != "individual":
            continue
        sid = int(event["student_id"])
        if sid in seen_students:
            continue
        seen_students.add(sid)
        line = _payment_line(uid, sid, today)
        if "🔴" in line:
            overdue += 1
        elif "🟠" in line:
            due_today += 1
        elif "⚪" in line:
            not_set += 1
    parts = []
    if overdue:
        parts.append(f"🔴 просрочено: {overdue}")
    if due_today:
        parts.append(f"🟠 оплат сегодня: {due_today}")
    if not_set:
        parts.append(f"⚪ без настройки оплаты: {not_set}")
    return " • ".join(parts)


async def today_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = datetime.now(schedule.tz(uid)).date()
    events = _individual_today(uid, today) + _group_today(uid, today)
    events.sort(key=lambda e: (e["time"], e["kind"], e["name"].lower()))

    header = f"📍 Сегодня • {today.strftime('%d.%m.%Y')}"
    if not events:
        await update.message.reply_text(
            header + "\n\nСегодня занятий нет 🎉",
            reply_markup=base.MAIN_KB,
        )
        return

    lines = [header, f"Занятий: {len(events)}"]
    summary = _summary(uid, events, today)
    if summary:
        lines.append(summary)

    for event in events:
        moved = " ↪️" if event["moved"] else ""
        if event["kind"] == "individual":
            lines.append(
                f"\n🕒 {event['time']} • 👤 {event['name']}{moved}\n"
                f"{_payment_line(uid, event['student_id'], today)}"
            )
        else:
            lines.append(
                f"\n🕒 {event['time']} • 👥 {event['name']}{moved}\n"
                "💳 оплата участников появится после подключения состава группы"
            )

    if any(e["moved"] for e in events):
        lines.append("\n↪️ — занятие было перенесено")

    await update.message.reply_text("\n".join(lines), reply_markup=base.MAIN_KB)


def build_app():
    app = payments.build_app()
    base.MAIN_KB = ReplyKeyboardMarkup(
        [
            ["📍 Сегодня"],
            ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
            ["⚙️ Настройки"],
        ],
        resize_keyboard=True,
    )
    app.add_handler(MessageHandler(filters.Regex(r"^📍 Сегодня$"), today_dashboard), group=-2)
    return app
