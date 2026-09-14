"""Keep the attention zone compatible with the migrated parent schema.

The parent-schema migration renamed ``parent_links.telegram_user_id`` to
``parent_telegram_user_id``.  The attention-zone module predates that migration,
so this final compatibility layer accepts either schema without changing data.
"""

import sqlite3
import secrets
from datetime import datetime, timedelta

import run_bot_live90 as live90


live34 = live90.live79.live34
bot = live34.bot


def _columns(conn, table):
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _parent_link_layout(conn):
    columns = _columns(conn, "parent_links")
    user_column = (
        "parent_telegram_user_id"
        if "parent_telegram_user_id" in columns
        else "telegram_user_id"
        if "telegram_user_id" in columns
        else None
    )
    name_column = (
        "parent_name"
        if "parent_name" in columns
        else "telegram_name"
        if "telegram_name" in columns
        else None
    )
    if not user_column or not name_column:
        raise RuntimeError("parent_links schema has no supported Telegram columns")
    return user_column, name_column


def _parents_for_student_compat(conn, student_id):
    user_column, name_column = _parent_link_layout(conn)
    return conn.execute(
        f"""
        SELECT {user_column} AS telegram_user_id,
               {name_column} AS telegram_name
        FROM parent_links
        WHERE student_id = ? AND active = 1
        ORDER BY rowid
        """,
        (int(student_id),),
    ).fetchall()


def _invite_column(conn):
    columns = _columns(conn, "parent_invites")
    if "token" in columns:
        return "token", True
    if "code" in columns:
        return "code", False
    raise RuntimeError("parent_invites schema has no supported token column")


def _make_parent_invite_compat(student_id):
    code = secrets.token_hex(4)
    now = datetime.now(bot.TIMEZONE)
    expires = now + timedelta(hours=live34.PARENT_INVITE_HOURS)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        invite_column, modern = _invite_column(conn)
        if modern:
            conn.execute(
                f"""
                INSERT INTO parent_invites (token, student_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, int(student_id), now.isoformat(), expires.isoformat()),
            )
        else:
            conn.execute(
                f"""
                INSERT INTO parent_invites ({invite_column}, student_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (code, int(student_id), now.isoformat(), expires.isoformat()),
            )
        conn.commit()
    return code, expires


async def _link_parent_from_start_compat(update, context, code):
    if update.effective_chat.type != "private":
        return
    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        invite_column, modern = _invite_column(conn)
        row = conn.execute(
            f"""
            SELECT i.student_id, i.expires_at, i.used_at
            FROM parent_invites i
            JOIN students s ON s.id = i.student_id
            WHERE i.{invite_column} = ? AND s.active = 1
            LIMIT 1
            """,
            (code,),
        ).fetchone()
        if not row:
            await update.message.reply_text(
                "Ссылка для родителя не найдена. Попросите преподавателя создать новую."
            )
            return
        student_id, expires_text, used_at = row
        try:
            expires = datetime.fromisoformat(expires_text)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=bot.TIMEZONE)
        except Exception:
            expires = now - timedelta(seconds=1)
        if now > expires:
            await update.message.reply_text(
                "Срок действия ссылки закончился. Попросите преподавателя создать новую."
            )
            return

        student = next(
            (row for row in live34._student_rows() if int(row[0]) == int(student_id)),
            None,
        )
        if not student:
            await update.message.reply_text("Ученик сейчас недоступен. Напишите Марии Александровне.")
            return

        user = update.effective_user
        user_column, name_column = _parent_link_layout(conn)
        if user_column == "parent_telegram_user_id":
            conn.execute(
                """
                INSERT INTO parent_links
                    (parent_telegram_user_id, student_id, parent_username, parent_name, active, linked_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(parent_telegram_user_id, student_id) DO UPDATE SET
                    parent_username = excluded.parent_username,
                    parent_name = excluded.parent_name,
                    active = 1,
                    linked_at = excluded.linked_at
                """,
                (
                    int(user.id),
                    int(student_id),
                    user.username or "",
                    user.full_name or "",
                    now.isoformat(),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO parent_links
                    (student_id, telegram_user_id, telegram_username, telegram_name, active, linked_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(student_id, telegram_user_id) DO UPDATE SET
                    telegram_username = excluded.telegram_username,
                    telegram_name = excluded.telegram_name,
                    active = 1,
                    linked_at = excluded.linked_at
                """,
                (
                    int(student_id),
                    int(user.id),
                    user.username or "",
                    user.full_name or "",
                    now.isoformat(),
                ),
            )
        if modern:
            conn.execute(
                "UPDATE parent_invites SET used_at = ?, used_by = ? WHERE token = ?",
                (now.isoformat(), int(user.id), code),
            )
        else:
            conn.execute(
                "UPDATE parent_invites SET used_at = ? WHERE code = ?",
                (now.isoformat(), code),
            )
        conn.commit()

    await update.message.reply_text(
        f"✅ Готово! Вы подключены как родитель ученика {live34._shown_name(student)}.\n\n"
        "Если учебная ситуация потребует внимания и не улучшится после личного напоминания ученику, бот пришлёт вам уведомление."
    )


live34._parents_for_student = _parents_for_student_compat
live34._make_parent_invite = _make_parent_invite_compat
live34._link_parent_from_start = _link_parent_from_start_compat


def verify_attention_parent_schema_compatibility():
    live34.ensure_attention_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        _parent_link_layout(conn)
        _invite_column(conn)
    print("LIVE97: attention zone supports migrated parent schema", flush=True)


verify_attention_parent_schema_compatibility()

