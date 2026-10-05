"""One-off attendance correction for 30.09.2026.

Maria confirmed that only Алиса and Злата were absent.
The patch is idempotent and refuses to write if either name is ambiguous.
"""

import re
import sqlite3
from datetime import datetime, date

import run_bot_live90 as live90

bot = live90.bot
live3 = live90.live79.live31.live30.live3

TARGET_DATE = date(2026, 9, 30)


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold().replace("ё", "е")


def _shown_name(row, columns):
    data = dict(zip(columns, row))
    for key in ("display_name", "user_name", "user_email"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return f"student:{data.get('id')}"


def _find_lesson_number():
    for lesson_number in range(1, int(bot.TOTAL_LESSONS) + 1):
        lesson_date = live3.lesson_date_by_number(lesson_number)
        if lesson_date == TARGET_DATE:
            return lesson_number
    raise RuntimeError("No course lesson found for 2026-09-30")


def seed():
    live3.ensure_attendance_tables()
    lesson_number = _find_lesson_number()
    now = datetime.now(bot.TIMEZONE).isoformat()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        columns = [
            str(row[1])
            for row in conn.execute("PRAGMA table_info(students)").fetchall()
        ]
        wanted = ["id", "user_name", "user_email"]
        if "display_name" in columns:
            wanted.insert(1, "display_name")

        rows = conn.execute(
            f"SELECT {','.join(wanted)} FROM students WHERE active=1 ORDER BY id"
        ).fetchall()

        matches = {"алиса": [], "злата": []}
        for row in rows:
            name = _shown_name(row, wanted)
            n = _norm(name)
            if re.search(r"(^|\s)алиса($|\s)", n):
                matches["алиса"].append((int(row[0]), name))
            if re.search(r"(^|\s)злата($|\s)", n):
                matches["злата"].append((int(row[0]), name))

        bad = {
            key: value for key, value in matches.items()
            if len(value) != 1
        }
        if bad:
            raise RuntimeError(
                "Attendance 30.09.2026 not changed: ambiguous/missing students "
                + repr(bad)
            )

        absent_ids = {
            matches["алиса"][0][0],
            matches["злата"][0][0],
        }

        live3.ensure_attendance_session(lesson_number)

        for row in rows:
            sid = int(row[0])
            status = "absent" if sid in absent_ids else "present"
            conn.execute(
                """
                INSERT INTO attendance_records
                    (lesson_number, student_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lesson_number, student_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (lesson_number, sid, status, now),
            )

        conn.execute(
            """
            UPDATE attendance_sessions
            SET finalized=1, updated_at=?
            WHERE lesson_number=?
            """,
            (now, lesson_number),
        )
        conn.commit()

        verify = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status='present' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END),
                COUNT(*)
            FROM attendance_records
            WHERE lesson_number=?
            """,
            (lesson_number,),
        ).fetchone()
        finalized = conn.execute(
            "SELECT finalized FROM attendance_sessions WHERE lesson_number=?",
            (lesson_number,),
        ).fetchone()

    print(
        "Attendance correction 2026-09-30 applied: "
        f"lesson={lesson_number} "
        f"absent={[matches['алиса'][0][1], matches['злата'][0][1]]} "
        f"present={int(verify[0] or 0)} absent_count={int(verify[1] or 0)} "
        f"total={int(verify[2] or 0)} finalized={int((finalized or [0])[0] or 0)}",
        flush=True,
    )
