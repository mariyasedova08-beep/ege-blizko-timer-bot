"""One-time privacy-safe audit for unresolved payment Telegram recipients."""
import sqlite3

import run_bot_live85 as payments

bot = payments.bot
TARGETS = {
    "Силинг Иосиф": "iosifsiling@gmail.com",
    "Трубецкая Василисса": "kenvijj@gmail.com",
}


def _same_name(candidate, label):
    return bool(candidate and payments._name_key(candidate) == payments._name_key(label))


def main():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        all_students = conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), ''),
                   coalesce(nullif(user_name, ''), ''),
                   coalesce(nullif(telegram_username, ''), ''),
                   coalesce(nullif(user_email, ''), ''),
                   telegram_user_id IS NOT NULL AS has_telegram,
                   active
            FROM students
            ORDER BY active DESC, id
            """
        ).fetchall()

        poll_rows = []
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='probnik_poll_answers'"
        ).fetchone()
        if table_exists:
            poll_rows = conn.execute(
                """
                SELECT telegram_user_id,
                       coalesce(nullif(telegram_name, ''), ''),
                       coalesce(nullif(telegram_username, ''), '')
                FROM probnik_poll_answers
                """
            ).fetchall()

        for label, email in TARGETS.items():
            email_rows = conn.execute(
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
            print(f"PAYMENT_LINK_AUDIT target={label} email_matches={len(email_rows)}", flush=True)
            for sid, display_name, user_name, has_telegram, active in email_rows:
                print(
                    f"PAYMENT_LINK_ROW target={label} student_id={sid} active={int(active or 0)} "
                    f"telegram={'yes' if has_telegram else 'no'} display={display_name or '-'} user={user_name or '-'}",
                    flush=True,
                )

            name_rows = [
                row for row in all_students
                if _same_name(row[1], label) or _same_name(row[2], label)
            ]
            print(f"PAYMENT_LINK_NAME_AUDIT target={label} name_matches={len(name_rows)}", flush=True)
            for sid, display_name, user_name, telegram_username, _email, has_telegram, active in name_rows:
                print(
                    f"PAYMENT_LINK_NAME_ROW target={label} student_id={sid} active={int(active or 0)} "
                    f"telegram={'yes' if has_telegram else 'no'} display={display_name or '-'} "
                    f"user={user_name or '-'} tguser={telegram_username or '-'}",
                    flush=True,
                )

            poll_matches = {}
            for telegram_id, telegram_name, telegram_username in poll_rows:
                if _same_name(telegram_name, label):
                    poll_matches[int(telegram_id)] = (telegram_name, telegram_username)
            print(f"PAYMENT_LINK_POLL_AUDIT target={label} telegram_matches={len(poll_matches)}", flush=True)
            for _telegram_id, (telegram_name, telegram_username) in poll_matches.items():
                print(
                    f"PAYMENT_LINK_POLL_ROW target={label} telegram=yes name={telegram_name or '-'} "
                    f"tguser={telegram_username or '-'}",
                    flush=True,
                )

        active_payment_keys = {
            str(row[0]) for row in conn.execute(
                "SELECT source_key FROM payment_students WHERE active = 1 AND source_sheet = ?",
                (payments.PAYMENT_SHEET_NAME,),
            ).fetchall()
        }
        known_email_keys = {
            "kenvijj@gmail.com": "вася",
            "iosifsiling@gmail.com": "еся",
        }
        unmatched = []
        for sid, display_name, user_name, telegram_username, email, has_telegram, active in all_students:
            if not active or not has_telegram:
                continue
            keys = {
                payments._name_key(value)
                for value in (display_name, user_name)
                if value
            }
            claimed = bool(keys & active_payment_keys)
            if not claimed and email:
                claimed = known_email_keys.get(email.casefold()) in active_payment_keys
            if not claimed:
                unmatched.append((sid, display_name, user_name, telegram_username))

        print(f"PAYMENT_LINK_UNCLAIMED linked_active={len(unmatched)}", flush=True)
        for sid, display_name, user_name, telegram_username in unmatched:
            print(
                f"PAYMENT_LINK_UNCLAIMED_ROW student_id={sid} display={display_name or '-'} "
                f"user={user_name or '-'} tguser={telegram_username or '-'}",
                flush=True,
            )


main()
