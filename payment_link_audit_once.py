"""One-time privacy-safe audit for unresolved payment Telegram recipients."""
import sqlite3

import run_bot_live85 as payments

bot = payments.bot
TARGETS = {
    "Силинг Иосиф": "iosifsiling@gmail.com",
    "Трубецкая Василисса": "kenvijj@gmail.com",
}


def main():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for label, email in TARGETS.items():
            rows = conn.execute(
                """
                SELECT id,
                       coalesce(nullif(display_name, ''), ''),
                       coalesce(nullif(user_name, ''), ''),
                       telegram_user_id IS NOT NULL AS has_telegram,
                       active
                FROM students
                WHERE lower(coalesce(user_email, '')) = lower(?)
                ORDER BY active DESC, id
                """,
                (email,),
            ).fetchall()
            print(f"PAYMENT_LINK_AUDIT target={label} email_matches={len(rows)}", flush=True)
            for sid, display_name, user_name, has_telegram, active in rows:
                print(
                    f"PAYMENT_LINK_ROW target={label} student_id={sid} active={int(active or 0)} "
                    f"telegram={'yes' if has_telegram else 'no'} display={display_name or '-'} user={user_name or '-'}",
                    flush=True,
                )


main()
