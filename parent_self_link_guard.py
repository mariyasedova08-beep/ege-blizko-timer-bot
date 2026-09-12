"""Prevent students from linking the parent cabinet to their own Telegram account.

Also repairs any existing self-links and reopens still-valid invites that were
consumed by the student themselves, so the same invitation can be forwarded to
an actual parent.
"""
import sqlite3

import parent_cabinet

bot = parent_cabinet.bot
_original_consume = parent_cabinet.consume


def _repair_existing_self_links():
    parent_cabinet.ensure_tables()
    now_iso = parent_cabinet.now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT pl.parent_telegram_user_id, pl.student_id
            FROM parent_links pl
            JOIN students s ON s.id = pl.student_id
            WHERE pl.active = 1
              AND s.telegram_user_id IS NOT NULL
              AND pl.parent_telegram_user_id = s.telegram_user_id
            """
        ).fetchall()
        for telegram_user_id, student_id in rows:
            conn.execute(
                """
                UPDATE parent_links
                SET active = 0
                WHERE parent_telegram_user_id = ? AND student_id = ?
                """,
                (int(telegram_user_id), int(student_id)),
            )
            # If the student's own account consumed the invite, make a still-valid
            # invitation usable again by the real parent.
            conn.execute(
                """
                UPDATE parent_invites
                SET used_at = NULL, used_by = NULL
                WHERE student_id = ?
                  AND used_by = ?
                  AND expires_at >= ?
                """,
                (int(student_id), int(telegram_user_id), now_iso),
            )
        conn.commit()
    return len(rows)


def consume_without_self_link(token, user):
    parent_cabinet.ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT student_id FROM parent_invites WHERE token = ?",
            (str(token),),
        ).fetchone()
    if row:
        student = parent_cabinet.student_by_id(int(row[0]))
        if student and student[4] is not None and int(student[4]) == int(user.id):
            return None, (
                "Эта ссылка предназначена для родителя. "
                "Откройте её с Telegram-аккаунта родителя или перешлите ему это приглашение."
            )
    return _original_consume(token, user)


parent_cabinet.consume = consume_without_self_link
_repaired = _repair_existing_self_links()
print(f"Parent self-link guard ready: repaired={_repaired}", flush=True)
