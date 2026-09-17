"""SQLite-safe schema installer for PREPODMIN homework/attendance."""

import teacher_product_mvp as base
import teacher_product_student_reminders as student_reminders


def ensure_tables():
    student_reminders.ensure_tables()
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL CHECK(lesson_kind IN ('individual','group')),
                schedule_slot_id INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                student_id INTEGER,
                person_id INTEGER,
                person_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('present','absent','cancelled')),
                marked_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_teacher_attendance_occurrence
            ON teacher_attendance(
                teacher_telegram_user_id,lesson_kind,schedule_slot_id,lesson_date,
                COALESCE(student_id,-1),COALESCE(person_id,-1)
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_attendance_teacher_date
            ON teacher_attendance(teacher_telegram_user_id,lesson_date,status);

            CREATE TABLE IF NOT EXISTS teacher_homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                target_kind TEXT NOT NULL CHECK(target_kind IN ('individual','group')),
                student_id INTEGER,
                group_id INTEGER,
                target_name TEXT NOT NULL,
                homework_text TEXT NOT NULL,
                due_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_teacher_due
            ON teacher_homework(teacher_telegram_user_id,active,due_date);

            CREATE TABLE IF NOT EXISTS teacher_homework_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                homework_id INTEGER NOT NULL,
                teacher_telegram_user_id INTEGER NOT NULL,
                student_id INTEGER,
                person_id INTEGER,
                person_name TEXT NOT NULL,
                telegram_user_id INTEGER,
                status TEXT NOT NULL DEFAULT 'assigned' CHECK(status IN ('assigned','done')),
                completed_at TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_teacher_homework_recipient_unique
            ON teacher_homework_recipients(
                homework_id,COALESCE(student_id,-1),COALESCE(person_id,-1)
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_homework_recipients_hw
            ON teacher_homework_recipients(homework_id,status);
            """
        )
        conn.commit()
