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



class GroupMultidayRoutingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from unittest.mock import AsyncMock
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "routing.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        base.upsert_teacher(101, name="Маша", subject="Химия",
                            onboarding_completed_at="2026-10-20")
        self.group_id = groups.add_group(101, "ОГЭ 2027")

    def tearDown(self):
        self.tmp.cleanup()

    def test_direct_group_callback_registered_in_active_multiday_builder(self):
        from pathlib import Path
        import teacher_product_multiday as multiday
        source = Path(multiday.__file__).read_text(encoding="utf-8")
        self.assertIn('CallbackQueryHandler(group_pick_group, pattern=r"^gs:add:\\d+$")', source)
        self.assertIn('CallbackQueryHandler(groups.group_slot_add_begin, pattern=r"^gs:add$")', source)

    async def test_group_specific_button_opens_multiday_selection(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import teacher_product_multiday as multiday

        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=101),
            data=f"gs:add:{self.group_id}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})
        state = await multiday.group_pick_group(
            SimpleNamespace(callback_query=callback), context,
        )
        self.assertEqual(state, groups.ADD_GROUP_SLOT_DAY)
        self.assertEqual(context.user_data["gs_gid"], self.group_id)
        self.assertIn("ОГЭ 2027", callback.edit_message_text.await_args.args[0])
        self.assertIn("несколько дней", callback.edit_message_text.await_args.args[0])
        buttons = callback.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
        targets = [button.callback_data for line in buttons for button in line]
        self.assertIn("gs:day:done", targets)

    async def test_cannot_open_other_teachers_group(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from telegram.ext import ConversationHandler
        import teacher_product_multiday as multiday

        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=202),
            data=f"gs:add:{self.group_id}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        context = SimpleNamespace(user_data={})
        state = await multiday.group_pick_group(
            SimpleNamespace(callback_query=callback), context,
        )
        self.assertEqual(state, ConversationHandler.END)
        self.assertNotIn("gs_gid", context.user_data)



class GroupPaymentWizardRecoveryTest(unittest.IsolatedAsyncioTestCase):
    """Payment editing should recover from unfinished amount/date entry."""

    def setUp(self):
        from unittest.mock import AsyncMock
        import teacher_product_group_payments as group_payments
        self.group_payments = group_payments
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "payments_recovery.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        group_payments.ensure_tables()
        base.upsert_teacher(101, name="Мария", subject="Химия",
                            onboarding_completed_at="2026-10-20")
        self.gid = groups.add_group(101, "ОГЭ 2027")
        self.member = student_reminders.add_member(101, self.gid, "Алина")
        self.pid = int(self.member["id"])
        self.AsyncMock = AsyncMock

    def tearDown(self):
        self.tmp.cleanup()

    def callback(self, action, teacher=101):
        from types import SimpleNamespace
        q = SimpleNamespace(
            from_user=SimpleNamespace(id=teacher),
            data=action,
            answer=self.AsyncMock(),
            edit_message_text=self.AsyncMock(),
        )
        return SimpleNamespace(callback_query=q)

    def test_wizard_reentry_and_cancel_are_registered(self):
        conv = self.group_payments._payment_setup_conversation()
        self.assertTrue(conv.allow_reentry)
        self.assertTrue(conv.entry_points[0].pattern.fullmatch(f"gpay:setup:{self.pid}"))
        self.assertTrue(conv.fallbacks[0].pattern.fullmatch(f"gpay:cancel:{self.pid}"))
        self.assertIn(self.group_payments.GPAY_AMOUNT, conv.states)
        self.assertIn(self.group_payments.GPAY_FINAL, conv.states)

    async def test_repeated_configure_restarts_instead_of_reusing_stale_amount(self):
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler
        context = SimpleNamespace(user_data={
            "gpay": {"pid": self.pid, "type": "monthly", "amount": 5000},
        })
        update = self.callback(f"gpay:setup:{self.pid}")
        state = await self.group_payments.setup_begin(update, context)
        self.assertEqual(state, self.group_payments.GPAY_TYPE)
        self.assertEqual(context.user_data["gpay"]["pid"], self.pid)
        self.assertNotIn("amount", context.user_data["gpay"])
        self.assertNotIn("type", context.user_data["gpay"])
        self.assertIn("Как оплачивает", update.callback_query.edit_message_text.await_args.args[0])

        type_update = self.callback("gpay:type:package")
        state = await self.group_payments.setup_type(type_update, context)
        self.assertEqual(state, self.group_payments.GPAY_AMOUNT)
        self.assertIn("сумму", type_update.callback_query.edit_message_text.await_args.args[0])

        cancel = self.callback(f"gpay:cancel:{self.pid}")
        state = await self.group_payments.setup_cancel(cancel, context)
        self.assertEqual(state, ConversationHandler.END)
        self.assertNotIn("gpay", context.user_data)
        self.assertIn("Оплата не настроена", cancel.callback_query.edit_message_text.await_args.args[0])
        self.assertIsNone(self.group_payments._plan(101, self.pid))

    async def test_invalid_amount_has_cancel_and_does_not_save_payment(self):
        from types import SimpleNamespace
        context = SimpleNamespace(user_data={
            "gpay": {"pid": self.pid, "gid": self.gid,
                     "name": "Алина", "type": "package"},
        })
        message = SimpleNamespace(text="не знаю", reply_text=self.AsyncMock())
        state = await self.group_payments.setup_amount(
            SimpleNamespace(message=message), context)
        self.assertEqual(state, self.group_payments.GPAY_AMOUNT)
        buttons = message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, f"gpay:cancel:{self.pid}")
        self.assertIsNone(self.group_payments._plan(101, self.pid))

    async def test_other_teacher_cannot_edit_members_payment(self):
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler
        context = SimpleNamespace(user_data={})
        update = self.callback(f"gpay:setup:{self.pid}", teacher=202)
        state = await self.group_payments.setup_begin(update, context)
        self.assertEqual(state, ConversationHandler.END)
        self.assertNotIn("gpay", context.user_data)
        self.assertIsNone(self.group_payments._plan(101, self.pid))


if __name__ == "__main__":
    unittest.main()
