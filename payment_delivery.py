"""Safe automatic Grade 11 payment reminders.

Delivery is idempotent, starts on 2026-09-28, and only sends to an exactly
matched active Telegram-linked student. Payment coverage is re-read on every
run, so marking a payment prevents later reminders.
"""
import html
import sqlite3
from datetime import date, datetime, timedelta

import payment_schedule

LAUNCH_DATE = date(2026, 9, 28)
SEND_TIME = "10:00"


def _payments():
    return payment_schedule._payments


def _bot():
    return payment_schedule._bot


def ensure_tables():
    payment_schedule.ensure_payment_plans()
    bot = _bot()
    payments = _payments()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_delivery_events (
                payment_student_id INTEGER NOT NULL,
                period TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('notice','followup','overdue')),
                telegram_user_id INTEGER,
                status TEXT NOT NULL CHECK(status IN ('sent','failed')),
                sent_at TEXT,
                error TEXT,
                PRIMARY KEY(payment_student_id, period, kind)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_delivery_migrations (
                migration_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        key = "enable_student_messages_2026_09_28_v1"
        applied = conn.execute(
            "SELECT 1 FROM payment_delivery_migrations WHERE migration_key = ?", (key,)
        ).fetchone()
        if not applied:
            now = datetime.now(bot.TIMEZONE).isoformat()
            conn.execute(
                """
                UPDATE payment_students
                SET student_messages_enabled = 1, updated_at = ?
                WHERE active = 1 AND source_sheet = ?
                """,
                (now, payments.PAYMENT_SHEET_NAME),
            )
            conn.execute(
                "INSERT INTO payment_delivery_migrations(migration_key, applied_at) VALUES (?, ?)",
                (key, now),
            )
        conn.commit()


def _recipient(row):
    """Return one exact Telegram recipient by the already-installed stable name key."""
    bot = _bot()
    payments = _payments()
    target = payments._name_key(row["name"])
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT telegram_user_id,
                   coalesce(nullif(display_name, ''), ''),
                   coalesce(nullif(user_name, ''), ''),
                   coalesce(user_email, '')
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
            """
        ).fetchall()
    matches = {}
    for telegram_id, display_name, user_name, email in students:
        for candidate in (display_name, user_name):
            if candidate and payments._name_key(candidate) == target:
                matches[int(telegram_id)] = display_name or user_name or email
                break
    if len(matches) != 1:
        return None
    telegram_id = next(iter(matches))
    return telegram_id, matches[telegram_id]


def audit():
    ensure_tables()
    eligible = [
        row for row in payment_schedule.schedule_rows()
        if row["cadence"] in ("monthly", "quarterly")
    ]
    linked, missing = [], []
    for row in eligible:
        if _recipient(row):
            linked.append(row["name"])
        else:
            missing.append(row["name"])
    print(
        f"PAYMENT_DELIVERY_AUDIT eligible={len(eligible)} linked={len(linked)} "
        f"unmapped={len(missing)} launch={LAUNCH_DATE.isoformat()} time={SEND_TIME}",
        flush=True,
    )
    if missing:
        print("PAYMENT_DELIVERY_UNMAPPED " + " | ".join(missing), flush=True)
    return linked, missing


def _already_sent(student_id, period, kind):
    with sqlite3.connect(_bot().COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT status FROM payment_delivery_events
            WHERE payment_student_id = ? AND period = ? AND kind = ?
            """,
            (student_id, period, kind),
        ).fetchone()
    return bool(row and row[0] == "sent")


def _record(student_id, period, kind, telegram_id, status, error=None):
    bot = _bot()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO payment_delivery_events
                (payment_student_id, period, kind, telegram_user_id, status, sent_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(payment_student_id, period, kind) DO UPDATE SET
                telegram_user_id = excluded.telegram_user_id,
                status = excluded.status,
                sent_at = excluded.sent_at,
                error = excluded.error
            """,
            (student_id, period, kind, telegram_id, status, now, error),
        )
        conn.commit()


def _kind(item, today):
    if today < LAUNCH_DATE:
        return None
    first_notice = max(item["notice_date"], LAUNCH_DATE)
    followup = item["due_date"].replace(day=5)
    overdue = item["due_date"] + timedelta(days=1)
    if today >= overdue:
        return "overdue"
    if today >= followup:
        return "followup"
    if today >= first_notice:
        return "notice"
    return None


def _message(item, kind):
    amount = payment_schedule.money(item["remaining_cents"])
    due = item["due_date"].strftime("%d.%m.%Y")
    label = html.escape(item["label"])
    if kind == "notice":
        return (
            f"Привет! 💗 Напоминаю об оплате курса за {label}.\n"
            f"Сумма: <b>{amount}</b>.\n"
            f"Пожалуйста, внеси оплату до <b>{due}</b> включительно.\n\n"
            "После оплаты, пожалуйста, пришли Маше расчётный чек, чтобы она отметила платёж. 💗"
        )
    if kind == "followup":
        return (
            f"Привет! 💗 Небольшое напоминание об оплате курса за {label}.\n"
            f"К оплате: <b>{amount}</b>, срок — до <b>{due}</b> включительно.\n\n"
            "Если оплата уже внесена, пришли Маше расчётный чек, чтобы она отметила платёж. 💗"
        )
    return (
        f"Привет! 💗 Напоминаю, что срок оплаты курса за {label} был до <b>{due}</b>.\n"
        f"Сейчас к оплате: <b>{amount}</b>.\n\n"
        "Если оплата уже внесена, пришли Маше расчётный чек. Если ещё нет — пожалуйста, внеси оплату и тоже пришли чек Маше. 💗"
    )


async def tick(context):
    ensure_tables()
    bot = _bot()
    today = bot.today_moscow()
    if today < LAUNCH_DATE:
        return
    sent, missing, failed = [], [], []
    for row in payment_schedule.schedule_rows(today):
        if not row.get("messages_enabled"):
            continue
        item = row["next_invoice"]
        if not item:
            continue
        kind = _kind(item, today)
        if not kind or _already_sent(row["id"], item["period"], kind):
            continue
        recipient = _recipient(row)
        if not recipient:
            missing.append(row["name"])
            continue
        telegram_id, _label = recipient
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=_message(item, kind),
                parse_mode="HTML",
            )
            _record(row["id"], item["period"], kind, telegram_id, "sent")
            sent.append(row["name"])
        except Exception as exc:
            _record(row["id"], item["period"], kind, telegram_id, "failed", repr(exc)[:500])
            failed.append(row["name"])

    if sent or missing or failed:
        admin_id = bot.get_admin_id()
        if admin_id:
            lines = ["💳 Рассылка по оплатам"]
            if sent:
                lines.append(f"✅ Отправлено: {len(sent)} — " + ", ".join(sent))
            if missing:
                lines.append(f"🔗 Telegram не сопоставлен: {len(missing)} — " + ", ".join(missing))
            if failed:
                lines.append(f"⚠️ Ошибка отправки: {len(failed)} — " + ", ".join(failed))
            await context.bot.send_message(chat_id=int(admin_id), text="\n".join(lines))


def register_jobs(application):
    bot = _bot()
    ensure_tables()
    audit()
    application.job_queue.run_daily(
        tick,
        time=datetime.strptime(SEND_TIME, "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        name="grade11_payment_delivery",
    )
    print(
        f"Payment delivery enabled: launch={LAUNCH_DATE.isoformat()} daily={SEND_TIME}; "
        "followup=day5 overdue=day8",
        flush=True,
    )
