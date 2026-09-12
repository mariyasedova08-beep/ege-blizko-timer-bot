import json
import re
import sqlite3

import run_bot_live79

live79 = run_bot_live79
live78 = live79.live78
live77 = live79.live77
live76 = live79.live76
live75 = live79.live75
live74 = live79.live74
live73 = live79.live73
live72 = live79.live72
live71 = live79.live71
live70 = live79.live70
live69 = live79.live69
live68 = live79.live68
live67 = live79.live67
live66 = live79.live66
live65 = live79.live65
live64 = live79.live64
live63 = live79.live63
live61 = live79.live61
live60 = live79.live60
live59 = live79.live59
live56 = live79.live56
live50 = live79.live50
live51 = live79.live51
live48 = live79.live48
live46 = live79.live46
live44 = live79.live44
live43 = live79.live43
live41 = live79.live41
live39 = live79.live39
live37 = live79.live37
live35 = live79.live35
live34 = live79.live34
live31 = live79.live31
live24 = live79.live24
live17 = live79.live17
live28 = live79.live28
bot = live79.bot


def _safe_text(value):
    return str(value or "").strip()


def _name_norm(value):
    return _safe_text(value).casefold().replace("ё", "е")


def _lesson_number(lesson_id, lesson_name):
    lesson_id = _safe_text(lesson_id)
    m = re.search(r"monitoring:lesson:(\d+)", lesson_id, flags=re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"урок\s*№?\s*(\d+)", _name_norm(lesson_name), flags=re.I)
    if m:
        return int(m.group(1))
    return None


def _submission_source(raw_json):
    try:
        payload = json.loads(raw_json or "{}")
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return _safe_text(payload.get("source"))


def log_privacy_safe_coreapp_audit():
    """Production-only verification without printing student PII or secrets."""
    result = {
        "target_student_matches": 0,
        "target_has_lesson1": False,
        "target_has_lesson2": False,
        "target_lesson1_xlsx": 0,
        "target_lesson2_xlsx": 0,
        "target_lesson1_live": 0,
        "target_lesson2_live": 0,
        "webhook_completion_events": 0,
        "webhook_completion_ok": 0,
        "webhook_completion_saved": 0,
        "webhook_completion_duplicates": 0,
        "webhook_latest_status": None,
        "webhook_latest_error": None,
    }

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute(
            """
            SELECT coreapp_user_id, user_email, display_name, user_name
            FROM students
            """
        ).fetchall()

        target_students = []
        for user_id, email, display_name, user_name in students:
            haystack = " ".join((_name_norm(display_name), _name_norm(user_name)))
            if "овсянников" in haystack:
                target_students.append((_safe_text(user_id), _safe_text(email).lower()))

        result["target_student_matches"] = len(target_students)

        submissions = conn.execute(
            """
            SELECT user_id, lower(user_email), lesson_id, lesson_name, raw_json
            FROM homework_submissions
            """
        ).fetchall()

        for target_user_id, target_email in target_students:
            for user_id, email, lesson_id, lesson_name, raw_json in submissions:
                same_student = bool(
                    (target_user_id and _safe_text(user_id) == target_user_id)
                    or (target_email and _safe_text(email).lower() == target_email)
                )
                if not same_student:
                    continue
                lesson_no = _lesson_number(lesson_id, lesson_name)
                if lesson_no not in {1, 2}:
                    continue
                source = _submission_source(raw_json)
                if lesson_no == 1:
                    result["target_has_lesson1"] = True
                    if source == "coreapp_monitoring_xlsx":
                        result["target_lesson1_xlsx"] += 1
                    if source == "coreapp_webhook_live":
                        result["target_lesson1_live"] += 1
                elif lesson_no == 2:
                    result["target_has_lesson2"] = True
                    if source == "coreapp_monitoring_xlsx":
                        result["target_lesson2_xlsx"] += 1
                    if source == "coreapp_webhook_live":
                        result["target_lesson2_live"] += 1

        paths = (
            "/coreapp/lesson-completed",
            "/coreapp/lesson-complete",
            "/coreapp/lesson-finished",
        )
        placeholders = ",".join("?" for _ in paths)
        rows = conn.execute(
            f"""
            SELECT http_status, saved, duplicate, error_code
            FROM coreapp_webhook_events
            WHERE path IN ({placeholders})
            ORDER BY id
            """,
            paths,
        ).fetchall()
        result["webhook_completion_events"] = len(rows)
        result["webhook_completion_ok"] = sum(1 for status, *_ in rows if int(status or 0) == 200)
        result["webhook_completion_saved"] = sum(1 for _status, saved, _dup, _err in rows if int(saved or 0) == 1)
        result["webhook_completion_duplicates"] = sum(1 for _status, _saved, duplicate, _err in rows if int(duplicate or 0) == 1)
        if rows:
            status, _saved, _duplicate, error_code = rows[-1]
            result["webhook_latest_status"] = int(status or 0)
            result["webhook_latest_error"] = _safe_text(error_code) or None

    print("COREAPP_AUDIT_SAFE " + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    live71.ensure_molar_access_tables()
    live70.ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live24.live18.ensure_acid_reminder_table()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    live73.ensure_admin_task_view_state()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live66.seed_zlata_accounting_task()
    live67.ensure_individual_students_table()
    live71.complete_molar_mass_task()
    live74.ensure_notification_catchup_tables()
    live77.ensure_lesson_feedback_tables()
    live78.seed_priority_tasks()
    log_privacy_safe_coreapp_audit()
    live56.log_probnik_cabinet_audit()
    print("Privacy-safe CoreApp production audit ready", flush=True)
    print("Admin tasks separated: active / completed / content / technical", flush=True)
    print("Admin current-task table shows first seven tasks", flush=True)
    print("Completed admin tasks stay completed after restart", flush=True)
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
