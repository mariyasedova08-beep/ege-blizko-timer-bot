"""Group payments and attendance-based package accounting for PREPADMIN pilot.

Adds payment plans per group member without changing the existing individual-payment
schema. Also reconciles package lesson counters with attendance marks so repeated
clicks or status corrections do not double-charge a lesson.
"""
import calendar
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_payments as individual_payments
import teacher_product_student_reminders as student_reminders
import teacher_product_learning as learning
import teacher_product_reports as reports
import teacher_product_webapp as webapp
import teacher_product_student_webapp as student_webapp


GPAY_TYPE, GPAY_AMOUNT, GPAY_FINAL = range(810, 813)


def ensure_tables():
    individual_payments.ensure_tables()
    student_reminders.ensure_tables()
    with base.db() as conn:
        # Older databases may not yet have package counters on individual plans.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(student_payment_plans)").fetchall()}
        if "lessons_total" not in cols:
            conn.execute("ALTER TABLE student_payment_plans ADD COLUMN lessons_total INTEGER")
        if "lessons_remaining" not in cols:
            conn.execute("ALTER TABLE student_payment_plans ADD COLUMN lessons_remaining INTEGER")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS group_member_payment_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                payment_type TEXT NOT NULL CHECK(payment_type IN ('once','monthly','package')),
                amount_rub INTEGER NOT NULL,
                next_due_date TEXT,
                lessons_total INTEGER,
                lessons_remaining INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(teacher_telegram_user_id, person_id)
            );

            CREATE TABLE IF NOT EXISTS group_member_payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                amount_rub INTEGER NOT NULL,
                payment_type TEXT NOT NULL,
                due_date TEXT,
                paid_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payment_attendance_charges (
                teacher_telegram_user_id INTEGER NOT NULL,
                subject_kind TEXT NOT NULL CHECK(subject_kind IN ('individual','group_member')),
                subject_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                charged_at TEXT NOT NULL,
                PRIMARY KEY(
                    teacher_telegram_user_id,subject_kind,subject_id,
                    schedule_slot_id,lesson_date
                )
            );

            CREATE INDEX IF NOT EXISTS idx_group_payment_teacher
            ON group_member_payment_plans(teacher_telegram_user_id,active,next_due_date);

            CREATE INDEX IF NOT EXISTS idx_group_payment_history_teacher
            ON group_member_payment_history(teacher_telegram_user_id,paid_at);
            """
        )
        conn.commit()


def _money(value):
    return f"{int(value or 0):,}".replace(",", " ") + " ₽"


def _parse_amount(text):
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    if not digits:
        return None
    value = int(digits)
    return value if 0 < value <= 10_000_000 else None


def _add_month(d):
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _member(uid, pid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.id,p.name,p.group_id,g.name AS group_name,p.telegram_user_id
            FROM student_reminder_people p
            JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.id=? AND p.teacher_id=? AND p.kind='group'
              AND p.active=1 AND g.active=1
            """,
            (int(pid), int(uid)),
        ).fetchone()


