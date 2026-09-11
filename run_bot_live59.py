import json
import sqlite3
from urllib.parse import urlparse

import run_bot_live58

live58 = run_bot_live58
live56 = live58.live56
live55 = live58.live55
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

# CoreApp official webhook event "Ученик закончил урок в курсе" provides
# user_id/user_email/user_name/course_id plus lesson_id/lesson_name and optional
# correct_count/total_count. Accept intuitive endpoint aliases and normalize all of
# them into the existing submission pipeline.
_LESSON_COMPLETION_ALIASES = {
    "/coreapp/lesson-completed",
    "/coreapp/lesson-complete",
    "/coreapp/lesson-finished",
}

_original_do_post = bot.CoreAppWebhookHandler.do_POST
_original_save_submission = bot.save_coreapp_submission


def save_coreapp_submission_idempotent(payload):
    """Save one CoreApp lesson completion without duplicate rows on retries."""
    user_id = str(payload.get("user_id", "") or "").strip()
    email = bot.normalize_email(payload.get("user_email"))
    lesson_id = str(payload.get("lesson_id", "") or "").strip()
    lesson_name = str(payload.get("lesson_name", "") or "").strip()

    # If the event is incomplete, preserve old behavior so we can inspect it.
    if not (user_id or email) or not (lesson_id or lesson_name):
        return _original_save_submission(payload)

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        duplicate = conn.execute(
            """
            SELECT 1
            FROM homework_submissions
            WHERE (
                    (? != '' AND user_id = ?)
                    OR (? != '' AND lower(user_email) = lower(?))
                  )
              AND (
                    (? != '' AND lesson_id = ?)
                    OR (? != '' AND lesson_name = ?)
                  )
            LIMIT 1
            """,
            (
                user_id, user_id,
                email, email,
                lesson_id, lesson_id,
                lesson_name, lesson_name,
            ),
        ).fetchone()
    if duplicate:
        # Still refresh student data in case name/course/id changed.
        bot.upsert_student(payload, active=1)
        return

    _original_save_submission(payload)


bot.save_coreapp_submission = save_coreapp_submission_idempotent


def do_post_with_lesson_completion_aliases(self):
    parsed = urlparse(self.path)
    if parsed.path in _LESSON_COMPLETION_ALIASES:
        # Reuse the already-tested authenticated /coreapp/homework-submitted
        # handler. It stores exactly the fields emitted by CoreApp's lesson
        # completion webhook.
        query = ("?" + parsed.query) if parsed.query else ""
        self.path = "/coreapp/homework-submitted" + query
        return _original_do_post(self)
    return _original_do_post(self)


bot.CoreAppWebhookHandler.do_POST = do_post_with_lesson_completion_aliases


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
    live24.main()
