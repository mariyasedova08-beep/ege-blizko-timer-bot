"""One-time read-only diagnostic for Liza's homework after lesson 2."""
import sqlite3

import run_bot_live90 as live90
import homework_deadline_logic as hdl

bot = live90.bot


def _mask_email(value):
    text = str(value or "")
    if "@" not in text:
        return "-"
    left, right = text.split("@", 1)
    return (left[:2] + "***@" + right) if left else ("***@" + right)


def run():
    try:
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            students = conn.execute(
                """
                SELECT id, coalesce(display_name,''), coalesce(user_name,''),
                       coalesce(user_email,''), coalesce(coreapp_user_id,''), telegram_user_id
                FROM students
                WHERE active = 1
                  AND (
                    lower(coalesce(display_name,'')) LIKE '%лиз%'
                    OR lower(coalesce(user_name,'')) LIKE '%лиз%'
                    OR lower(coalesce(display_name,'')) LIKE '%овсянников%'
                    OR lower(coalesce(user_name,'')) LIKE '%овсянников%'
                  )
                ORDER BY id
                """
            ).fetchall()

            print(f"LIZA_DIAG students={len(students)}", flush=True)
            for row in students:
                sid, display, uname, email, core_id, tg_id = row
                print(
                    "LIZA_DIAG student "
                    f"id={sid} display={display!r} user_name={uname!r} "
                    f"email={_mask_email(email)!r} core_id={core_id!r} tg={'yes' if tg_id else 'no'}",
                    flush=True,
                )
                subs = conn.execute(
                    """
                    SELECT received_at, user_id, user_email, lesson_id, lesson_name
                    FROM homework_submissions
                    WHERE (user_id IS NOT NULL AND trim(cast(user_id as text)) = ?)
                       OR (user_email IS NOT NULL AND lower(trim(user_email)) = lower(trim(?)))
                    ORDER BY received_at
                    """,
                    (str(core_id or '').strip(), str(email or '').strip()),
                ).fetchall()
                print(f"LIZA_DIAG submissions={len(subs)}", flush=True)
                for s in subs:
                    received_at, user_id, user_email, lesson_id, lesson_name = s
                    print(
                        "LIZA_DIAG submission "
                        f"at={received_at!r} lesson_id={lesson_id!r} lesson_name={lesson_name!r} "
                        f"uid_match={str(user_id or '').strip()==str(core_id or '').strip()} "
                        f"email={_mask_email(user_email)!r}",
                        flush=True,
                    )

            dates = hdl._course_dates()
            if len(dates) >= 2:
                source_date = dates[1]
                due = hdl.due_lesson_for_source(source_date)
                print(
                    f"LIZA_DIAG lesson2 source_date={source_date.isoformat()} due={due}",
                    flush=True,
                )
                if due:
                    due_date, due_no = due
                    done_ids, done_emails, evidence = hdl.homework_done_sets(
                        source_date, 2, due_date, due_no
                    )
                    print(
                        "LIZA_DIAG lesson2_match "
                        f"evidence={evidence} done_ids={len(done_ids)} done_emails={len(done_emails)}",
                        flush=True,
                    )
                    for row in students:
                        _sid, display, _uname, email, core_id, _tg = row
                        is_done = hdl._is_done(core_id, email, done_ids, done_emails)
                        print(f"LIZA_DIAG lesson2_student_done display={display!r} done={is_done}", flush=True)
    except Exception as exc:
        print(f"LIZA_DIAG ERROR {type(exc).__name__}: {exc}", flush=True)


run()