def _plan(uid, pid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*,m.name AS member_name,g.name AS group_name
            FROM group_member_payment_plans p
            JOIN student_reminder_people m ON m.id=p.person_id
            JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.teacher_telegram_user_id=? AND p.person_id=?
              AND m.active=1 AND g.active=1
            """,
            (int(uid), int(pid)),
        ).fetchone()


def _status(uid, row):
    if not row or not int(row["active"] or 0):
        return "⚪ не настроено", "muted"
    if row["payment_type"] == "package":
        left = int(row["lessons_remaining"] or 0)
        total = int(row["lessons_total"] or 0)
        return (f"🔴 абонемент закончился · 0/{total}", "bad") if left <= 0 else (f"🎟 осталось {left}/{total} занятий", "ok")
    due_text = row["next_due_date"]
    if not due_text:
        return "⚪ дата не настроена", "muted"
    due = date.fromisoformat(due_text)
    today = datetime.now(schedule.tz(uid)).date()
    if due < today:
        return f"🔴 просрочено {(today-due).days} дн.", "bad"
    if due == today:
        return "🟠 оплата сегодня", "warn"
    return f"🟢 до {due.strftime('%d.%m')}", "ok"


def _group_rows(uid, gid):
    members = student_reminders._members(uid, gid)
    with base.db() as conn:
        plans = {
            int(r["person_id"]): r
            for r in conn.execute(
                "SELECT * FROM group_member_payment_plans WHERE teacher_telegram_user_id=? AND group_id=?",
                (int(uid), int(gid)),
            ).fetchall()
        }
    return [(m, plans.get(int(m["id"]))) for m in members]


async def payments_home(update, context):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    ensure_tables()
    individual_count = len(base.list_students(uid))
    group_count = len(groups.groups(uid))
    with base.db() as conn:
        group_members = conn.execute(
            """
            SELECT COUNT(*) FROM student_reminder_people
            WHERE teacher_id=? AND kind='group' AND active=1
            """,
            (uid,),
        ).fetchone()[0]
    text = (
        "💳 Оплаты\n\n"
        f"👤 Индивидуальные ученики: {individual_count}\n"
        f"👥 Группы: {group_count} · участников: {int(group_members or 0)}\n\n"
        "Оплата хранится отдельно для каждого ученика, в том числе внутри группы."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Индивидуальные", callback_data="gpay:individual")],
        [InlineKeyboardButton("👥 Группы", callback_data="gpay:groups")],
        [InlineKeyboardButton("📜 История групповых оплат", callback_data="gpay:history")],
    ])
    await update.message.reply_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def individual_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    ensure_tables()
    rows = individual_payments._plans(uid)
    lines = ["💳 Оплаты · индивидуальные"]
    if not rows:
        lines += ["", "Индивидуальных учеников пока нет."]
    for r in rows[:40]:
        if r["payment_type"] and r["active"]:
            lines += ["", r["name"], f"{_money(r['amount_rub'])} · {individual_payments._type_label(r['payment_type'])}", individual_payments._status(uid, r)]
        else:
            lines += ["", r["name"], "⚪ оплата не настроена"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Настроить / изменить", callback_data="pay:setup")],
        [InlineKeyboardButton("✅ Получила оплату", callback_data="pay:mark")],
        [InlineKeyboardButton("📜 История", callback_data="pay:history")],
        [InlineKeyboardButton("← Все оплаты", callback_data="gpay:home")],
    ])
    await q.edit_message_text("\n".join(lines), reply_markup=kb)
    raise ApplicationHandlerStop


async def home_callback(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    with base.db() as conn:
        group_members = conn.execute(
            "SELECT COUNT(*) FROM student_reminder_people WHERE teacher_id=? AND kind='group' AND active=1",
            (uid,),
        ).fetchone()[0]
    await q.edit_message_text(
        "💳 Оплаты\n\n"
        f"👤 Индивидуальные ученики: {len(base.list_students(uid))}\n"
        f"👥 Группы: {len(groups.groups(uid))} · участников: {int(group_members or 0)}\n\n"
        "Оплата хранится отдельно для каждого ученика, в том числе внутри группы.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 Индивидуальные", callback_data="gpay:individual")],
            [InlineKeyboardButton("👥 Группы", callback_data="gpay:groups")],
            [InlineKeyboardButton("📜 История групповых оплат", callback_data="gpay:history")],
        ]),
    )
    raise ApplicationHandlerStop


async def groups_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    rows = groups.groups(uid)
    kb = [[InlineKeyboardButton(f"👥 {g['name']}", callback_data=f"gpay:group:{g['id']}")] for g in rows[:60]]
    kb.append([InlineKeyboardButton("← Все оплаты", callback_data="gpay:home")])
    await q.edit_message_text(
        "👥 Групповые оплаты\n\nВыбери группу:" if rows else "👥 Групповые оплаты\n\nГрупп пока нет.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    raise ApplicationHandlerStop


async def group_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    try:
        gid = int(q.data.rsplit(":", 1)[1])
    except Exception:
        raise ApplicationHandlerStop
    group = groups.get_group(uid, gid)
    if not group:
        await q.edit_message_text("Группа не найдена.")
        raise ApplicationHandlerStop
    rows = _group_rows(uid, gid)
    lines = [f"👥 {group['name']}", "", "Оплата по каждому ученику:"]
    kb = []
    for member, plan in rows[:60]:
        status_text, _level = _status(uid, plan)
        lines.append(f"• {member['name']} — {status_text}")
        kb.append([InlineKeyboardButton(member["name"], callback_data=f"gpay:member:{member['id']}")])
    if not rows:
        lines += ["", "В группе пока нет учеников."]
    kb.append([InlineKeyboardButton("← К группам", callback_data="gpay:groups")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    raise ApplicationHandlerStop


def _member_card(uid, pid):
    member = _member(uid, pid)
    if not member:
        return None, None
    plan = _plan(uid, pid)
    lines = [f"👤 {member['name']}", f"👥 {member['group_name']}", ""]
    if not plan or not int(plan["active"] or 0):
        lines.append("💳 Оплата не настроена.")
    else:
        status_text, _level = _status(uid, plan)
        type_label = {"once": "разовая", "monthly": "ежемесячно", "package": "абонемент"}.get(plan["payment_type"], plan["payment_type"])
        lines += [
            f"💳 {_money(plan['amount_rub'])} · {type_label}",
            status_text,
        ]
    kb = [
        [InlineKeyboardButton("⚙️ Настроить / изменить", callback_data=f"gpay:setup:{pid}")],
    ]
    if plan and int(plan["active"] or 0):
        kb.append([InlineKeyboardButton("✅ Получила оплату", callback_data=f"gpay:paid:{pid}")])
    kb.append([InlineKeyboardButton("← К группе", callback_data=f"gpay:group:{member['group_id']}")])
    return "\n".join(lines), InlineKeyboardMarkup(kb)


async def member_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    pid = int(q.data.rsplit(":", 1)[1])
    text, kb = _member_card(uid, pid)
    if not text:
        await q.edit_message_text("Ученик не найден.")
    else:
        await q.edit_message_text(text, reply_markup=kb)
    raise ApplicationHandlerStop


async def setup_begin(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    pid = int(q.data.rsplit(":", 1)[1])
    member = _member(uid, pid)
    if not member:
        await q.edit_message_text("Ученик не найден.")
        return ConversationHandler.END
    context.user_data["gpay"] = {"pid": pid, "gid": int(member["group_id"]), "name": member["name"]}
    await q.edit_message_text(
        f"💳 {member['name']}\n\nКак оплачивает ученик?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1️⃣ Разовая", callback_data="gpay:type:once")],
            [InlineKeyboardButton("📅 Ежемесячно", callback_data="gpay:type:monthly")],
            [InlineKeyboardButton("🎟 Абонемент на занятия", callback_data="gpay:type:package")],
            [InlineKeyboardButton("Отмена", callback_data=f"gpay:member:{pid}")],
        ]),
    )
    return GPAY_TYPE


async def setup_type(update, context):
    q = update.callback_query
    await q.answer()
    data = context.user_data.get("gpay")
    if not data:
        return ConversationHandler.END
    payment_type = q.data.rsplit(":", 1)[1]
    data["type"] = payment_type
    await q.edit_message_text("Напиши сумму в рублях, например: 15000")
    return GPAY_AMOUNT


async def setup_amount(update, context):
    data = context.user_data.get("gpay")
    if not data:
        return ConversationHandler.END
    amount = _parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("Не поняла сумму. Напиши только число, например: 15000")
        return GPAY_AMOUNT
    data["amount"] = amount
    if data["type"] == "package":
        await update.message.reply_text("Сколько занятий входит в абонемент? Например: 8")
    else:
        await update.message.reply_text("На какую дату ждём оплату? Например: 28.09")
    return GPAY_FINAL


def _save_group_plan(uid, data, due=None, lessons=None):
    now = datetime.utcnow().isoformat()
    payment_type = data["type"]
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO group_member_payment_plans(
                teacher_telegram_user_id,person_id,group_id,payment_type,amount_rub,
                next_due_date,lessons_total,lessons_remaining,active,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,1,?,?)
            ON CONFLICT(teacher_telegram_user_id,person_id) DO UPDATE SET
                group_id=excluded.group_id,payment_type=excluded.payment_type,
                amount_rub=excluded.amount_rub,next_due_date=excluded.next_due_date,
                lessons_total=excluded.lessons_total,lessons_remaining=excluded.lessons_remaining,
                active=1,updated_at=excluded.updated_at
            """,
            (
                int(uid), int(data["pid"]), int(data["gid"]), payment_type, int(data["amount"]),
                due.isoformat() if due else None,
                int(lessons) if lessons is not None else None,
                int(lessons) if lessons is not None else None,
                now, now,
            ),
        )
        # A package is considered paid when it is created/replenished.
        if payment_type == "package":
            conn.execute(
                """
                INSERT INTO group_member_payment_history(
                    teacher_telegram_user_id,person_id,group_id,amount_rub,payment_type,due_date,paid_at
                ) VALUES(?,?,?,?, 'package',NULL,?)
                """,
                (int(uid), int(data["pid"]), int(data["gid"]), int(data["amount"]), now),
            )
        conn.commit()


