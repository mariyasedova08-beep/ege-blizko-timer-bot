import calendar
from datetime import date, datetime

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
import teacher_product_reset as reset

PAY_STUDENT, PAY_TYPE, PAY_AMOUNT, PAY_DATE = range(70, 74)


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS student_payment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                payment_type TEXT NOT NULL,
                amount_rub INTEGER NOT NULL,
                next_due_date TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(teacher_telegram_user_id, student_id)
            );

            CREATE TABLE IF NOT EXISTS student_payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                amount_rub INTEGER NOT NULL,
                payment_type TEXT NOT NULL,
                due_date TEXT,
                paid_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_student_payment_plans_teacher
            ON student_payment_plans(teacher_telegram_user_id, active, next_due_date);

            CREATE INDEX IF NOT EXISTS idx_student_payment_history_teacher
            ON student_payment_history(teacher_telegram_user_id, paid_at);
            """
        )
        conn.commit()


def _today(uid):
    return datetime.now(schedule.tz(uid)).date()


def _money(value):
    return f"{int(value):,}".replace(",", " ") + " ₽"


def _parse_amount(text):
    cleaned = "".join(ch for ch in text if ch.isdigit())
    if not cleaned:
        return None
    value = int(cleaned)
    if value <= 0 or value > 10_000_000:
        return None
    return value


def _add_month(d):
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _student(uid, sid):
    with base.db() as conn:
        return conn.execute(
            "SELECT id,name FROM students WHERE id=? AND teacher_telegram_user_id=? AND active=1",
            (int(sid), int(uid)),
        ).fetchone()


def _plan(uid, sid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*, s.name AS student_name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=? AND p.student_id=? AND s.active=1
            """,
            (int(uid), int(sid)),
        ).fetchone()


def _plans(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT s.id AS student_id,s.name,p.payment_type,p.amount_rub,p.next_due_date,p.active
            FROM students s
            LEFT JOIN student_payment_plans p
              ON p.student_id=s.id AND p.teacher_telegram_user_id=s.teacher_telegram_user_id
            WHERE s.teacher_telegram_user_id=? AND s.active=1
            ORDER BY lower(s.name)
            """,
            (int(uid),),
        ).fetchall()


def _active_plans(uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*,s.name AS student_name
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=? AND p.active=1 AND s.active=1
            ORDER BY p.next_due_date,lower(s.name)
            """,
            (int(uid),),
        ).fetchall()


