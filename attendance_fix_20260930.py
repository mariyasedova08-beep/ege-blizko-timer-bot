"""One-off correction: attendance for 30 Sep 2026.

Maria confirmed that only Alice and Zlata were absent. The migration is
idempotent and keeps the existing course lesson number for that date.
"""

import sqlite3
from datetime import date, datetime

import run_bot_live90 as live90

bot = live90.bot
live3 = live90.live79.live31.live30.live3
run_bot = live90.live79.live31.live30.run_bot

TARGET_DATE = date(2026, 9, 30)


def _norm(value):
    return str(value or "").strip().casefold().replace("ё", "е")


def seed():
    live3.ensure_attendance_tables()

    try:
        lesson_number = list(run_bot.COURSE_LESSON_DATES).index(TARGET_DATE) + 1
    except ValueError:
        print(
            "Attendance fix 2026-09-30 skipped: date not found in course schedule",
            flush=True,
        )
        return

    live3.ensure_attendance_session(lesson_number)
    now = datetime.now(bot.TIMEZONE).isoformat()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик')
            FROM students
            WHERE active=1
            ORDER BY id
            """
        ).fetchall()

        absent_ids = []
        absent_names = []
        for student_id, shown_name in students:
            name_norm = _norm(shown_name)
            first = name_norm.split()[0] if name_norm.split() else name_norm
            if first in {"алиса", "злата"}:
                absent_ids.append(int(student_id))
                absent_names.append(str(shown_name))

        if len(absent_ids) != 2:
            print(
                "Attendance fix 2026-09-30 not applied: "
                f"expected 2 absentees Alice/Zlata, matched={absent_names}",
                flush=True,
            )
            return

        for student_id, _shown_name in students:
            status = "absent" if int(student_id) in absent_ids else "present"
            conn.execute(
                """
                INSERT INTO attendance_records
                    (lesson_number, student_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lesson_number, student_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (lesson_number, int(student_id), status, now),
            )

        conn.execute(
            """
            UPDATE attendance_sessions
            SET lesson_date=?, finalized=1, updated_at=?
            WHERE lesson_number=?
            """,
            (TARGET_DATE.isoformat(), now, lesson_number),
        )
        conn.commit()

        present_count = conn.execute(
            """
            SELECT COUNT(*) FROM attendance_records
            WHERE lesson_number=? AND status='present'
            """,
            (lesson_number,),
        ).fetchone()[0]
        absent_rows = conn.execute(
            """
            SELECT s.id,
                   coalesce(nullif(s.display_name,''),nullif(s.user_name,''),s.user_email,'Ученик')
            FROM attendance_records ar
            JOIN students s ON s.id=ar.student_id
            WHERE ar.lesson_number=? AND ar.status='absent'
            ORDER BY s.id
            """,
            (lesson_number,),
        ).fetchall()

    print(
        "Attendance fix 2026-09-30 applied: "
        f"lesson={lesson_number} present={int(present_count or 0)} "
        f"absent={len(absent_rows)} names={[row[1] for row in absent_rows]}",
        flush=True,
    )