async def setup_final(update, context):
    uid = int(update.effective_user.id)
    data = context.user_data.get("gpay")
    if not data:
        return ConversationHandler.END
    if data["type"] == "package":
        digits = "".join(ch for ch in str(update.message.text or "") if ch.isdigit())
        count = int(digits) if digits else 0
        if count <= 0 or count > 100:
            await update.message.reply_text("Напиши количество занятий числом, например: 8")
            return GPAY_FINAL
        _save_group_plan(uid, data, lessons=count)
        message = (
            f"✅ Абонемент для {data['name']} настроен.\n\n"
            f"Сумма: {_money(data['amount'])}\n"
            f"Занятий: {count}\n"
            "После отметки «Был(а)» одно занятие будет списываться автоматически."
        )
    else:
        due = schedule.parse_date(update.message.text, datetime.now(schedule.tz(uid)).date())
        if not due:
            await update.message.reply_text("Не поняла дату. Напиши, например: 28.09")
            return GPAY_FINAL
        _save_group_plan(uid, data, due=due)
        message = (
            f"✅ Оплата для {data['name']} настроена.\n\n"
            f"Сумма: {_money(data['amount'])}\n"
            f"Дата: {due.strftime('%d.%m.%Y')}"
        )
    context.user_data.pop("gpay", None)
    await update.message.reply_text(message, reply_markup=base.MAIN_KB)
    return ConversationHandler.END


