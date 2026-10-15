import os
import tempfile
import unittest

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_payments as payments
import teacher_product_reports as reports
import teacher_product_schedule as schedule
import teacher_product_tasks as tasks
import teacher_product_webapp as webapp


class TeacherDashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "test.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        tasks.ensure_tables()
        payments.ensure_tables()
        reports.ensure_tables()
        base.upsert_teacher(
            501,
            name="Мария",
            subject="Химия",
            work_format="groups",
            onboarding_completed_at="2026-09-22T00:00:00",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_dashboard_contains_all_main_screen_sections(self):
        data = webapp._dashboard(501)
        self.assertIsNotNone(data)
        self.assertIn("events", data)
        self.assertIn("tasks", data)
        self.assertIn("debts", data)
        self.assertIn("attention", data)
        self.assertEqual(data["teacher"]["name"], "Мария")
        self.assertTrue(data["teacher"]["profile_complete"])

    def test_teacher_can_update_own_name_without_resetting_profile(self):
        base.upsert_teacher(
            502, name="Анна", subject="Математика",
            work_format="individual",
            onboarding_completed_at="2026-09-22T00:00:00",
        )
        data = webapp._teacher_action(501, {
            "action": "profile_update", "name": "Маша",
            "subject": "Химия и биология",
        })
        self.assertTrue(data["ok"])
        self.assertEqual(webapp._dashboard(501)["teacher"]["name"], "Маша")
        self.assertEqual(webapp._profile_view(501)["subject"], "Химия и биология")
        self.assertEqual(base.teacher(502)["name"], "Анна")
        self.assertIsNotNone(base.teacher(501)["onboarding_completed_at"])

    def test_menu_button_cannot_replace_teacher_name_or_subject(self):
        self.assertIsNone(base.normalize_teacher_name("👤 Мой кабинет"))
        self.assertIsNone(base.normalize_teacher_subject("💗 ПРЕПАДМИН"))
        self.assertEqual(
            webapp._teacher_action(501, {
                "action": "profile_update", "name": "👤 Мой кабинет",
                "subject": "Химия"
            })["error"],
            "invalid_teacher_name",
        )
        self.assertEqual(base.teacher(501)["name"], "Мария")
        self.assertEqual(
            webapp._teacher_action(501, {
                "action": "profile_update", "name": "Маша",
                "subject": "💗 ПРЕПАДМИН"
            })["error"],
            "invalid_teacher_subject",
        )
        self.assertEqual(base.teacher(501)["subject"], "Химия")

    def test_invalid_old_name_is_not_shown_in_greeting(self):
        base.upsert_teacher(501, name="👤 Мой кабинет")
        self.assertEqual(webapp._dashboard(501)["teacher"]["name"], "коллега")
        self.assertFalse(webapp._dashboard(501)["teacher"]["profile_complete"])
        self.assertEqual(webapp._profile_view(501)["name"], "")

    def test_telegram_cabinet_greets_saved_teacher_name(self):
        self.assertIn("👩‍🏫 <b>Мария</b> · ПРЕПАДМИН", webapp._bot_cabinet_text(501))
        self.assertNotIn("Привет, 👤 Мой кабинет", webapp._bot_cabinet_text(501))

    def test_telegram_cabinet_refreshes_edited_name(self):
        base.upsert_teacher(502, name="Анна Сергеевна", subject="Математика",
                            onboarding_completed_at="2026-09-22T00:00:00")
        self.assertIn("<b>Анна Сергеевна</b>", webapp._bot_cabinet_text(502))
        response = webapp._teacher_action(502, {
            "action": "profile_update", "name": "Анна",
            "subject": "Математика",
        })
        self.assertTrue(response["ok"])
        self.assertIn("<b>Анна</b>", webapp._bot_cabinet_text(502))
        self.assertIn("<b>Мария</b>", webapp._bot_cabinet_text(501))

    def test_invalid_name_not_used_in_telegram_cabinet(self):
        base.upsert_teacher(501, name="👤 Мой кабинет")
        text = webapp._bot_cabinet_text(501)
        self.assertTrue(text.startswith("👤 <b>Мой кабинет</b>"))
        self.assertNotIn("👩‍🏫", text)


if __name__ == "__main__":
    unittest.main()
