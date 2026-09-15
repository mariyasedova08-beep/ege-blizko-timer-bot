from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_today as today
import teacher_product_subscriptions as subscriptions


def ensure_tables():
    subscriptions.ensure_tables()
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_package_lesson_marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                usage_id INTEGER,
                marked_at TEXT NOT NULL,
                UNIQUE(teacher_telegram_user_id, student_id, schedule_slot_id, lesson_date)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_package_lesson_marks_teacher_date
            ON student_package_lesson_marks(teacher_telegram_user_id, lesson_date)
            """
        )
        conn.commit()


def _is_marked(uid, sid, slot_id, lesson_date):
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM student_package_lesson_marks
            WHERE teacher_telegram_user_id=? AND student_id=?
              AND schedule_slot_id=? AND lesson_date=?
            """,
            (int(uid), int(sid), int(slot_id), lesson_date.isoformat()),
        ).fetchone()
    return bool(row)


def _action_rows(uid, lesson_date):
    ensure_tables()
    rows = []
    for event in today._individual_today(uid, lesson_date):
        sid = int(event["student_id"])
        slot_id = int(event["slot_id"])
        plan = subscriptions._package_plan(uid, sid)
        if not plan or not int(plan["active"]):
            continue
        total = int(plan["lessons_total"] or 0)
        remaining = int(plan["lessons_remaining"] or 0)
        if total <= 0 or remaining <= 0:
            continue
        if _is_marked(uid, sid, slot_id, lesson_date):
            continue
        rows.append({
            "student_id": sid,
            "slot_id": slot_id,
            "name": event["name"],
            "time": event["time"],
            "remaining": remaining,
            "total": total,
            "moved": bool(event["moved"]),
        })
    rows.sort(key=lambda r: (r["time"], r["name"].lower()))
    return rows


def _actions_markup(uid, lesson_date):
    buttons = []
    compact_date = lesson_date.strftime("%Y%m%d")
    for row in _action_rows(uid, lesson_date):
        moved = " ↪️" if row["moved"] else ""
        label = (
            f"✅ {row['time']} • {row['name']}{moved} • "
            f"{row['remaining']}/{row['total']}"
        )
        callback = f"sub:today:{row['student_id']}:{row['slot_id']}:{compact_date}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])
    return InlineKeyboardMarkup(buttons) if buttons else None


async def today_with_package_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    lesson_date = datetime.now(schedule.tz(uid)).date()

    # Сначала показываем обычный экран «Сегодня» со всеми уроками, оплатами и задачами.
    await today.today_dashboard(update, context)

    markup = _actions_markup(uid, lesson_date)
    if markup:
        await update.message.reply_text(
            "✅ Отметить проведённое занятие\n\n"
            "Нажми кнопку только после того, как урок действительно состоялся. "
            "Для абонемента сразу спишется 1 занятие.",
            reply_markup=markup,
        )

    # Не даём старому обработчику «Сегодня» отправить тот же экран второй раз.
    raise ApplicationHandlerStop


