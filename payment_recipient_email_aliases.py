"""Exact e-mail fallback for payment recipients whose Core display name differs."""
import sqlite3

import payment_delivery

EMAIL_BY_KEY = {
    "еся": "iosifsiling@gmail.com",
    "вася": "kenvijj@gmail.com",
}

_original_recipient = payment_delivery._recipient


def recipient_with_email_fallback(row):
    direct = _original_recipient(row)
    if direct:
        return direct

    payments = payment_delivery._payments()
    bot = payment_delivery._bot()
    key = payments._name_key(row["name"])
    email = EMAIL_BY_KEY.get(key)
    if not email:
        return None

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT telegram_user_id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, '')
            FROM students
            WHERE active = 1
              AND telegram_user_id IS NOT NULL
              AND lower(coalesce(user_email, '')) = lower(?)
            """,
            (email,),
        ).fetchall()
    unique = {int(tid): label for tid, label in rows if tid is not None}
    if len(unique) != 1:
        return None
    telegram_id = next(iter(unique))
    return telegram_id, unique[telegram_id]


payment_delivery._recipient = recipient_with_email_fallback
print("Payment recipient email aliases loaded", flush=True)
