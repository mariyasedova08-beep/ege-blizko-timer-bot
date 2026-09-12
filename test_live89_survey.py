"""Offline integration checks: real imports/handler registration, fake Telegram I/O."""
import os
import json
import socket
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler


class SurveyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ege-survey-tests-")
        cls.env = patch.dict(os.environ, {
            "COREAPP_DB_PATH": cls.tmp.name + "/test.sqlite3",
            "BOT_TOKEN": "123:offline-test-token",
        })
        cls.env.start()
        cls.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network disabled"))
        cls.network.start()
        import run_bot_live89
        cls.survey = run_bot_live89

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.s = self.survey
        self.s.ensure_teacher_survey_tables()
        with sqlite3.connect(self.s.bot.COREAPP_DB_PATH) as conn:
            conn.execute("DELETE FROM teacher_survey_answers")
            conn.execute("DELETE FROM teacher_survey_sessions")
        self.message = SimpleNamespace(reply_text=AsyncMock(), text="", document=None)
        self.query = SimpleNamespace(data="", answer=AsyncMock(), edit_message_text=AsyncMock(), message=self.message)
        self.update = SimpleNamespace(
            effective_chat=SimpleNamespace(type="private"),
            effective_user=SimpleNamespace(id=101),
            message=self.message, effective_message=self.message, callback_query=self.query,
        )
        self.context = SimpleNamespace(args=[], user_data={}, bot=SimpleNamespace(get_me=AsyncMock(
            return_value=SimpleNamespace(username="ege_blizko_timer_bot"))))

    async def test_real_menu_and_cabinet_button(self):
        self.s.verify_teacher_survey_wiring()
        self.s.live79.live71.ensure_molar_access_tables()
        self.message.text = "👩‍🏫 Кабинет Маши"
        with patch.object(self.s.bot, "user_is_admin", return_value=True):
            await self.s.live7.student_text_router(self.update, self.context)
        markup = self.message.reply_text.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertEqual(callbacks.count("cab:surveyadmin"), 1)
        self.assertIn("cab:payments", callbacks)

    async def test_start_deep_link_and_complete_all_questions(self):
        self.context.args = ["teacher_survey"]
        await self.s.live7.start_router(self.update, self.context)
        self.assertIn("Опрос для преподавателей", self.message.reply_text.await_args.args[0])
        self.query.data = "cab:sv:start"
        await self.s.live23.cabinet_callback(self.update, self.context)
        for question in self.s.SURVEY_QUESTIONS:
            self.assertEqual(self.s._survey_session(101)[0], question["key"])
            if question.get("type") == "text":
                self.message.text = "Тестовая рутина преподавателя"
                await self.s.live7.student_text_router(self.update, self.context)
            else:
                await self.answer_options(question)
        self.assertIsNotNone(self.s._survey_session(101)[1])
        self.assertIn("Завершили: <b>1</b>", self.s.survey_admin_text())

    async def test_admin_results_and_share_link(self):
        with patch.object(self.s.bot, "user_is_admin", return_value=True):
            self.query.data = "cab:surveyadmin"
            await self.s.live23.cabinet_callback(self.update, self.context)
            self.assertIn("Опрос преподавателей", self.query.edit_message_text.await_args.args[0])
            self.query.data = "cab:surveyadmin:link"
            await self.s.live23.cabinet_callback(self.update, self.context)
            self.assertIn("https://t.me/ege_blizko_timer_bot?start=teacher_survey", self.message.reply_text.await_args.args[0])

    async def test_nonadmin_cannot_read_results(self):
        self.query.data = "cab:surveyadmin"
        with patch.object(self.s.bot, "user_is_admin", return_value=False):
            await self.s.live23.cabinet_callback(self.update, self.context)
        self.query.edit_message_text.assert_not_awaited()

    async def test_duplicate_click_does_not_advance(self):
        self.s._start_survey(101)
        self.query.data = "cab:sv:a:work_format:individual"
        await self.s.live23.cabinet_callback(self.update, self.context)
        await self.s.live23.cabinet_callback(self.update, self.context)
        self.assertEqual(self.s._survey_session(101)[0], "work_format")
        self.query.data = "cab:sv:a:work_format:done"
        await self.s.live23.cabinet_callback(self.update, self.context)
        self.assertEqual(self.s._survey_session(101)[0], "subject")

    async def test_group_link_delegates_to_previous_router(self):
        self.update.effective_chat.type = "group"
        self.context.args = ["teacher_survey"]
        with patch.object(self.s, "_previous_start_router", new_callable=AsyncMock) as previous:
            await self.s.live7.start_router(self.update, self.context)
            previous.assert_awaited_once()

    async def test_main_registers_survey_routers(self):
        self.s.bot.init_coreapp_db()
        app = MagicMock()
        builder = MagicMock()
        builder.token.return_value.build.return_value = app
        with patch.object(self.s.bot, "start_http_server"), patch.object(self.s.bot.Application, "builder", return_value=builder):
            self.s.live79.live24.main()
        handlers = [call.args[0] for call in app.add_handler.call_args_list]
        self.assertTrue(any(isinstance(h, CommandHandler) and "start" in h.commands and h.callback is self.s.start_router_with_teacher_survey for h in handlers))
        self.assertTrue(any(isinstance(h, CallbackQueryHandler) and h.callback is self.s.cabinet_callback_with_teacher_survey for h in handlers))
        self.assertTrue(any(isinstance(h, MessageHandler) and h.callback is self.s.text_router_with_teacher_survey for h in handlers))
        app.run_polling.assert_called_once()

    async def test_health_error_and_recovery_hook_preserved(self):
        builder = self.s.bot.Application.builder()
        self.assertIs(builder._post_init, self.s.live79.live70._post_init)

    def database_snapshot(self):
        with sqlite3.connect(self.s.bot.COREAPP_DB_PATH) as conn:
            return tuple(conn.iterdump())

    async def preview_click(self, data):
        self.query.data = data
        with patch.object(self.s.bot, "user_is_admin", return_value=True):
            await self.s.live23.cabinet_callback(self.update, self.context)

    async def public_click(self, data):
        self.query.data = data
        await self.s.live23.cabinet_callback(self.update, self.context)

    async def answer_options(self, question, preview=False):
        prefix = "cab:svtest:a" if preview else "cab:sv:a"
        click = self.preview_click if preview else self.public_click
        for code, _label in question["options"][:question.get("min_choices", 1)]:
            action = "set_" + code if question.get("min_choices") else code
            await click(f"{prefix}:{question['key']}:{action}")
        if question.get("min_choices"):
            await click(f"{prefix}:{question['key']}:done")

    async def test_preview_all_questions_preserve_real_answers(self):
        # Existing public answers for this user and another participant must survive.
        self.s._start_survey(101)
        self.s._save_survey_answer(101, "work_format", answer_code="mixed")
        self.s._start_survey(202)
        for question in self.s.SURVEY_QUESTIONS:
            if question.get("type") == "text":
                self.s._save_survey_answer(202, question["key"], answer_text="Обычный ответ")
            else:
                self.s._save_survey_answer(202, question["key"], answer_code=question["options"][0][0])
        before = self.database_snapshot()
        self.context.args = ["teacher_survey_test"]
        with patch.object(self.s.bot, "user_is_admin", return_value=True):
            await self.s.live7.start_router(self.update, self.context)
        self.assertIn("Тестовый проход для Маши", self.message.reply_text.await_args.args[0])
        await self.preview_click("cab:svtest:start")
        for index, question in enumerate(self.s.SURVEY_QUESTIONS):
            self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], index)
            if question.get("type") == "text":
                self.message.text = "Пробный ответ — не сохранять"
                with patch.object(self.s.bot, "user_is_admin", return_value=True):
                    await self.s.live7.student_text_router(self.update, self.context)
            else:
                await self.answer_options(question, preview=True)
        self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        self.assertIn("Тест завершён", self.query.edit_message_text.await_args.args[0])
        self.assertEqual(self.database_snapshot(), before)
        await self.preview_click("cab:svtest:start")
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 0)
        self.assertEqual(self.database_snapshot(), before)

    async def test_preview_admin_button_and_same_questions(self):
        self.assertIn("cab:svtest:welcome", [b.callback_data for row in self.s.survey_admin_markup().inline_keyboard for b in row])
        await self.preview_click("cab:svtest:welcome")
        self.assertIn("Тестовый проход", self.query.edit_message_text.await_args.args[0])
        await self.preview_click("cab:svtest:start")
        self.assertIn(self.s.SURVEY_QUESTIONS[0]["text"], self.query.edit_message_text.await_args.args[0])
        for question in self.s.SURVEY_QUESTIONS:
            normal = self.s._survey_question_markup(question)
            preview = self.s._survey_question_markup(question, "cab:svtest:a")
            if normal:
                self.assertEqual([b.text for row in normal.inline_keyboard for b in row], [b.text for row in preview.inline_keyboard for b in row])
                self.assertTrue(all(len(b.callback_data.encode()) <= 64 for row in preview.inline_keyboard for b in row))

    async def test_preview_rejects_nonadmin_and_group(self):
        before = self.database_snapshot()
        self.context.args = ["teacher_survey_test"]
        for admin, chat_type in [(False, "private"), (True, "group")]:
            self.update.effective_chat.type = chat_type
            with patch.object(self.s.bot, "user_is_admin", return_value=admin):
                await self.s.live7.start_router(self.update, self.context)
                self.query.data = "cab:svtest:start"
                await self.s.live23.cabinet_callback(self.update, self.context)
            self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        self.assertEqual(self.database_snapshot(), before)

    async def test_preview_stale_invalid_and_lost_session_buttons(self):
        await self.preview_click("cab:svtest:start")
        self.query.edit_message_text.reset_mock()
        await self.preview_click("cab:svtest:start")
        self.query.edit_message_text.assert_not_awaited()
        await self.preview_click("cab:svtest:a:work_format:forged")
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 0)
        await self.preview_click("cab:svtest:a:work_format:individual")
        self.query.edit_message_text.reset_mock()
        await self.preview_click("cab:svtest:a:work_format:individual")
        self.query.edit_message_text.assert_not_awaited()
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 0)
        await self.preview_click("cab:svtest:a:work_format:done")
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 1)
        self.context.user_data.clear()
        await self.preview_click("cab:svtest:a:work_format:individual")
        self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        self.assertIn("Тест не запущен", self.query.edit_message_text.await_args.args[0])

    async def test_preview_text_validation_and_exit_to_cabinet(self):
        before = self.database_snapshot()
        await self.preview_click("cab:svtest:start")
        await self.preview_click("cab:svtest:a:work_format:individual")
        await self.preview_click("cab:svtest:a:work_format:done")
        with patch.object(self.s.bot, "user_is_admin", return_value=True):
            for invalid in ["x", "x" * 1001]:
                self.message.text = invalid
                await self.s.live7.student_text_router(self.update, self.context)
                self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 1)
            self.message.text = "👩‍🏫 Кабинет Маши"
            with patch.object(self.s, "_previous_text_router", new_callable=AsyncMock) as previous:
                await self.s.live7.student_text_router(self.update, self.context)
                previous.assert_awaited_once()
        self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        self.assertEqual(self.database_snapshot(), before)

    async def test_preview_exit_and_public_start_clear_preview(self):
        await self.preview_click("cab:svtest:start")
        await self.preview_click("cab:svtest:exit")
        self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        await self.preview_click("cab:svtest:start")
        self.context.args = ["teacher_survey"]
        await self.s.live7.start_router(self.update, self.context)
        self.assertNotIn(self.s.PREVIEW_STATE_KEY, self.context.user_data)
        self.assertIn("Опрос для преподавателей", self.message.reply_text.await_args.args[0])

    async def test_multiple_formats_toggle_confirm_and_duplicate_delivery(self):
        await self.public_click("cab:sv:start")
        q = self.s.SURVEY_BY_KEY["work_format"]
        self.assertIn("Можно выбрать несколько ответов", q["text"])
        await self.public_click("cab:sv:a:work_format:done")
        self.assertEqual(self.s._survey_session(101)[0], "work_format")
        before = self.database_snapshot()
        for code in ["individual", "groups", "institution"]:
            await self.public_click("cab:sv:a:work_format:set_" + code)
        await self.public_click("cab:sv:a:work_format:unset_institution")
        self.query.edit_message_text.reset_mock()
        await self.public_click("cab:sv:a:work_format:set_groups")
        self.query.edit_message_text.assert_not_awaited()
        self.assertEqual(self.s._multi_selected(self.context, q), ["individual", "groups"])
        self.assertEqual(self.database_snapshot(), before)
        markup = self.s._survey_question_markup(q, selected=["individual", "groups"])
        self.assertEqual(sum(b.text.startswith("✅") for row in markup.inline_keyboard for b in row), 2)
        await self.public_click("cab:sv:a:work_format:done")
        with sqlite3.connect(self.s.bot.COREAPP_DB_PATH) as conn:
            stored = conn.execute("SELECT answer_code FROM teacher_survey_answers WHERE telegram_user_id=101 AND question_key='work_format'").fetchone()[0]
        self.assertEqual(json.loads(stored), ["individual", "groups"])
        completed = self.database_snapshot()
        await self.public_click("cab:sv:a:work_format:done")
        self.assertEqual(self.database_snapshot(), completed)

    async def test_priority_requires_exactly_three_and_replacement(self):
        self.s._start_survey(101)
        self.s._save_survey_answer(101, "biggest_routine", answer_text="Подготовка")
        q = self.s.SURVEY_BY_KEY["priority_function"]
        self.assertIn("Выберите 3 самые актуальные", q["text"])
        prefix = "cab:sv:a:priority_function:"
        for code in ["payments", "schedule"]:
            await self.public_click(prefix + "set_" + code)
        await self.public_click(prefix + "done")
        self.assertEqual(self.s._survey_session(101)[0], "priority_function")
        await self.public_click(prefix + "set_homework")
        await self.public_click(prefix + "set_attendance")
        self.assertEqual(self.s._multi_selected(self.context, q), ["payments", "schedule", "homework"])
        await self.public_click(prefix + "unset_schedule")
        await self.public_click(prefix + "done")
        self.assertEqual(self.s._survey_session(101)[0], "priority_function")
        await self.public_click(prefix + "set_attendance")
        await self.public_click(prefix + "done")
        self.assertEqual(self.s._survey_session(101)[0], "reminder_mode")
        with sqlite3.connect(self.s.bot.COREAPP_DB_PATH) as conn:
            stored = conn.execute("SELECT answer_code FROM teacher_survey_answers WHERE telegram_user_id=101 AND question_key='priority_function'").fetchone()[0]
        self.assertEqual(json.loads(stored), ["payments", "homework", "attendance"])

    async def test_preview_priority_limits_without_changing_public_choices(self):
        self.context.user_data[self.s.MULTI_STATE_KEY] = {"priority_function": ["reports"]}
        self.context.user_data[self.s.PREVIEW_STATE_KEY] = 6
        before = self.database_snapshot()
        prefix = "cab:svtest:a:priority_function:"
        for code in ["payments", "schedule"]:
            await self.preview_click(prefix + "set_" + code)
        await self.preview_click(prefix + "done")
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 6)
        await self.preview_click(prefix + "set_homework")
        await self.preview_click(prefix + "set_attendance")
        self.assertEqual(len(self.s._multi_selected(self.context, self.s.SURVEY_BY_KEY["priority_function"], True)), 3)
        await self.preview_click(prefix + "done")
        self.assertEqual(self.context.user_data[self.s.PREVIEW_STATE_KEY], 7)
        self.assertEqual(self.context.user_data[self.s.MULTI_STATE_KEY], {"priority_function": ["reports"]})
        self.assertEqual(self.database_snapshot(), before)

    async def test_results_aggregate_old_and_new_answers_without_rewriting(self):
        self.s._start_survey(101)
        self.s._save_survey_answer(101, "work_format", answer_code="mixed")
        self.s._save_survey_answer(101, "priority_function", answer_code="payments")
        self.s._save_survey_answer(101, "pilot", answer_code="yes")
        self.s._start_survey(202)
        self.s._save_survey_answer(202, "work_format", answer_code=json.dumps(["individual", "groups"]))
        self.s._save_survey_answer(202, "priority_function", answer_code=json.dumps(["payments", "homework", "attendance"]))
        self.s._save_survey_answer(202, "pilot", answer_code="yes")
        before = self.database_snapshot()
        text = self.s.survey_admin_text()
        for line in ["Индивидуально — 2", "В группах — 2", "Оплаты и долги — 2", "Домашние задания — 1", "Посещаемость — 1"]:
            self.assertIn(line, text)
        self.assertNotIn('["', text)
        self.assertEqual(self.database_snapshot(), before)

    async def test_legacy_combined_format_button(self):
        self.s._start_survey(101)
        await self.public_click("cab:sv:a:work_format:mixed")
        self.assertEqual(self.s._multi_selected(self.context, self.s.SURVEY_BY_KEY["work_format"]), ["individual", "groups"])
        self.assertEqual(self.s._survey_session(101)[0], "work_format")


if __name__ == "__main__":
    unittest.main()
