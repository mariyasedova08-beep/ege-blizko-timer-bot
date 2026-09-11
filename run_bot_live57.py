import hashlib
import sqlite3

import run_bot_live56

live56 = run_bot_live56
live55 = live56.live55
live54 = live55.live54
live52 = live55.live52
live51 = live55.live51
live50 = live55.live50
live49 = live55.live49
live48 = live55.live48
live46 = live55.live46
live44 = live55.live44
live43 = live55.live43
live41 = live55.live41
live39 = live55.live39
live37 = live55.live37
live35 = live55.live35
live34 = live55.live34
live31 = live55.live31
live24 = live55.live24
live17 = live55.live17
bot = live55.bot
run_bot = live34.run_bot


def _name_hash(value):
    normalized = live34._norm_name(value)
    if not normalized:
        return "-"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def log_homework_audit():
    """Temporary privacy-preserving homework audit.

    Logs only short hashes of student names and non-personal lesson metadata.
    No e-mail, Telegram IDs or CoreApp user IDs are printed.
    """
    try:
        students = live34._student_rows()
        first_lesson_date = run_bot.COURSE_LESSON_DATES[0]
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            for row in students:
                if row[5] is None:
                    continue
                _sid, display_name, user_name, email, coreapp_user_id, _tg = row
                submissions = conn.execute(
                    """
                    SELECT received_at, lesson_id, lesson_name
                    FROM homework_submissions
                    WHERE (coalesce(user_id, '') != '' AND user_id = ?)
                       OR (coalesce(user_email, '') != '' AND lower(user_email) = lower(?))
                    ORDER BY id DESC
                    LIMIT 8
                    """,
                    (str(coreapp_user_id or ""), str(email or "")),
                ).fetchall()
                explicit_lesson1 = [
                    s for s in submissions
                    if live31._submission_explicitly_matches(
                        s[1], s[2], 2, 1, first_lesson_date
                    )
                ]
                recent_meta = [
                    (str(s[0]), str(s[1] or ""), str(s[2] or ""))
                    for s in submissions[:4]
                ]
                print(
                    "HW_AUDIT "
                    f"display={_name_hash(display_name)} user={_name_hash(user_name)} "
                    f"submissions={len(submissions)} lesson1_explicit={len(explicit_lesson1)} "
                    f"recent={recent_meta}"
                )
    except Exception as exc:
        print("HW_AUDIT error:", repr(exc))


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live56.log_probnik_cabinet_audit()
    log_homework_audit()
    live24.main()
