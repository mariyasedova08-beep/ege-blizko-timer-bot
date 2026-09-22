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


if __name__ == "__main__":
    unittest.main()
