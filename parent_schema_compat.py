"""One-time compatibility migration for legacy parent cabinet SQLite tables.

The project already had an older parent cabinet schema. New parent modules use clearer
column names. This migration preserves legacy rows in backup tables, rebuilds the two
parent tables in the current schema, and is idempotent on future restarts.
"""
import sqlite3

import parent_cabinet

bot = parent_cabinet.bot

INVITE_REQUIRED = {"token", "student_id", "created_at", "expires_at", "used_at", "used_by"}
LINK_REQUIRED = {
    "parent_telegram_user_id", "student_id", "parent_username", "parent_name", "active", "linked_at"
}


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _exists(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def _migrate_invites(conn):
    cols = _columns(conn, "parent_invites")
    if INVITE_REQUIRED.issubset(cols):
        return False
    if not cols:
        conn.execute("""CREATE TABLE parent_invites(
            token TEXT PRIMARY KEY, student_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, used_at TEXT, used_by INTEGER)""")
        return True
    if "code" not in cols:
        raise RuntimeError(f"Unsupported parent_invites schema: {sorted(cols)}")

    if not _exists(conn, "parent_invites_legacy_backup_20260912"):
        conn.execute("CREATE TABLE parent_invites_legacy_backup_20260912 AS SELECT * FROM parent_invites")

    conn.execute("DROP TABLE IF EXISTS parent_invites_new_20260912")
    conn.execute("""CREATE TABLE parent_invites_new_20260912(
        token TEXT PRIMARY KEY, student_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, used_at TEXT, used_by INTEGER)""")
    conn.execute("""
        INSERT OR IGNORE INTO parent_invites_new_20260912
            (token, student_id, created_at, expires_at, used_at, used_by)
        SELECT
            pi.code,
            pi.student_id,
            pi.created_at,
            pi.expires_at,
            pi.used_at,
            CASE
                WHEN pi.used_at IS NULL THEN NULL
                ELSE COALESCE((
                    SELECT pl.telegram_user_id
                    FROM parent_links pl
                    WHERE pl.student_id = pi.student_id
                      AND COALESCE(pl.active, 1) = 1
                      AND pl.telegram_user_id IS NOT NULL
                    ORDER BY pl.linked_at DESC
                    LIMIT 1
                ), -1)
            END
        FROM parent_invites pi
        WHERE pi.code IS NOT NULL AND trim(pi.code) <> ''
    """)
    conn.execute("DROP TABLE parent_invites")
    conn.execute("ALTER TABLE parent_invites_new_20260912 RENAME TO parent_invites")
    return True


def _migrate_links(conn):
    cols = _columns(conn, "parent_links")
    if LINK_REQUIRED.issubset(cols):
        return False
    if not cols:
        conn.execute("""CREATE TABLE parent_links(
            parent_telegram_user_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
            parent_username TEXT, parent_name TEXT, active INTEGER NOT NULL DEFAULT 1,
            linked_at TEXT NOT NULL, PRIMARY KEY(parent_telegram_user_id, student_id))""")
        return True
    if "telegram_user_id" not in cols:
        raise RuntimeError(f"Unsupported parent_links schema: {sorted(cols)}")

    if not _exists(conn, "parent_links_legacy_backup_20260912"):
        conn.execute("CREATE TABLE parent_links_legacy_backup_20260912 AS SELECT * FROM parent_links")

    conn.execute("DROP TABLE IF EXISTS parent_links_new_20260912")
    conn.execute("""CREATE TABLE parent_links_new_20260912(
        parent_telegram_user_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
        parent_username TEXT, parent_name TEXT, active INTEGER NOT NULL DEFAULT 1,
        linked_at TEXT NOT NULL, PRIMARY KEY(parent_telegram_user_id, student_id))""")
    conn.execute("""
        INSERT OR IGNORE INTO parent_links_new_20260912
            (parent_telegram_user_id, student_id, parent_username, parent_name, active, linked_at)
        SELECT
            telegram_user_id,
            student_id,
            COALESCE(telegram_username, ''),
            COALESCE(telegram_name, ''),
            COALESCE(active, 1),
            COALESCE(linked_at, datetime('now'))
        FROM parent_links
        WHERE telegram_user_id IS NOT NULL AND student_id IS NOT NULL
    """)
    conn.execute("DROP TABLE parent_links")
    conn.execute("ALTER TABLE parent_links_new_20260912 RENAME TO parent_links")
    return True


def migrate():
    with sqlite3.connect(bot.COREAPP_DB_PATH, timeout=20) as conn:
        conn.execute("BEGIN IMMEDIATE")
        invite_changed = _migrate_invites(conn)
        link_changed = _migrate_links(conn)
        invite_cols = _columns(conn, "parent_invites")
        link_cols = _columns(conn, "parent_links")
        if not INVITE_REQUIRED.issubset(invite_cols):
            raise RuntimeError(f"parent_invites migration validation failed: {sorted(invite_cols)}")
        if not LINK_REQUIRED.issubset(link_cols):
            raise RuntimeError(f"parent_links migration validation failed: {sorted(link_cols)}")
        invites = int(conn.execute("SELECT COUNT(*) FROM parent_invites").fetchone()[0] or 0)
        links = int(conn.execute("SELECT COUNT(*) FROM parent_links").fetchone()[0] or 0)
        conn.commit()
    print(
        f"Parent schema compatibility ready: invites_migrated={int(invite_changed)} "
        f"links_migrated={int(link_changed)} invites={invites} links={links}",
        flush=True,
    )


migrate()
