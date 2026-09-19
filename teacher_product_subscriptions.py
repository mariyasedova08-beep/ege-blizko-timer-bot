from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_payments as payments
import teacher_product_today as today
import teacher_product_learning as learning


SUB_STUDENT, SUB_AMOUNT, SUB_COUNT = range(210, 213)
_SENTINEL_DUE = "9999-12-31"

_ORIGINAL_PAYMENT_LINE = today._payment_line
_ORIGINAL_SET_ATTENDANCE = learning._set_attendance


def _table_columns(conn, table_name):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_tables():
    payments.ensure_tables()
    with base.db() as conn:
        cols = _table_columns(conn, "student_payment_plans")
        if "lessons_total" not in cols:
            conn.execute("ALTER TABLE student_payment_plans ADD COLUMN lessons_total INTEGER")
        if "lessons_remaining" not in cols:
            conn.execute("ALTER TABLE student_payment_plans ADD COLUMN lessons_remaining INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_subscription_lesson_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                amount_rub_deducted INTEGER NOT NULL DEFAULT 0,
                lessons_before INTEGER NOT NULL,
                lessons_after INTEGER NOT NULL,
                used_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_subscription_usage_teacher
            ON student_subscription_lesson_usage(teacher_telegram_user_id, student_id, used_at)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_subscription_attendance_usage (
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                lessons_before INTEGER NOT NULL,
                lessons_after INTEGER NOT NULL,
                deducted_at TEXT NOT NULL,
                PRIMARY KEY(
                    teacher_telegram_user_id,student_id,lesson_kind,
                    schedule_slot_id,lesson_date
                )
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_subscription_repairs (
                repair_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    _apply_requested_balance_repairs()


def _apply_requested_balance_repairs():
    """One-time correction explicitly requested by the teacher."""
    repair_key = "alina-topup-balance-8-20260919"
    with base.db() as conn:
        done = conn.execute(
            "SELECT 1 FROM teacher_subscription_repairs WHERE repair_key=?",
            (repair_key,),
        ).fetchone()
        if done:
            return

        candidates = conn.execute(
            """
            SELECT p.teacher_telegram_user_id,p.student_id,p.lessons_total,
                   p.lessons_remaining,s.name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
             AND s.teacher_telegram_user_id=p.teacher_telegram_user_id
            WHERE p.payment_type='package' AND p.active=1 AND s.active=1
            """
        ).fetchall()
        rows = [
            row for row in candidates
            if "алин" in str(row["name"] or "").strip().casefold()
        ]

        if len(rows) == 1:
            row = rows[0]
            current_total = int(row["lessons_total"] or 0)
            conn.execute(
                """
                UPDATE student_payment_plans
                SET lessons_remaining=8,
                    lessons_total=CASE WHEN lessons_total<8 OR lessons_total IS NULL THEN 8 ELSE lessons_total END,
                    updated_at=?
                WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
                """,
                (
                    datetime.utcnow().isoformat(),
                    int(row["teacher_telegram_user_id"]),
                    int(row["student_id"]),
                ),
            )
            conn.execute(
                "INSERT INTO teacher_subscription_repairs(repair_key,applied_at) VALUES(?,?)",
                (repair_key, datetime.utcnow().isoformat()),
            )
            conn.commit()
            print(
                f"PREPODMIN requested subscription repair applied: Alina remaining=8 total_before={current_total}",
                flush=True,
            )
        else:
            print(
                f"PREPODMIN requested subscription repair skipped: exact Alina matches={len(rows)}",
                flush=True,
            )


def _attendance_usage(uid, sid, kind, slot_id, lesson_date):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT *
            FROM student_subscription_attendance_usage
            WHERE teacher_telegram_user_id=? AND student_id=?
              AND lesson_kind=? AND schedule_slot_id=? AND lesson_date=?
            """,
            (int(uid), int(sid), str(kind), int(slot_id), lesson_date.isoformat()),
        ).fetchone()


def _deduct_for_attendance(uid, sid, kind, slot_id, lesson_date):
    if _attendance_usage(uid, sid, kind, slot_id, lesson_date):
        return False

    plan = _package_plan(uid, sid)
    if not plan or not int(plan["active"] or 0):
        return False

    total = int(plan["lessons_total"] or 0)
    before = int(plan["lessons_remaining"] or 0)
    if total <= 0 or before <= 0:
        return False

    after = before - 1
    prev_balance = _package_balance(plan["amount_rub"], total, before)
    new_balance = _package_balance(plan["amount_rub"], total, after)
    deducted = max(0, prev_balance - new_balance)
    now_local = datetime.now(schedule.tz(uid)).isoformat()
    now_utc = datetime.utcnow().isoformat()

    with base.db() as conn:
        existing = conn.execute(
            """
            SELECT 1
            FROM student_subscription_attendance_usage
            WHERE teacher_telegram_user_id=? AND student_id=?
              AND lesson_kind=? AND schedule_slot_id=? AND lesson_date=?
            """,
            (int(uid), int(sid), str(kind), int(slot_id), lesson_date.isoformat()),
        ).fetchone()
        if existing:
            return False

        conn.execute(
            """
            UPDATE student_payment_plans
            SET lessons_remaining=?,updated_at=?
            WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
            """,
            (after, now_utc, int(uid), int(sid)),
        )
        conn.execute(
            """
            INSERT INTO student_subscription_lesson_usage(
                teacher_telegram_user_id,student_id,amount_rub_deducted,
                lessons_before,lessons_after,used_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (int(uid), int(sid), deducted, before, after, now_local),
        )
        conn.execute(
            """
            INSERT INTO student_subscription_attendance_usage(
                teacher_telegram_user_id,student_id,lesson_kind,
                schedule_slot_id,lesson_date,lessons_before,lessons_after,deducted_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                int(uid), int(sid), str(kind), int(slot_id),
                lesson_date.isoformat(), before, after, now_local,
            ),
        )
        conn.commit()

    print(
        f"PREPODMIN subscription auto-deduct: before={before} after={after} date={lesson_date.isoformat()}",
        flush=True,
    )
    return True


def _restore_for_attendance(uid, sid, kind, slot_id, lesson_date):
    usage = _attendance_usage(uid, sid, kind, slot_id, lesson_date)
    if not usage:
        return False
    plan = _package_plan(uid, sid)
    if not plan or not int(plan["active"] or 0):
        return False

    before = int(plan["lessons_remaining"] or 0)
    after = before + 1
    total = max(int(plan["lessons_total"] or 0), after)
    with base.db() as conn:
        conn.execute(
            """
            UPDATE student_payment_plans
            SET lessons_remaining=?,lessons_total=?,updated_at=?
            WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
            """,
            (after, total, datetime.utcnow().isoformat(), int(uid), int(sid)),
        )
        conn.execute(
            """
            DELETE FROM student_subscription_attendance_usage
            WHERE teacher_telegram_user_id=? AND student_id=?
              AND lesson_kind=? AND schedule_slot_id=? AND lesson_date=?
            """,
            (int(uid), int(sid), str(kind), int(slot_id), lesson_date.isoformat()),
        )
        conn.commit()
    print(
        f"PREPODMIN subscription attendance restore: before={before} after={after} date={lesson_date.isoformat()}",
        flush=True,
    )
    return True


def _set_attendance_with_subscription(
    uid, kind, slot_id, lesson_date, subject_kind, subject_id, status
):
    previous = learning._attendance_status(
        uid, kind, slot_id, lesson_date, subject_kind, subject_id
    )
    result = _ORIGINAL_SET_ATTENDANCE(
        uid, kind, slot_id, lesson_date, subject_kind, subject_id, status
    )

    if kind == "individual" and subject_kind == "individual":
        sid = int(subject_id)
        if previous != "present" and status == "present":
            _deduct_for_attendance(uid, sid, kind, slot_id, lesson_date)
        elif previous == "present" and status != "present":
            _restore_for_attendance(uid, sid, kind, slot_id, lesson_date)
    return result


def _parse_positive_int(text, max_value):
    cleaned = "".join(ch for ch in str(text) if ch.isdigit())
    if not cleaned:
        return None
    value = int(cleaned)
    if value <= 0 or value > max_value:
        return None
    return value


def _package_balance(amount_rub, total, remaining):
    if not total or total <= 0:
        return 0
    return int(round(int(amount_rub) * int(remaining) / int(total)))


def _package_plan(uid, sid):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*, s.name AS student_name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=? AND p.student_id=?
              AND p.payment_type='package' AND s.active=1
            """,
            (int(uid), int(sid)),
        ).fetchone()


def _active_non_package_plans(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*,s.name AS student_name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=? AND p.active=1 AND s.active=1
              AND p.payment_type<>'package'
            ORDER BY p.next_due_date,lower(s.name)
            """,
            (int(uid),),
        ).fetchall()


def _payment_line_with_package(uid, student_id, today_date):
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT payment_type,amount_rub,lessons_total,lessons_remaining,active
            FROM student_payment_plans
            WHERE teacher_telegram_user_id=? AND student_id=?
            """,
            (int(uid), int(student_id)),
        ).fetchone()
    if row and row["payment_type"] == "package" and int(row["active"]):
        total = int(row["lessons_total"] or 0)
        remaining = int(row["lessons_remaining"] or 0)
        if remaining <= 0:
            return "💳 🎟 абонемент закончился • нужна новая оплата"
        balance = _package_balance(row["amount_rub"], total, remaining)
        return f"💳 🎟 осталось {remaining}/{total} занятий • остаток {payments._money(balance)}"
    return _ORIGINAL_PAYMENT_LINE(uid, student_id, today_date)


def patch_functions():
    payments._active_plans = _active_non_package_plans
    today._payment_line = _payment_line_with_package
    learning._set_attendance = _set_attendance_with_subscription


def _rows(uid):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT s.id AS student_id,s.name,p.payment_type,p.amount_rub,p.next_due_date,
                   p.active,p.lessons_total,p.lessons_remaining
            FROM students s
            LEFT JOIN student_payment_plans p
              ON p.student_id=s.id AND p.teacher_telegram_user_id=s.teacher_telegram_user_id
            WHERE s.teacher_telegram_user_id=? AND s.active=1
            ORDER BY lower(s.name)
            """,
            (int(uid),),
        ).fetchall()


async def payments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rows = _rows(uid)
    if not rows:
        await update.message.reply_text(
            "💳 Оплаты\n\nСначала добавь хотя бы одного индивидуального ученика.",
            reply_markup=base.MAIN_KB,
        )
        raise ApplicationHandlerStop

    lines = ["💳 Оплаты • индивидуальные"]
    for r in rows[:30]:
        if not r["payment_type"] or not r["active"]:
            lines.append(f"\n{r['name']}\n⚪ оплата не настроена")
            continue
        if r["payment_type"] == "package":
            total = int(r["lessons_total"] or 0)
            remaining = int(r["lessons_remaining"] or 0)
            balance = _package_balance(r["amount_rub"], total, remaining)
            if remaining > 0:
                lines.append(
                    f"\n{r['name']}\n🎟 Абонемент: {payments._money(r['amount_rub'])} • "
                    f"{total} занятий\nОсталось: {remaining} занятий • {payments._money(balance)}"
                )
            else:
                lines.append(
                    f"\n{r['name']}\n🎟 Абонемент закончился\n🔴 Нужна новая оплата"
                )
        else:
            plan = f"{payments._money(r['amount_rub'])} • {payments._type_label(r['payment_type'])}"
            lines.append(f"\n{r['name']}\n{plan}\n{payments._status(uid, r)}")

    lines.append("\nДля абонемента дата следующего платежа не ставится: она наступает, когда закончатся оплаченные занятия.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟 Новый абонемент", callback_data="sub:setup")],
        [InlineKeyboardButton("➖ Ручное списание", callback_data="sub:use")],
        [InlineKeyboardButton("➕ Разовая / ежемесячная", callback_data="pay:setup")],
        [InlineKeyboardButton("✅ Получила разовую / месячную оплату", callback_data="pay:mark")],
        [InlineKeyboardButton("📜 История оплат", callback_data="pay:history")],
    ])
    await update.message.reply_text("\n".join(lines), reply_markup=kb)
    raise ApplicationHandlerStop


async def setup_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    students = base.list_students(q.from_user.id)
    if not students:
        await q.edit_message_text("Сначала добавь индивидуального ученика.")
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(s["name"], callback_data=f"sub:student:{s['id']}")] for s in students[:40]]
    await q.edit_message_text(
        "🎟 Новый абонемент\n\nКто оплатил пакет занятий?",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return SUB_STUDENT


async def setup_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sid = int(q.data.rsplit(":", 1)[1])
    student = payments._student(q.from_user.id, sid)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        return ConversationHandler.END
    current = _package_plan(q.from_user.id, sid)
    context.user_data["sub_sid"] = sid
    context.user_data["sub_name"] = student["name"]
    warning = ""
    if current and int(current["lessons_remaining"] or 0) > 0:
        warning = (
            f"\n\nСейчас у ученика ещё {int(current['lessons_remaining'])} оплаченных занятий. "
            "Новые занятия добавятся к этому остатку."
        )
    await q.edit_message_text(
        f"{student['name']}\n\nСколько рублей получено за абонемент?\nНапример: 40000{warning}"
    )
    return SUB_AMOUNT


async def setup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = payments._parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("Не поняла сумму. Напиши, например: 40000")
        return SUB_AMOUNT
    context.user_data["sub_amount"] = amount
    await update.message.reply_text(
        "Сколько занятий входит в абонемент?\nНапример: 8"
    )
    return SUB_COUNT


async def setup_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = _parse_positive_int(update.message.text, 100)
    if count is None:
        await update.message.reply_text("Не поняла количество. Напиши число занятий, например: 8")
        return SUB_COUNT

    uid = int(update.effective_user.id)
    sid = context.user_data.get("sub_sid")
    name = context.user_data.get("sub_name", "Ученик")
    amount = context.user_data.get("sub_amount")
    if sid is None or amount is None:
        await update.message.reply_text(
            "Настройка сбилась. Открой «💳 Оплаты» и попробуй ещё раз.",
            reply_markup=base.MAIN_KB,
        )
        return ConversationHandler.END

    now_local = datetime.now(schedule.tz(uid))
    now_utc = datetime.utcnow().isoformat()
    current = _package_plan(uid, sid)
    old_remaining = (
        int(current["lessons_remaining"] or 0)
        if current and int(current["active"] or 0)
        else 0
    )
    old_balance = (
        _package_balance(
            current["amount_rub"],
            int(current["lessons_total"] or 0),
            old_remaining,
        )
        if current and old_remaining > 0
        else 0
    )
    new_remaining = old_remaining + int(count)
    new_total = new_remaining
    new_amount = old_balance + int(amount)

    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO student_payment_plans(
                teacher_telegram_user_id,student_id,payment_type,amount_rub,
                next_due_date,active,created_at,updated_at,lessons_total,lessons_remaining
            ) VALUES(?,?,?,?,?,1,?,?,?,?)
            ON CONFLICT(teacher_telegram_user_id,student_id) DO UPDATE SET
                payment_type='package',
                amount_rub=excluded.amount_rub,
                next_due_date=excluded.next_due_date,
                active=1,
                updated_at=excluded.updated_at,
                lessons_total=excluded.lessons_total,
                lessons_remaining=excluded.lessons_remaining
            """,
            (
                uid, int(sid), "package", new_amount, _SENTINEL_DUE,
                now_utc, now_utc, new_total, new_remaining,
            ),
        )
        conn.execute(
            """
            INSERT INTO student_payment_history(
                teacher_telegram_user_id,student_id,amount_rub,payment_type,due_date,paid_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, int(sid), int(amount), "package", None, now_local.isoformat()),
        )
        conn.commit()

    for key in ("sub_sid", "sub_name", "sub_amount"):
        context.user_data.pop(key, None)

    per_lesson = int(round(int(amount) / int(count)))
    await update.message.reply_text(
        f"✅ Оплата для {name} учтена.\n\n"
        f"Получено сейчас: {payments._money(amount)}\n"
        f"Добавлено занятий: {count}\n"
        f"Было в остатке: {old_remaining}\n"
        f"Теперь в остатке: {new_remaining}\n"
        f"Ориентир за 1 новое занятие: {payments._money(per_lesson)}\n\n"
        "Занятие теперь списывается автоматически, когда в «✅ Посещаемость» "
        "ученик отмечен как «Был(а)». Поздняя отметка за вчера тоже учитывается.",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def use_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ensure_tables()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT p.student_id,p.amount_rub,p.lessons_total,p.lessons_remaining,s.name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=? AND p.payment_type='package'
              AND p.active=1 AND s.active=1
            ORDER BY lower(s.name)
            """,
            (int(q.from_user.id),),
        ).fetchall()
    if not rows:
        await q.edit_message_text("Активных абонементов пока нет.")
        return
    kb = []
    for r in rows[:40]:
        remaining = int(r["lessons_remaining"] or 0)
        label = f"{r['name']} • осталось {remaining}/{int(r['lessons_total'] or 0)}"
        kb.append([InlineKeyboardButton(label, callback_data=f"sub:use:{r['student_id']}")])
    await q.edit_message_text(
        "Ручное списание абонемента.\n\nОбычно списывать здесь не нужно: "
        "занятие списывается автоматически через «✅ Посещаемость» → «Был(а)». "
        "Используй ручное списание только если занятие не отмечалось в посещаемости.",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def use_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    sid = int(q.data.rsplit(":", 1)[1])
    plan = _package_plan(uid, sid)
    if not plan or not int(plan["active"]):
        await q.edit_message_text("Абонемент не найден.")
        return

    total = int(plan["lessons_total"] or 0)
    before = int(plan["lessons_remaining"] or 0)
    if total <= 0:
        await q.edit_message_text("В абонементе некорректно указано количество занятий. Настрой его заново.")
        return
    if before <= 0:
        await q.edit_message_text(
            f"🎟 {plan['student_name']}\n\nАбонемент уже закончился. Нужна новая оплата."
        )
        return

    after = before - 1
    prev_balance = _package_balance(plan["amount_rub"], total, before)
    new_balance = _package_balance(plan["amount_rub"], total, after)
    deducted = max(0, prev_balance - new_balance)
    now = datetime.now(schedule.tz(uid)).isoformat()
    with base.db() as conn:
        conn.execute(
            """
            UPDATE student_payment_plans
            SET lessons_remaining=?, updated_at=?
            WHERE teacher_telegram_user_id=? AND student_id=? AND payment_type='package'
            """,
            (after, datetime.utcnow().isoformat(), uid, sid),
        )
        conn.execute(
            """
            INSERT INTO student_subscription_lesson_usage(
                teacher_telegram_user_id,student_id,amount_rub_deducted,
                lessons_before,lessons_after,used_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, sid, deducted, before, after, now),
        )
        conn.commit()

    if after == 0:
        tail = (
            "\n\n🔴 Абонемент закончился.\n"
            "Следующая оплата нужна теперь, но фиксированной даты нет — всё зависит от фактически проведённых занятий."
        )
    elif after == 1:
        tail = "\n\n🟠 Осталось последнее оплаченное занятие."
    else:
        tail = ""
    await q.edit_message_text(
        f"✅ Занятие списано.\n\n"
        f"{plan['student_name']}\n"
        f"Осталось: {after}/{total} занятий\n"
        f"Остаток абонемента: {payments._money(new_balance)}"
        f"{tail}"
    )


def install(app):
    ensure_tables()
    patch_functions()

    setup = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_begin, pattern=r"^sub:setup$")],
        states={
            SUB_STUDENT: [CallbackQueryHandler(setup_student, pattern=r"^sub:student:\d+$")],
            SUB_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_amount)],
            SUB_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_count)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(setup, group=-10)
    app.add_handler(CallbackQueryHandler(use_picker, pattern=r"^sub:use$"), group=-10)
    app.add_handler(CallbackQueryHandler(use_apply, pattern=r"^sub:use:\d+$"), group=-10)
    app.add_handler(MessageHandler(filters.Regex(r"^💳 Оплаты$"), payments_menu), group=-10)
    return app