def _deduct_today_lesson(uid, sid, slot_id, lesson_date):
    ensure_tables()
    plan = subscriptions._package_plan(uid, sid)
    if not plan or not int(plan["active"]):
        return {"ok": False, "reason": "no_package"}

    total = int(plan["lessons_total"] or 0)
    before = int(plan["lessons_remaining"] or 0)
    if total <= 0:
        return {"ok": False, "reason": "bad_package"}
    if before <= 0:
        return {"ok": False, "reason": "empty", "name": plan["student_name"], "total": total}

    now_local = datetime.now(schedule.tz(uid)).isoformat()
    now_utc = datetime.utcnow().isoformat()

    with base.db() as conn:
        already = conn.execute(
            """
            SELECT 1
            FROM student_package_lesson_marks
            WHERE teacher_telegram_user_id=? AND student_id=?
              AND schedule_slot_id=? AND lesson_date=?
            """,
            (uid, sid, slot_id, lesson_date.isoformat()),
        ).fetchone()
        if already:
            return {"ok": False, "reason": "already", "name": plan["student_name"]}

        # Перечитываем остаток внутри той же транзакции перед списанием.
        current = conn.execute(
            """
            SELECT amount_rub,lessons_total,lessons_remaining,active
            FROM student_payment_plans
            WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
            """,
            (uid, sid),
        ).fetchone()
        if not current or not int(current["active"]):
            return {"ok": False, "reason": "no_package"}

        total = int(current["lessons_total"] or 0)
        before = int(current["lessons_remaining"] or 0)
        if total <= 0:
            return {"ok": False, "reason": "bad_package"}
        if before <= 0:
            return {"ok": False, "reason": "empty", "name": plan["student_name"], "total": total}

        after = before - 1
        prev_balance = subscriptions._package_balance(current["amount_rub"], total, before)
        new_balance = subscriptions._package_balance(current["amount_rub"], total, after)
        deducted = max(0, prev_balance - new_balance)

        conn.execute(
            """
            UPDATE student_payment_plans
            SET lessons_remaining=?, updated_at=?
            WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
            """,
            (after, now_utc, uid, sid),
        )
        cur = conn.execute(
            """
            INSERT INTO student_subscription_lesson_usage(
                teacher_telegram_user_id,student_id,amount_rub_deducted,
                lessons_before,lessons_after,used_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, sid, deducted, before, after, now_local),
        )
        conn.execute(
            """
            INSERT INTO student_package_lesson_marks(
                teacher_telegram_user_id,student_id,schedule_slot_id,
                lesson_date,usage_id,marked_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, sid, slot_id, lesson_date.isoformat(), int(cur.lastrowid), now_local),
        )
        conn.commit()

    return {
        "ok": True,
        "name": plan["student_name"],
        "total": total,
        "before": before,
        "after": after,
        "balance": new_balance,
    }


async def today_lesson_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)

    try:
        _, _, sid_text, slot_text, compact_date = q.data.split(":", 4)
        sid = int(sid_text)
        slot_id = int(slot_text)
        lesson_date = datetime.strptime(compact_date, "%Y%m%d").date()
    except Exception:
        await q.answer("Не удалось определить занятие.", show_alert=True)
        return

    result = _deduct_today_lesson(uid, sid, slot_id, lesson_date)
    if not result["ok"]:
        reason = result.get("reason")
        if reason == "already":
            await q.answer("Это занятие уже отмечено и списано.", show_alert=True)
        elif reason == "empty":
            await q.answer("Абонемент уже закончился. Нужна новая оплата.", show_alert=True)
        elif reason == "bad_package":
            await q.answer("В абонементе некорректное количество занятий.", show_alert=True)
        else:
            await q.answer("Активный абонемент не найден.", show_alert=True)
        return

    after = int(result["after"])
    total = int(result["total"])
    balance = subscriptions.payments._money(result["balance"])

    if after == 0:
        tail = "\n🔴 Абонемент закончился — нужна новая оплата."
    elif after == 1:
        tail = "\n🟠 Осталось последнее оплаченное занятие."
    else:
        tail = ""

    await q.message.reply_text(
        f"✅ Занятие проведено и списано.\n\n"
        f"{result['name']}\n"
        f"Осталось: {after}/{total} занятий\n"
        f"Остаток абонемента: {balance}{tail}"
    )

    markup = _actions_markup(uid, lesson_date)
    if markup:
        await q.edit_message_text(
            "✅ Отметить проведённое занятие\n\n"
            "Нажми кнопку только после того, как урок действительно состоялся. "
            "Для абонемента сразу спишется 1 занятие.",
            reply_markup=markup,
        )
    else:
        await q.edit_message_text("✅ На сегодня все занятия по абонементам отмечены.")


def install(app):
    ensure_tables()
    app.add_handler(
        MessageHandler(filters.Regex(r"^📍 Сегодня$"), today_with_package_actions),
        group=-11,
    )
    app.add_handler(
        CallbackQueryHandler(today_lesson_done, pattern=r"^sub:today:\d+:\d+:\d{8}$"),
        group=-11,
    )
    return app
