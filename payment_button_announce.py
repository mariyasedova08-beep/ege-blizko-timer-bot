"""One-time DM announcing the new student payment button."""
import sqlite3
from datetime import datetime

import payment_delivery
import payment_schedule
import payment_student_ui

ANNOUNCEMENT_KEY = "payment_button_2026_09_12_v1"


def _bot():
    return payment_schedule._bot


def ensure_table():
    with sqlite3.connect(_bot().COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_feature_announcements (
                payment_student_id INTEGER NOT NULL,
                announcement_key TEXT NOT NULL,
                telegram_user_id INTEGER,
                sent_at TEXT,
                PRIMARY KEY(payment_student_id, announcement_key)
            )
            """
        )
        conn.commit()


def _already_sent(student_id):
    with sqlite3.connect(_bot().COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM payment_feature_announcements
            WHERE payment_student_id = ? AND announcement_key = ?
            """,
            (int(student_id), ANNOUNCEMENT_KEY),
        ).fetchone()
    return bool(row)


def _mark_sent(student_id, telegram_id):
    now = datetime.now(_bot().TIMEZONE).isoformat()
    with sqlite3.connect(_bot().COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO payment_feature_announcements
                (payment_student_id, announcement_key, telegram_user_id, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(student_id), ANNOUNCEMENT_KEY, int(telegram_id), now),
        )
        conn.commit()


def _text():
    return (
        "Привет! 💗\n\n"
        "В твоём личном кабинете появилась новая кнопка <b>«💳 Оплата»</b>.\n\n"
        "Теперь там можно в любой момент посмотреть:\n"
        "• что уже оплачено;\n"
        "• свой график оплаты;\n"
        "• сумму и срок следующего платежа.\n\n"
        "После оплаты, пожалуйста, пришли Маше расчётный чек — после того как платёж будет отмечен, информация в кабинете обновится.\n\n"
        "Кнопка уже в меню ниже 👇"
    )


async def send_once(context):
    ensure_table()
    sent, skipped, failed = [], [], []
    for row in payment_schedule.schedule_rows():
        if _already_sent(row["id"]):
            skipped.append(row["name"])
            continue
        recipient = payment_delivery._recipient(row)
        if not recipient:
            failed.append(row["name"])
            continue
        telegram_id, _label = recipient
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=_text(),
                parse_mode="HTML",
                reply_markup=payment_student_ui.live7.STUDENT_KEYBOARD,
            )
            _mark_sent(row["id"], telegram_id)
            sent.append(row["name"])
        except Exception:
            failed.append(row["name"])

    print(
        f"PAYMENT_BUTTON_ANNOUNCE sent={len(sent)} skipped={len(skipped)} failed={len(failed)}",
        flush=True,
    )
    if failed:
        print("PAYMENT_BUTTON_ANNOUNCE_FAILED " + " | ".join(failed), flush=True)

    admin_id = _bot().get_admin_id()
    if admin_id and (sent or failed):
        lines = ["💳 Кнопка «Оплата»: личная рассылка"]
        if sent:
            lines.append(f"✅ Отправлено: {len(sent)}")
        if failed:
            lines.append(f"⚠️ Не отправлено: {len(failed)} — " + ", ".join(failed))
        await context.bot.send_message(chat_id=int(admin_id), text="\n".join(lines))


def register(application):
    ensure_table()
    application.job_queue.run_once(send_once, when=3, name="payment_button_announce_once")
    print("Payment button announcement job registered", flush=True)
