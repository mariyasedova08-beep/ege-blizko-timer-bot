import hmac
import json
import os
import sqlite3
from urllib.parse import urlparse

import run_bot_live80

live80 = run_bot_live80
bot = live80.bot


def _coreapp_audit_result():
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
            haystack = " ".join((live80._name_norm(display_name), live80._name_norm(user_name)))
            if "овсянников" in haystack:
                target_students.append((live80._safe_text(user_id), live80._safe_text(email).lower()))

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
                    (target_user_id and live80._safe_text(user_id) == target_user_id)
                    or (target_email and live80._safe_text(email).lower() == target_email)
                )
                if not same_student:
                    continue
                lesson_no = live80._lesson_number(lesson_id, lesson_name)
                if lesson_no not in {1, 2}:
                    continue
                source = live80._submission_source(raw_json)
                if lesson_no == 1:
                    result["target_has_lesson1"] = True
                    if source == "coreapp_monitoring_xlsx":
                        result["target_lesson1_xlsx"] += 1
                    elif source == "coreapp_webhook_live":
                        result["target_lesson1_live"] += 1
                elif lesson_no == 2:
                    result["target_has_lesson2"] = True
                    if source == "coreapp_monitoring_xlsx":
                        result["target_lesson2_xlsx"] += 1
                    elif source == "coreapp_webhook_live":
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
            result["webhook_latest_error"] = live80._safe_text(error_code) or None

    return result


_BaseCoreAppWebhookHandler = bot.CoreAppWebhookHandler


class DiagnosticCoreAppWebhookHandler(_BaseCoreAppWebhookHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/internal/coreapp-audit":
            expected = os.getenv("COREAPP_DIAG_SECRET", "")
            supplied = str(self.headers.get("X-CoreApp-Diag-Secret", "") or "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return self._send_json(404, {"ok": False, "error": "not_found"})
            try:
                return self._send_json(200, {"ok": True, "audit": _coreapp_audit_result()})
            except Exception as exc:
                print("CoreApp private audit error:", type(exc).__name__, flush=True)
                return self._send_json(500, {"ok": False, "error": "audit_failed"})
        return super().do_GET()


bot.CoreAppWebhookHandler = DiagnosticCoreAppWebhookHandler


if __name__ == "__main__":
    live80.live71.ensure_molar_access_tables()
    live80.live70.ensure_health_tables()
    live80.live59.ensure_coreapp_webhook_audit_table()
    live80.live31.live25.ensure_lesson_day_before_table()
    live80.live31.live24.ensure_probnik_poll_tables()
    live80.live28.ensure_unanswered_reminder_tables()
    live80.live31.live30.live3.ensure_attendance_tables()
    live80.live31.live30.ensure_auto_attendance_table()
    live80.live31.ensure_personal_homework_reminder_table()
    live80.live17.ensure_acid_tables()
    live80.live24.live18.ensure_acid_reminder_table()
    live80.live34.ensure_attention_tables()
    live80.live35.ensure_admin_tasks_table()
    live80.live79.ensure_task_sections()
    live80.live73.ensure_admin_task_view_state()
    live80.live35.seed_monday_task()
    live80.live37.update_monday_task_text()
    live80.live39.seed_probnik_return_task()
    live80.live41.ensure_weekly_report_tables()
    live80.live41.seed_current_trainers()
    live80.live48.ensure_metals_tables()
    live80.live48.register_metals_trainer()
    live80.live60.ensure_oxides_tables()
    live80.live60.register_oxides_trainer()
    live80.live43.ensure_probnik_analysis_tables()
    live80.live44.enable_probnik_analysis_now()
    live80.live46.ensure_monthly_auto_report_table()
    live80.live50.seed_molar_mass_task()
    live80.live51.ensure_course_schedule_table()
    live80.live66.seed_zlata_accounting_task()
    live80.live67.ensure_individual_students_table()
    live80.live71.complete_molar_mass_task()
    live80.live74.ensure_notification_catchup_tables()
    live80.live77.ensure_lesson_feedback_tables()
    live80.live78.seed_priority_tasks()
    live80.live56.log_probnik_cabinet_audit()
    print("Secret-gated CoreApp production audit endpoint ready", flush=True)
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
    print(f"Oxides trainer ready: questions={len(live80.live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live80.live24.main()
