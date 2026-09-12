import hmac
import os
from urllib.parse import parse_qs, urlparse

import run_bot_live81

live81 = run_bot_live81
live80 = live81.live80
bot = live81.bot


_BaseDiagnosticHandler = bot.CoreAppWebhookHandler


class OneTimeQueryDiagnosticHandler(_BaseDiagnosticHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/internal/coreapp-audit":
            expected = os.getenv("COREAPP_DIAG_SECRET", "")
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            if expected and hmac.compare_digest(str(supplied), str(expected)):
                try:
                    return self._send_json(200, {"ok": True, "audit": live81._coreapp_audit_result()})
                except Exception as exc:
                    print("CoreApp one-time audit error:", type(exc).__name__, flush=True)
                    return self._send_json(500, {"ok": False, "error": "audit_failed"})
        return super().do_GET()


bot.CoreAppWebhookHandler = OneTimeQueryDiagnosticHandler


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
    print("One-time CoreApp diagnostic query access ready", flush=True)
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
