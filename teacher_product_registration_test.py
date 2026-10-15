"""Registration smoke tests for the isolated PREPODMIN teacher profile flow."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.ext import ConversationHandler

import teacher_product_mvp as base
import teacher_product_onboarding as onboarding
import teacher_product_webapp as webapp


def make_update(uid, text=""):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        message=SimpleNamespace(text=text, reply_text=AsyncMock()),
    )


def make_callback(uid, value="cnt:1_10"):
    return SimpleNamespace(
        callback_query=SimpleNamespace(
            from_user=SimpleNamespace(id=uid),
            data=value,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        ),
    )


class TeacherRegistrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.temp.name, "teacher.sqlite3")
        base.ensure_tables()
        onboarding.ensure_tables()

    def tearDown(self):
        self.temp.cleanup()

    async def test_new_user_must_enter_name_then_subject(self):
        update = make_update(201)
        self.assertEqual(await base.start(update, None), base.NAME)
        self.assertIsNone(base.teacher(201)["name"])
        update.message.text = "  Анна   Сергеевна "
        self.assertEqual(await base.onboarding_name(update, None), base.SUBJECT)
        self.assertEqual(base.teacher(201)["name"], "Анна Сергеевна")
        self.assertIsNone(base.teacher(201)["subject"])
        update.message.text = "Кнопки меню 🚀"
        self.assertEqual(await base.onboarding_subject(update, None), base.SUBJECT)
        self.assertIsNone(base.teacher(201)["subject"])
        update.message.text = "  Математика  "
        self.assertEqual(await base.onboarding_subject(update, None), base.FORMAT)
        row = base.teacher(201)
        self.assertEqual(row["subject"], "Математика")
        self.assertIsNone(row["onboarding_completed_at"])

    async def test_cannot_finish_registration_with_blank_name_or_subject(self):
        base.upsert_teacher(202, work_format="groups")
        q = make_callback(202)
        self.assertEqual(await onboarding.onboarding_count(q, None), -1)
        self.assertIsNone(base.teacher(202)["onboarding_completed_at"])
        base.upsert_teacher(202, name="Мария", subject="👤 Мой кабинет")
        self.assertEqual(await onboarding.onboarding_count(q, None), -1)
        self.assertIsNone(base.teacher(202)["onboarding_completed_at"])

    async def test_new_teacher_can_complete_after_required_fields(self):
        base.upsert_teacher(203, name="Мария Александровна", subject="Химия", work_format="mixed")
        q = make_callback(203)
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        self.assertEqual(await onboarding.onboarding_count(q, context), -1)
        row = base.teacher(203)
        self.assertTrue(row["onboarding_completed_at"])
        self.assertEqual(row["subject"], "Химия")
        self.assertTrue(onboarding.setup_status(203)["profile"])

    async def test_existing_incomplete_profile_can_be_repaired_without_reset(self):
        base.upsert_teacher(
            204, name="👤 Мой кабинет", subject="Химия",
            work_format="groups", onboarding_completed_at="2026-10-10T10:00:00",
        )
        original_created_at = base.teacher(204)["created_at"]
        update = make_update(204)
        self.assertEqual(await base.start(update, None), base.NAME)
        self.assertFalse(onboarding.setup_status(204)["profile"])
        update.message.text = "Екатерина Николаевна"
        self.assertEqual(await base.onboarding_name(update, None), ConversationHandler.END)
        row = base.teacher(204)
        self.assertEqual(row["name"], "Екатерина Николаевна")
        self.assertEqual(row["subject"], "Химия")
        self.assertEqual(row["created_at"], original_created_at)
        self.assertEqual(row["work_format"], "groups")
        self.assertTrue(onboarding.setup_status(204)["profile"])

    async def test_existing_profile_with_missing_subject_can_be_repaired(self):
        base.upsert_teacher(
            205, name="Анна Сергеевна", subject=None,
            onboarding_completed_at="2026-10-10T10:00:00",
        )
        u = make_update(205)
        self.assertEqual(await base.start(u, None), base.SUBJECT)
        u.message.text = "Биология"
        self.assertEqual(await base.onboarding_subject(u, None), ConversationHandler.END)
        self.assertEqual(base.teacher(205)["subject"], "Биология")

    async def test_existing_valid_profile_keeps_onboarding_complete(self):
        base.upsert_teacher(206, name="Елена", subject="Физика",
                            onboarding_completed_at="2026-10-10T10:00:00")
        u = make_update(206)
        self.assertEqual(await base.start(u, None), ConversationHandler.END)
        self.assertIn("Елена", u.message.reply_text.await_args.args[0])
        self.assertIn("Физика", u.message.reply_text.await_args.args[0])

    def test_dashboard_payload_and_profile_are_specific_to_teacher(self):
        base.upsert_teacher(207, name="Ирина", subject="Русский язык",
                            onboarding_completed_at="2026-10-10T10:00:00")
        base.upsert_teacher(208, name="Наталья", subject="Физика",
                            onboarding_completed_at="2026-10-10T10:00:00")
        self.assertEqual(base._profile_values(base.teacher(207)), ("Ирина", "Русский язык"))
        self.assertEqual(base._profile_values(base.teacher(208)), ("Наталья", "Физика"))
        self.assertTrue(webapp._bot_cabinet_text(207).startswith("👩‍🏫 <b>Ирина</b>"))
        self.assertTrue(webapp._bot_cabinet_text(208).startswith("👩‍🏫 <b>Наталья</b>"))


if __name__ == "__main__":
    unittest.main()
