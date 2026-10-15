"""Isolated tests for the approved PREPODMIN subject picker and safe migrations."""
import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.ext import ConversationHandler

import teacher_product_mvp as base
import teacher_product_subjects as catalog
import teacher_product_webapp as webapp


class SubjectCatalogTest(unittest.TestCase):
    def test_all_approved_subjects_themes_and_flask(self):
        self.assertEqual(len(catalog.SUBJECTS), 15)
        self.assertEqual(len(catalog.THEMES), 14)
        self.assertEqual(catalog.subject_by_id("chemistry")["name"], "Химия")
        self.assertEqual(catalog.subject_by_text("  ХИМ  ")["id"], "chemistry")
        self.assertEqual(catalog.subject_by_text("алгебра")["id"], "mathematics")
        self.assertIsNone(catalog.subject_by_text("Неизвестный предмет"))
        self.assertEqual(catalog.DEFAULT_THEME_ID, "pink-pulse")
        self.assertEqual(catalog.theme_by_id("pink-pulse")["colors"]["accent"], "#F00087")
        self.assertEqual(catalog.theme_by_id("rose-ash")["name"], "Пепел розы")
        self.assertIn("night", {t["id"] for t in catalog.THEMES})
        subjects = catalog.public_subjects()
        self.assertEqual(len(subjects), 15)
        icons = {x["id"]: x["icon_svg"] for x in subjects}
        self.assertIn('<svg ', icons["chemistry"])
        self.assertIn('stroke="currentColor"', icons["chemistry"])
        self.assertIn('M9 3h6', icons["chemistry"])  # Approved flask, not a hexagon.
        self.assertTrue(all("<script" not in svg and "onload=" not in svg for svg in icons.values()))


class SubjectMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "teacher.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_schema_adds_columns_without_erasing_teacher_data(self):
        with sqlite3.connect(base.DB_PATH) as conn:
            conn.executescript("""
                CREATE TABLE teachers (
                    telegram_user_id INTEGER PRIMARY KEY,
                    name TEXT, subject TEXT, work_format TEXT, student_count TEXT,
                    timezone TEXT DEFAULT 'Europe/Moscow',
                    onboarding_completed_at TEXT, created_at TEXT NOT NULL
                );
                INSERT INTO teachers(telegram_user_id,name,subject,work_format,onboarding_completed_at,created_at)
                VALUES(100,'Мария','Химия','groups','2026-10-10','2026-10-01');
                INSERT INTO teachers(telegram_user_id,name,subject,work_format,onboarding_completed_at,created_at)
                VALUES(101,'Елена','Химия, биология','mixed','2026-10-10','2026-10-01');
            """)
        base.ensure_tables()
        base.ensure_tables()  # Idempotent restart.
        known = base.teacher(100)
        self.assertEqual(known["name"], "Мария")
        self.assertEqual(known["subject"], "Химия")
        self.assertEqual(known["subject_id"], "chemistry")
        self.assertEqual(known["theme_id"], "pink-pulse")
        self.assertEqual(known["work_format"], "groups")
        self.assertEqual(known["onboarding_completed_at"], "2026-10-10")
        unknown = base.teacher(101)
        self.assertEqual(unknown["subject"], "Химия, биология")
        self.assertIsNone(unknown["subject_id"])
        self.assertEqual(unknown["work_format"], "mixed")

    def test_other_teacher_and_legacy_subject_are_not_overwritten(self):
        base.ensure_tables()
        base.upsert_teacher(200, name="Ольга", subject="Химия, биология",
                            theme_id="night", work_format="groups")
        base.upsert_teacher(201, name="Екатерина", subject="Физика",
                            subject_id="physics", work_format="individual")
        result = webapp._teacher_action(200, {
            "action": "profile_update", "name": "Ольга Николаевна",
            "subject": "Химия, биология", "subject_id": "",
            "teacher_id": 201,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(base.teacher(200)["subject"], "Химия, биология")
        self.assertEqual(base.teacher(200)["theme_id"], "night")
        self.assertEqual(base.teacher(201)["name"], "Екатерина")
        self.assertEqual(base.teacher(201)["subject_id"], "physics")
        # Old integrations updating subject text must not leave a wrong icon.
        base.upsert_teacher(201, subject="Химия, биология")
        self.assertIsNone(base.teacher(201)["subject_id"])
        base.upsert_teacher(201, subject="Биология")
        self.assertEqual(base.teacher(201)["subject_id"], "biology")


class SubjectRegistrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "teacher.sqlite3")
        base.ensure_tables()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def callback(uid, data):
        return SimpleNamespace(callback_query=SimpleNamespace(
            from_user=SimpleNamespace(id=uid), data=data,
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        ))

    async def test_telegram_subject_button_stores_canonical_id(self):
        base.upsert_teacher(300, name="Анна")
        u = self.callback(300, "tsub:chemistry")
        self.assertEqual(await base.onboarding_subject_choice(u, None), base.FORMAT)
        self.assertEqual(base.teacher(300)["subject"], "Химия")
        self.assertEqual(base.teacher(300)["subject_id"], "chemistry")
        self.assertIsNone(base.teacher(300)["onboarding_completed_at"])
        self.assertEqual(u.callback_query.edit_message_text.await_count, 1)

    async def test_existing_teacher_updates_subject_without_restarting_onboarding(self):
        base.upsert_teacher(301, name="Анна", subject="Химия",
                            subject_id="chemistry", work_format="groups",
                            onboarding_completed_at="2026-10-10")
        u = self.callback(301, "tsub:biology")
        self.assertEqual(await base.onboarding_subject_choice(u, None), ConversationHandler.END)
        self.assertEqual(base.teacher(301)["subject_id"], "biology")
        self.assertEqual(base.teacher(301)["work_format"], "groups")
        self.assertEqual(base.teacher(301)["onboarding_completed_at"], "2026-10-10")

    async def test_unknown_button_does_not_change_profile(self):
        base.upsert_teacher(302, name="Анна", subject="Химия", subject_id="chemistry")
        u = self.callback(302, "tsub:unknown")
        self.assertEqual(await base.onboarding_subject_choice(u, None), base.SUBJECT)
        self.assertEqual(base.teacher(302)["subject_id"], "chemistry")

    def test_webapp_profile_subjects_and_authenticated_update(self):
        base.upsert_teacher(303, name="Мария", subject="Химия",
                            subject_id="chemistry", theme_id="rose-ash",
                            onboarding_completed_at="2026-10-10")
        base.upsert_teacher(304, name="Елена", subject="История",
                            subject_id="history", onboarding_completed_at="2026-10-10")
        profile = webapp._profile_view(303)
        self.assertEqual(profile["subject_id"], "chemistry")
        self.assertEqual(profile["theme_id"], "rose-ash")
        self.assertEqual(len(profile["subjects"]), 15)
        self.assertEqual(webapp._teacher_action(303, {
            "action": "profile_update", "name": "Мария Александровна",
            "subject_id": "biology", "teacher_id": 304,
        })["subject_id"], "biology")
        self.assertEqual(base.teacher(303)["name"], "Мария Александровна")
        self.assertEqual(base.teacher(303)["subject"], "Биология")
        self.assertEqual(base.teacher(303)["theme_id"], "rose-ash")
        self.assertEqual(base.teacher(304)["subject"], "История")
        self.assertEqual(webapp._teacher_action(303, {
            "action": "profile_update", "name": "Мария",
            "subject_id": "../../etc/passwd",
        })["error"], "invalid_teacher_subject")
        self.assertEqual(base.teacher(303)["subject_id"], "biology")
        # Existing API clients may still submit a valid custom/multi-subject label.
        legacy_result = webapp._teacher_action(303, {
            "action": "profile_update", "name": "Мария",
            "subject": "Химия и биология",
        })
        self.assertTrue(legacy_result["ok"])
        self.assertEqual(base.teacher(303)["subject"], "Химия и биология")
        self.assertIsNone(base.teacher(303)["subject_id"])
        self.assertEqual(base.teacher(304)["subject"], "История")


if __name__ == "__main__":
    unittest.main()
