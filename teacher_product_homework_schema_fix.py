"""SQLite-safe schema installer and migration for PREPODMIN homework/attendance."""

import teacher_product_mvp as base
import teacher_product_student_reminders as student_reminders


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing(conn, table, definitions):
    existing = _columns(conn, table)
    for name, ddl in definitions.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def ensure_tables():
    student_reminders.ensure_tables()
    with base.db() as conn:
        # Create a minimal compatible table if it does not exist, then migrate any
        # older table with the same name by adding only the missing columns.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """
        )
        _add_missing(conn, "teacher_attendance", {
            "teacher_telegram_user_id": "INTEGER",
            "lesson_kind": "TEXT",
            "schedule_slot_id": "INTEGER",
            "lesson_date": "TEXT",
            "student_id": "INTEGER",
            "person_id": "INTEGER",
            "person_name": "TEXT",
            "status": "TEXT",
            "marked_at": "TEXT",
        })

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """
        )
        _add_missing(conn, "teacher_homework", {
            "teacher_telegram_user_id": "INTEGER",
            "target_kind": "TEXT",
            "student_id": "INTEGER",
            "group_id": "INTEGER",
            "target_name": "TEXT",
            "homework_text": "TEXT",
            "due_date": "TEXT",
            "created_at": "TEXT",
            "active": "INTEGER DEFAULT 1",
        })

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_homework_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """
        )
        _add_missing(conn, "teacher_homework_recipients", {
            "homework_id": "INTEGER",
            "teacher_telegram_user_id": "INTEGER",
            "student_id": "INTEGER",
            "person_id": "INTEGER",
            "person_name": "TEXT",
            "telegram_user_id": "INTEGER",
            "status": "TEXT DEFAULT 'assigned'",
            "completed_at": "TEXT",
        })

        # Non-unique indexes keep migration safe even if an older experimental
        # table already contains duplicate rows. Runtime code prevents new
        # duplicate attendance marks itself.
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_teacher_attendance_occurrence_v2
            ON teacher_attendance(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                student_id,person_id
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_teacher_attendance_teacher_date
            ON teacher_attendance(teacher_telegram_user_id,lesson_date,status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_teacher_due
            ON teacher_homework(teacher_telegram_user_id,active,due_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_recipients_hw
            ON teacher_homework_recipients(homework_id,status)
            """
        )
        conn.commit()