async def mark_paid(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    pid = int(q.data.rsplit(":", 1)[1])
    plan = _plan(uid, pid)
    if not plan or not int(plan["active"] or 0):
        await q.edit_message_text("Активная оплата не найдена.")
        raise ApplicationHandlerStop

    now = datetime.now(schedule.tz(uid))
    due = None
    if plan["next_due_date"]:
        try:
            due = date.fromisoformat(plan["next_due_date"])
        except Exception:
            due = None

    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO group_member_payment_history(
                teacher_telegram_user_id,person_id,group_id,amount_rub,payment_type,due_date,paid_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                uid, pid, int(plan["group_id"]), int(plan["amount_rub"]),
                plan["payment_type"], due.isoformat() if due else None, now.isoformat(),
            ),
        )
        if plan["payment_type"] == "monthly":
            next_due = _add_month(due or now.date())
            conn.execute(
                "UPDATE group_member_payment_plans SET next_due_date=?,active=1,updated_at=? WHERE teacher_telegram_user_id=? AND person_id=?",
                (next_due.isoformat(), datetime.utcnow().isoformat(), uid, pid),
            )
        elif plan["payment_type"] == "package":
            total = int(plan["lessons_total"] or 0)
            next_due = None
            conn.execute(
                "UPDATE group_member_payment_plans SET lessons_remaining=?,active=1,updated_at=? WHERE teacher_telegram_user_id=? AND person_id=?",
                (total, datetime.utcnow().isoformat(), uid, pid),
            )
        else:
            next_due = None
            conn.execute(
                "UPDATE group_member_payment_plans SET active=0,updated_at=? WHERE teacher_telegram_user_id=? AND person_id=?",
                (datetime.utcnow().isoformat(), uid, pid),
            )
        conn.commit()

    text, kb = _member_card(uid, pid)
    prefix = "✅ Оплата отмечена.\n\n"
    if plan["payment_type"] == "monthly" and next_due:
        prefix += f"Следующая оплата: {next_due.strftime('%d.%m.%Y')}\n\n"
    elif plan["payment_type"] == "package":
        prefix += f"Абонемент пополнен до {int(plan['lessons_total'] or 0)} занятий.\n\n"
    await q.edit_message_text(prefix + (text or ""), reply_markup=kb)
    raise ApplicationHandlerStop