def _save_plan(uid, sid, payment_type, amount_rub, due_date):
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO student_payment_plans(
                teacher_telegram_user_id,student_id,payment_type,amount_rub,
                next_due_date,active,created_at,updated_at
            ) VALUES(?,?,?,?,?,1,?,?)
            ON CONFLICT(teacher_telegram_user_id,student_id) DO UPDATE SET
                payment_type=excluded.payment_type,
                amount_rub=excluded.amount_rub,
                next_due_date=excluded.next_due_date,
                active=1,
                updated_at=excluded.updated_at
            """,
            (int(uid), int(sid), payment_type, int(amount_rub), due_date.isoformat(), now, now),
        )
        conn.commit()


def _status(uid, row):
    if not row["payment_type"] or not row["active"]:
        return "⚪ не настроено"
    due = date.fromisoformat(row["next_due_date"])
    today = _today(uid)
    if due < today:
        days = (today - due).days
        return f"🔴 просрочено {days} дн."
    if due == today:
        return "🟠 сегодня"
    return f"🟡 до {due.strftime('%d.%m')}"


def _type_label(value):
    return "ежемесячно" if value == "monthly" else "разовая"


async def payments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_tables()
    rows = _plans(uid)
    if not rows:
        text = (
            "💳 Оплаты\n\n"
            "Сначала добавь хотя бы одного индивидуального ученика.\n\n"
            "Групповые оплаты подключим после того, как добавим участников групп."
        )
        await update.message.reply_text(text, reply_markup=base.MAIN_KB)
        raise ApplicationHandlerStop

    lines = ["💳 Оплаты • индивидуальные"]
    for r in rows[:30]:
        if r["payment_type"] and r["active"]:
            plan = f"{_money(r['amount_rub'])} • {_type_label(r['payment_type'])}"
            lines.append(f"\n{r['name']}\n{plan}\n{_status(uid, r)}")
        else:
            lines.append(f"\n{r['name']}\n⚪ оплата не настроена")

    lines.append("\nГрупповые оплаты добавим после участников групп.")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Настроить / изменить", callback_data="pay:setup")],
        [InlineKeyboardButton("✅ Получила оплату", callback_data="pay:mark")],
        [InlineKeyboardButton("📜 История", callback_data="pay:history")],
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
    kb = [[InlineKeyboardButton(s["name"], callback_data=f"pay:student:{s['id']}")] for s in students[:40]]
    await q.edit_message_text("Для кого настраиваем оплату?", reply_markup=InlineKeyboardMarkup(kb))
    return PAY_STUDENT


async def setup_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sid = int(q.data.rsplit(":", 1)[1])
    student = _student(q.from_user.id, sid)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        return ConversationHandler.END
    context.user_data["pay_sid"] = sid
    context.user_data["pay_name"] = student["name"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ Разовая", callback_data="pay:type:once")],
        [InlineKeyboardButton("🔁 Ежемесячная", callback_data="pay:type:monthly")],
    ])
    await q.edit_message_text(f"{student['name']}\n\nКак оплачивает ученик?", reply_markup=kb)
    return PAY_TYPE


async def setup_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    payment_type = q.data.rsplit(":", 1)[1]
    context.user_data["pay_type"] = payment_type
    label = "разовая" if payment_type == "once" else "ежемесячная"
    await q.edit_message_text(f"Тип оплаты: {label}.\n\nНапиши сумму в рублях, например: 15000")
    return PAY_AMOUNT


async def setup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = _parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("Не поняла сумму. Напиши только сумму, например: 15000")
        return PAY_AMOUNT
    context.user_data["pay_amount"] = amount
    await update.message.reply_text(
        "На какую дату ждём оплату?\nНапиши, например: 28.09"
    )
    return PAY_DATE


async def setup_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = _today(uid)
    due = schedule.parse_date(update.message.text, today)
    if not due:
        await update.message.reply_text("Не поняла дату. Напиши, например: 28.09")
        return PAY_DATE

    sid = context.user_data.get("pay_sid")
    name = context.user_data.get("pay_name", "Ученик")
    payment_type = context.user_data.get("pay_type")
    amount = context.user_data.get("pay_amount")
    if sid is None or payment_type not in {"once", "monthly"} or amount is None:
        await update.message.reply_text("Настройка сбилась. Открой «💳 Оплаты» и попробуй ещё раз.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    _save_plan(uid, sid, payment_type, amount, due)
    for key in ("pay_sid", "pay_name", "pay_type", "pay_amount"):
        context.user_data.pop(key, None)

    await update.message.reply_text(
        f"✅ Оплата для {name} настроена.\n\n"
        f"Тип: {_type_label(payment_type)}\n"
        f"Сумма: {_money(amount)}\n"
        f"Дата: {due.strftime('%d.%m.%Y')}",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def mark_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = _active_plans(q.from_user.id)
    if not rows:
        await q.edit_message_text("Сейчас нет настроенных оплат, которые можно отметить.")
        return
    kb = []
    for r in rows[:40]:
        due = date.fromisoformat(r["next_due_date"]).strftime("%d.%m")
        kb.append([
            InlineKeyboardButton(
                f"{r['student_name']} • {_money(r['amount_rub'])} • {due}",
                callback_data=f"pay:mark:{r['student_id']}",
            )
        ])
    await q.edit_message_text("Чью оплату ты получила?", reply_markup=InlineKeyboardMarkup(kb))


async def mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    sid = int(q.data.rsplit(":", 1)[1])
    plan = _plan(uid, sid)
    if not plan or not plan["active"]:
        await q.edit_message_text("Активная оплата не найдена.")
        return

    now = datetime.now(schedule.tz(uid))
    due = date.fromisoformat(plan["next_due_date"])
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO student_payment_history(
                teacher_telegram_user_id,student_id,amount_rub,payment_type,due_date,paid_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (uid, sid, int(plan["amount_rub"]), plan["payment_type"], due.isoformat(), now.isoformat()),
        )
        if plan["payment_type"] == "monthly":
            next_due = _add_month(due)
            conn.execute(
                "UPDATE student_payment_plans SET next_due_date=?,updated_at=? WHERE teacher_telegram_user_id=? AND student_id=?",
                (next_due.isoformat(), datetime.utcnow().isoformat(), uid, sid),
            )
        else:
            next_due = None
            conn.execute(
                "UPDATE student_payment_plans SET active=0,updated_at=? WHERE teacher_telegram_user_id=? AND student_id=?",
                (datetime.utcnow().isoformat(), uid, sid),
            )
        conn.commit()

    if next_due:
        tail = f"\nСледующая оплата: {next_due.strftime('%d.%m.%Y')}"
    else:
        tail = "\nРазовая оплата закрыта."
    await q.edit_message_text(
        f"✅ Оплата отмечена.\n\n"
        f"{plan['student_name']} — {_money(plan['amount_rub'])}{tail}"
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.amount_rub,h.paid_at,s.name
            FROM student_payment_history h
            JOIN students s ON s.id=h.student_id
            WHERE h.teacher_telegram_user_id=?
            ORDER BY h.paid_at DESC
            LIMIT 20
            """,
            (int(q.from_user.id),),
        ).fetchall()
    if not rows:
        await q.edit_message_text("📜 История оплат пока пустая.")
        return
    lines = ["📜 Последние оплаты"]
    for r in rows:
        paid = datetime.fromisoformat(r["paid_at"])
        lines.append(f"• {paid.strftime('%d.%m.%Y')} — {r['name']} — {_money(r['amount_rub'])}")
    await q.edit_message_text("\n".join(lines))


def build_app():
    ensure_tables()
    app = reset.build_app()

    setup = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_begin, pattern=r"^pay:setup$")],
        states={
            PAY_STUDENT: [CallbackQueryHandler(setup_student, pattern=r"^pay:student:\d+$")],
            PAY_TYPE: [CallbackQueryHandler(setup_type, pattern=r"^pay:type:(?:once|monthly)$")],
            PAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_amount)],
            PAY_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_date)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(setup, group=-1)
    app.add_handler(CallbackQueryHandler(mark_picker, pattern=r"^pay:mark$"), group=-1)
    app.add_handler(CallbackQueryHandler(mark_paid, pattern=r"^pay:mark:\d+$"), group=-1)
    app.add_handler(CallbackQueryHandler(history, pattern=r"^pay:history$"), group=-1)
    app.add_handler(MessageHandler(filters.Regex(r"^💳 Оплаты$"), payments_menu), group=-1)
    return app
