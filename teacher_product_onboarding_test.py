import os
import tempfile
import unittest

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_payments as payments
import teacher_product_student_reminders as student_reminders
import teacher_product_onboarding as onboarding


class QuickSetupStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "test.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        payments.ensure_tables()
        student_reminders.ensure_tables()
        onboarding.ensure_tables()
        base.upsert_teacher(
            101,
            name="Маша",
            subject="Химия",
            work_format="mixed",
            onboarding_completed_at="2026-09-22T00:00:00",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_progress_comes_from_real_records(self):
        status = onboarding.setup_status(101)
        self.assertTrue(status["profile"])
        self.assertFalse(status["people"])
        self.assertFalse(status["schedule"])
        self.assertFalse(status["payments"])

        base.add_student(101, "Алина", "")
        student = base.list_students(101)[0]
        schedule.add_slot(101, student["id"], 0, "18:00")
        payments._save_plan(101, student["id"], "monthly", 15000, schedule.date(2026, 9, 28))

        status = onboarding.setup_status(101)
        self.assertTrue(status["people"])
        self.assertTrue(status["schedule"])
        self.assertTrue(status["payments"])


if __name__ == "__main__":
    unittest.main()