async def history(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.amount_rub,h.paid_at,m.name,g.name AS group_name
            FROM group_member_payment_history h
            JOIN student_reminder_people m ON m.id=h.person_id
            JOIN teacher_groups g ON g.id=h.group_id
            WHERE h.teacher_telegram_user_id=?
            ORDER BY h.paid_at DESC
            LIMIT 30
            """,
            (uid,),
        ).fetchall()
    lines = ["📜 Групповые оплаты"]
    for r in rows:
        try:
            stamp = datetime.fromisoformat(r["paid_at"]).strftime("%d.%m.%Y")
        except Exception:
            stamp = str(r["paid_at"])[:10]
        lines.append(f"• {stamp} · {r['name']} · {r['group_name']} · {_money(r['amount_rub'])}")
    if not rows:
        lines += ["", "История пока пустая."]
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Все оплаты", callback_data="gpay:home")]]),
    )
    raise ApplicationHandlerStop


def _reconcile_package_charge(uid, subject_kind, subject_id, slot_id, lesson_date, status):
    """Make one attendance occurrence equal exactly one package charge."""
    ensure_tables()
    if subject_kind == "individual":
        table = "student_payment_plans"
        id_col = "student_id"
    elif subject_kind == "group_member":
        table = "group_member_payment_plans"
        id_col = "person_id"
    else:
        return

    key = (int(uid), subject_kind, int(subject_id), int(slot_id), lesson_date.isoformat())
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        plan = conn.execute(
            f"""
            SELECT id,lessons_total,lessons_remaining
            FROM {table}
            WHERE teacher_telegram_user_id=? AND {id_col}=?
              AND active=1 AND payment_type='package'
            """,
            (int(uid), int(subject_id)),
        ).fetchone()
        charge = conn.execute(
            """
            SELECT 1 FROM payment_attendance_charges
            WHERE teacher_telegram_user_id=? AND subject_kind=? AND subject_id=?
              AND schedule_slot_id=? AND lesson_date=?
            """,
            key,
        ).fetchone()
        if status == "present":
            if not plan or charge:
                return
            remaining = int(plan["lessons_remaining"] or 0)
            if remaining <= 0:
                return
            conn.execute(
                f"UPDATE {table} SET lessons_remaining=?,updated_at=? WHERE id=?",
                (remaining - 1, now, int(plan["id"])),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO payment_attendance_charges(
                    teacher_telegram_user_id,subject_kind,subject_id,schedule_slot_id,lesson_date,charged_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (*key, now),
            )
            conn.commit()
            return

        # A correction from present -> absent returns the charged lesson.
        if charge:
            if plan:
                total = int(plan["lessons_total"] or 0)
                remaining = int(plan["lessons_remaining"] or 0)
                conn.execute(
                    f"UPDATE {table} SET lessons_remaining=?,updated_at=? WHERE id=?",
                    (min(total, remaining + 1), now, int(plan["id"])),
                )
            conn.execute(
                """
                DELETE FROM payment_attendance_charges
                WHERE teacher_telegram_user_id=? AND subject_kind=? AND subject_id=?
                  AND schedule_slot_id=? AND lesson_date=?
                """,
                key,
            )
            conn.commit()


_PATCHED = False


def patch_attendance():
    global _PATCHED
    if _PATCHED:
        return
    original = learning._set_attendance

    def wrapped(uid, kind, slot_id, lesson_date, subject_kind, subject_id, status):
        original(uid, kind, slot_id, lesson_date, subject_kind, subject_id, status)
        try:
            _reconcile_package_charge(uid, subject_kind, subject_id, slot_id, lesson_date, status)
        except Exception as exc:
            print(f"PREPADMIN payment attendance reconcile failed: {type(exc).__name__}: {exc}", flush=True)

    learning._set_attendance = wrapped
    _PATCHED = True


def _group_payment_payload(uid, pid):
    row = _plan(uid, pid)
    if not row or not int(row["active"] or 0):
        return {"short": "не настроена", "hint": "", "full": "Активная оплата пока не настроена."}
    amount_text = _money(row["amount_rub"])
    if row["payment_type"] == "package":
        left = int(row["lessons_remaining"] or 0)
        total = int(row["lessons_total"] or 0)
        return {
            "short": f"{left}/{total}",
            "hint": "занятий осталось",
            "full": f"Абонемент: {amount_text}. Осталось {left} из {total} занятий.",
        }
    due_text = row["next_due_date"]
    if not due_text:
        return {"short": amount_text, "hint": "", "full": f"Сумма: {amount_text}."}
    due = date.fromisoformat(due_text)
    today = datetime.now(schedule.tz(uid)).date()
    if due < today:
        short, hint = "просрочено", due.strftime("%d.%m")
    elif due == today:
        short, hint = "сегодня", amount_text
    else:
        short, hint = "до " + due.strftime("%d.%m"), amount_text
    return {"short": short, "hint": hint, "full": f"{amount_text}. Следующая дата оплаты: {due.strftime('%d.%m.%Y')}."}


def patch_student_webapp():
    original = student_webapp._payment

    def payment(link):
        if link["kind"] == "group" and link["group_id"]:
            return _group_payment_payload(int(link["teacher_id"]), int(link["id"]))
        return original(link)

    student_webapp._payment = payment


def patch_teacher_webapp():
    original_payments = webapp._payments_view
    original_dashboard = webapp._dashboard

    def payments_view(uid):
        data = original_payments(uid)
        items = list(data.get("items") or [])
        with base.db() as conn:
            rows = conn.execute(
                """
                SELECT m.name,g.name AS group_name,p.payment_type,p.amount_rub,p.next_due_date,
                       p.lessons_total,p.lessons_remaining,p.active
                FROM student_reminder_people m
                JOIN teacher_groups g ON g.id=m.group_id
                LEFT JOIN group_member_payment_plans p
                  ON p.person_id=m.id AND p.teacher_telegram_user_id=m.teacher_id
                WHERE m.teacher_id=? AND m.kind='group' AND m.active=1 AND g.active=1
                ORDER BY lower(g.name),lower(m.name)
                """,
                (int(uid),),
            ).fetchall()
        today_local = datetime.now(schedule.tz(uid)).date()
        for r in rows:
            status, level = "Не настроено", "muted"
            if r["payment_type"] and int(r["active"] or 0):
                if r["payment_type"] == "package":
                    left = int(r["lessons_remaining"] or 0)
                    total = int(r["lessons_total"] or 0)
                    status = f"Осталось {left}/{total} занятий"
                    level = "bad" if left <= 0 else "ok"
                elif r["next_due_date"]:
                    due = date.fromisoformat(r["next_due_date"])
                    if due < today_local:
                        status, level = "Просрочено", "bad"
                    elif due == today_local:
                        status, level = "Оплата сегодня", "warn"
                    else:
                        status, level = "До " + due.strftime("%d.%m"), "ok"
            items.append({
                "name": f"{r['name']} · {r['group_name']}",
                "amount": int(r["amount_rub"] or 0),
                "status": status,
                "level": level,
            })
        return {**data, "items": items}

    def dashboard(uid):
        data = original_dashboard(uid)
        today_local = datetime.now(schedule.tz(uid)).date()
        with base.db() as conn:
            rows = conn.execute(
                """
                SELECT m.name,g.name AS group_name,p.amount_rub,p.payment_type,p.next_due_date,
                       p.lessons_remaining,p.active
                FROM group_member_payment_plans p
                JOIN student_reminder_people m ON m.id=p.person_id
                JOIN teacher_groups g ON g.id=p.group_id
                WHERE p.teacher_telegram_user_id=? AND p.active=1
                  AND m.active=1 AND g.active=1
                """,
                (int(uid),),
            ).fetchall()
        debts = []
        for r in rows:
            overdue = False
            detail = _money(r["amount_rub"])
            due = ""
            if r["payment_type"] == "package":
                if int(r["lessons_remaining"] or 0) <= 0:
                    overdue = True
                    detail = "Абонемент закончился"
            elif r["next_due_date"]:
                due_date = date.fromisoformat(r["next_due_date"])
                due = r["next_due_date"]
                overdue = due_date <= today_local
            if overdue:
                debts.append({
                    "kind": "payment",
                    "name": f"{r['name']} · {r['group_name']}",
                    "title": "Оплата",
                    "detail": detail,
                    "due": due,
                    "overdue": True,
                })
        result = dict(data)
        counts = dict(result.get("counts") or {})
        counts["payments"] = int(counts.get("payments") or 0) + len(debts)
        result["counts"] = counts
        result["debts"] = list(result.get("debts") or []) + debts
        return result

    webapp._payments_view = payments_view
    webapp._dashboard = dashboard


def patch_reports():
    original_stats = reports._stats
    original_aggregate = reports._aggregate

    def stats(uid, kind, subject_id, start, end, payment_sid=None):
        result = original_stats(uid, kind, subject_id, start, end, payment_sid)
        if kind == "group_member":
            row = _plan(uid, subject_id)
            text, problem = _status(uid, row)
            result = dict(result)
            result["pay_text"] = text
            result["pay_problem"] = problem == "bad"
        return result

    def aggregate(uid, indiv, members, start, end):
        result = original_aggregate(uid, indiv, members, start, end)
        issues = 0
        for pid in members:
            _text, level = _status(uid, _plan(uid, pid))
            issues += int(level == "bad")
        result = dict(result)
        result["payment_issues"] = int(result.get("payment_issues") or 0) + issues
        return result

    reports._stats = stats
    reports._aggregate = aggregate


def validate():
    ensure_tables()
    with base.db() as conn:
        required = {
            "group_member_payment_plans",
            "group_member_payment_history",
            "payment_attendance_charges",
        }
        actual = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = required - actual
    if missing:
        raise RuntimeError("Group payment tables missing: " + ", ".join(sorted(missing)))
    print("PREPADMIN group payments ready: per-member plans + package attendance charging", flush=True)


def install(app):
    ensure_tables()
    patch_attendance()
    patch_student_webapp()
    patch_teacher_webapp()
    patch_reports()

    setup = ConversationHandler(
        entry_points=[CallbackQueryHandler(setup_begin, pattern=r"^gpay:setup:\d+$")],
        states={
            GPAY_TYPE: [CallbackQueryHandler(setup_type, pattern=r"^gpay:type:(?:once|monthly|package)$")],
            GPAY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_amount)],
            GPAY_FINAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_final)],
        },
        fallbacks=[],
        per_message=False,
    )
    app.add_handler(setup, group=-2)
    app.add_handler(MessageHandler(filters.Regex(r"^💳 Оплаты$"), payments_home), group=-2)
    app.add_handler(CallbackQueryHandler(home_callback, pattern=r"^gpay:home$"), group=-2)
    app.add_handler(CallbackQueryHandler(individual_view, pattern=r"^gpay:individual$"), group=-2)
    app.add_handler(CallbackQueryHandler(groups_view, pattern=r"^gpay:groups$"), group=-2)
    app.add_handler(CallbackQueryHandler(group_view, pattern=r"^gpay:group:\d+$"), group=-2)
    app.add_handler(CallbackQueryHandler(member_view, pattern=r"^gpay:member:\d+$"), group=-2)
    app.add_handler(CallbackQueryHandler(mark_paid, pattern=r"^gpay:paid:\d+$"), group=-2)
    app.add_handler(CallbackQueryHandler(history, pattern=r"^gpay:history$"), group=-2)
    validate()
