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



class QuickSetupRefreshFeedbackTest(unittest.IsolatedAsyncioTestCase):
    """The Refresh button must visibly acknowledge both unchanged and new data."""

    async def test_unchanged_progress_confirms_without_editing_or_db_changes(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from telegram.ext import ApplicationHandlerStop

        query = SimpleNamespace(
            message=SimpleNamespace(text="Готово: 1/4 шагов"),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            callback_query=query,
        )
        progress = {
            "profile": True, "people": False,
            "schedule": False, "payments": False,
        }
        with patch.object(onboarding, "_progress_text", return_value=query.message.text), \
                patch.object(onboarding, "_progress_markup", return_value="markup"), \
                patch.object(onboarding, "setup_status", return_value=progress):
            with self.assertRaises(ApplicationHandlerStop):
                await onboarding.show_setup(update, None)
        query.answer.assert_awaited_once_with(
            "✅ Проверено: 1/4 шага. Новых изменений нет.",
            show_alert=True,
        )
        query.edit_message_text.assert_not_awaited()

    async def test_changed_progress_updates_message_and_shows_confirmation(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from telegram.ext import ApplicationHandlerStop

        query = SimpleNamespace(
            message=SimpleNamespace(text="Готово: 1/4 шагов"),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            callback_query=query,
        )
        progress = {
            "profile": True, "people": True,
            "schedule": False, "payments": False,
        }
        with patch.object(onboarding, "_progress_text", return_value="Готово: 2/4 шагов"), \
                patch.object(onboarding, "_progress_markup", return_value="markup"), \
                patch.object(onboarding, "setup_status", return_value=progress):
            with self.assertRaises(ApplicationHandlerStop):
                await onboarding.show_setup(update, None)
        query.answer.assert_awaited_once_with(
            "✅ Прогресс обновлён: 2/4 шага.",
            show_alert=True,
        )
        query.edit_message_text.assert_awaited_once_with(
            "Готово: 2/4 шагов", reply_markup="markup",
        )



class GuidedGroupSetupTest(unittest.IsolatedAsyncioTestCase):
    """A new group should immediately offer the real members and schedule flows."""

    def setUp(self):
        from unittest.mock import AsyncMock
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "guided.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        student_reminders.ensure_tables()
        base.upsert_teacher(101, name="Маша", subject="Химия",
                            work_format="groups",
                            onboarding_completed_at="2026-10-20")
        self.reply = AsyncMock()

    def tearDown(self):
        self.tmp.cleanup()

    async def test_creating_group_offers_all_next_steps_and_preserves_owner(self):
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            message=SimpleNamespace(text="ОГЭ 2027", reply_text=self.reply),
        )
        self.assertEqual(await groups.add_group_name(update, None), ConversationHandler.END)
        row = groups.groups(101)[0]
        gid = int(row["id"])
        self.assertEqual(row["name"], "ОГЭ 2027")
        self.assertIsNone(groups.get_group(202, gid))
        markup = self.reply.await_args.kwargs["reply_markup"]
        callbacks = [button.callback_data for line in markup.inline_keyboard for button in line]
        for target in (f"gmem:add:{gid}", f"gs:add:{gid}",
                       f"gpay:group:{gid}", "setup:home"):
            self.assertIn(target, callbacks)

    async def test_group_schedule_starts_with_day_for_selected_group(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from telegram.ext import ConversationHandler

        gid = groups.add_group(101, "ОГЭ 2027")
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=101),
            data=f"gs:add:{gid}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})
        update = SimpleNamespace(callback_query=query)
        state = await groups.group_slot_add_begin(update, context)
        self.assertEqual(state, groups.ADD_GROUP_SLOT_DAY)
        self.assertEqual(context.user_data["gs_gid"], gid)
        self.assertIn("ОГЭ 2027", query.edit_message_text.await_args.args[0])
        self.assertIn("В какой день", query.edit_message_text.await_args.args[0])
        callbacks = [
            b.callback_data
            for line in query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
            for b in line
        ]
        self.assertIn("gs:day:0", callbacks)

        day_query = SimpleNamespace(
            from_user=SimpleNamespace(id=101), data="gs:day:0",
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        )
        self.assertEqual(
            await groups.group_slot_pick_day(
                SimpleNamespace(callback_query=day_query), context),
            groups.ADD_GROUP_SLOT_TIME,
        )
        message = SimpleNamespace(
            text="18:30", reply_text=AsyncMock(),
        )
        self.assertEqual(
            await groups.group_slot_pick_time(
                SimpleNamespace(message=message, effective_user=SimpleNamespace(id=101)),
                context,
            ),
            ConversationHandler.END,
        )
        own_slots = [slot for slot in groups.group_slots(101) if slot["group_id"] == gid]
        self.assertEqual(len(own_slots), 1)
        self.assertEqual(own_slots[0]["time_text"], "18:30")
        next_buttons = [
            b.callback_data for row in message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
            for b in row
        ]
        self.assertIn(f"gs:add:{gid}", next_buttons)
        self.assertIn(f"gmem:add:{gid}", next_buttons)
        self.assertIn(f"gpay:group:{gid}", next_buttons)

    async def test_direct_group_schedule_rejects_another_teacher_group(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from telegram.ext import ConversationHandler
        gid = groups.add_group(101, "Личная группа")
        q = SimpleNamespace(
            from_user=SimpleNamespace(id=202),
            data=f"gs:add:{gid}",
            answer=AsyncMock(), edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})
        self.assertEqual(
            await groups.group_slot_add_begin(
                SimpleNamespace(callback_query=q), context),
            ConversationHandler.END,
        )
        self.assertNotIn("gs_gid", context.user_data)

    async def test_member_added_offers_schedule_and_payments(self):
        from types import SimpleNamespace
        import teacher_product_group_members as members

        gid = groups.add_group(101, "ОГЭ 2027")
        message = SimpleNamespace(text="Алина", reply_text=self.reply)
        context = SimpleNamespace(user_data={"gmem_gid": gid})
        result = await members.add_name(
            SimpleNamespace(effective_user=SimpleNamespace(id=101), message=message),
            context,
        )
        from telegram.ext import ConversationHandler
        self.assertEqual(result, ConversationHandler.END)
        self.assertEqual(len(student_reminders._members(101, gid)), 1)
        markup = self.reply.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]
        self.assertIn(f"gmem:add:{gid}", callbacks)
        self.assertIn(f"gs:add:{gid}", callbacks)
        self.assertIn(f"gpay:group:{gid}", callbacks)


if __name__ == "__main__":
    unittest.main()
