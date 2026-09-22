import os
import tempfile
import unittest

import teacher_product_groups as groups
import teacher_product_learning as learning
import teacher_product_mvp as base
import teacher_product_reset as reset
import teacher_product_schedule as schedule
import teacher_product_student_reminders as student_reminders
import teacher_product_tasks as tasks


class SafeResetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "test.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        student_reminders.ensure_tables()
        learning.ensure_tables()
        tasks.ensure_tables()
        base.upsert_teacher(100, name="Мария", onboarding_completed_at="2026-09-22")
        base.upsert_teacher(200, name="Другой преподаватель", onboarding_completed_at="2026-09-22")

    def tearDown(self):
        self.tmp.cleanup()

    def test_recipients_are_active_linked_and_unique(self):
        with base.db() as conn:
            for name, chat_id, active in (("Алина", 10, 1), ("Алина дубль", 10, 1), ("Оля", 11, 0), ("Мила", None, 1)):
                conn.execute(
                    """INSERT INTO student_reminder_people
                       (teacher_id,kind,group_id,name,invite_token,telegram_user_id,active,created_at)
                       VALUES(100,'group',1,?,?,?,?,?)""",
                    (name, name + "-token", chat_id, active, "2026-09-22"),
                )
            conn.commit()
        rows = reset.linked_students(100)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["telegram_user_id"], 10)

    def test_backup_then_delete_only_current_teacher(self):
        base.add_student(100, "Алина", "")
        base.add_student(200, "Чужой ученик", "")
        backup_path = reset.create_backup(100)
        self.assertTrue(os.path.exists(backup_path))

        reset.delete_teacher_data(100)

        self.assertIsNone(base.teacher(100))
        self.assertIsNotNone(base.teacher(200))
        self.assertEqual([r["name"] for r in base.list_students(200)], ["Чужой ученик"])

    def test_reset_keeps_legacy_app_builder_contract(self):
        self.assertTrue(callable(reset.build_app))


if __name__ == "__main__":
    unittest.main()
