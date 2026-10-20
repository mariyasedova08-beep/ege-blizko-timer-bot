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


class CompactTelegramMenuTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from unittest.mock import AsyncMock
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "compact_menu.sqlite3")
        base.ensure_tables()
        base.upsert_teacher(
            101, name="Мария Александровна", subject="Химия",
            work_format="groups", onboarding_completed_at="2026-10-20",
        )
        self.AsyncMock = AsyncMock

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def actions(markup):
        return [
            btn.callback_data for row in markup.inline_keyboard
            for btn in row if btn.callback_data
        ]

    def test_main_menu_is_six_clear_directions(self):
        markup = webapp._bot_cabinet_markup()
        values = self.actions(markup)
        self.assertEqual(len(values), 6)
        self.assertEqual(values, [
            "pcab:students", "pcab:menu:lessons",
            "pcab:payments", "pcab:tasks",
            "pcab:menu:learning", "pcab:menu:more",
        ])
        self.assertEqual(len(markup.inline_keyboard), 3)
        text = webapp._bot_cabinet_text(101)
        self.assertIn("Мария Александровна", text)
        self.assertIn("Выбери раздел", text)
        self.assertNotIn("ЕГЭ БЛИЗКО", text)

    def test_all_previous_actions_stay_reachable(self):
        main = self.actions(webapp._bot_cabinet_markup())
        sections = ("lessons", "learning", "more")
        available = set(main)
        for section in sections:
            markup = webapp._bot_cabinet_markup(101, section)
            callbacks = self.actions(markup)
            self.assertEqual(callbacks[-1], "pcab:back")
            available.update(callbacks)
        preserved = {
            "pcab:students", "pcab:schedule", "pcab:homework",
            "pcab:attendance", "pcab:payments", "pcab:slots",
            "pcab:tasks", "pcab:reports", "pcab:materials",
            "pcab:reminders", "pcab:transfer", "pcab:cancel",
            "pcab:settings", "pcab:help", "pcab:attention",
        }
        self.assertTrue(preserved.issubset(available))

    async def test_submenu_and_back_edit_same_message(self):
        from types import SimpleNamespace
        query = SimpleNamespace(
            data="pcab:menu:lessons",
            from_user=SimpleNamespace(id=101),
            answer=self.AsyncMock(),
            edit_message_text=self.AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        await webapp.bot_cabinet_callback(update, None)
        self.assertIn("Занятия", query.edit_message_text.await_args.args[0])
        lesson_markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("pcab:schedule", self.actions(lesson_markup))
        self.assertIn("pcab:back", self.actions(lesson_markup))

        query.data = "pcab:back"
        await webapp.bot_cabinet_callback(update, None)
        home_markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertEqual(len(self.actions(home_markup)), 6)

    def test_app_launch_still_available_when_configured(self):
        from unittest.mock import patch
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
        launched = InlineKeyboardMarkup([[
            InlineKeyboardButton("💗 Открыть ПРЕПАДМИН",
                                 web_app=WebAppInfo(url="https://example.com/webapp?launch=test"))
        ]])
        with patch.object(webapp, "WEBAPP_URL", "https://example.com/webapp"):
            with patch.object(webapp, "_launch_markup", return_value=launched):
                markup = webapp._bot_cabinet_markup(101)
        self.assertEqual(len(markup.inline_keyboard), 4)
        self.assertIsNotNone(markup.inline_keyboard[-1][0].web_app)
        self.assertEqual(len(self.actions(markup)), 6)




if __name__ == "__main__":
    unittest.main()
