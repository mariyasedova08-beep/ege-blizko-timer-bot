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



class GroupPaymentsFastNavigationTest(unittest.IsolatedAsyncioTestCase):
    """No production writes: all group navigation checks run on temporary SQLite."""

    def setUp(self):
        from datetime import date
        from unittest.mock import AsyncMock
        import teacher_product_group_payments as payments
        self.payments = payments
        self.AsyncMock = AsyncMock
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "fast_navigation.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        payments.ensure_tables()
        base.upsert_teacher(101, name="Мария", subject="Химия",
                            onboarding_completed_at="2026-10-20")
        base.upsert_teacher(202, name="Елена", subject="Биология",
                            onboarding_completed_at="2026-10-20")
        self.gid = groups.add_group(101, "ОГЭ 2027")
        self.ids = [
            int(student_reminders.add_member(101, self.gid, name)["id"])
            for name in ("Алина", "Аня", "Арина")
        ]
        self.other_gid = groups.add_group(202, "Чужая группа")
        self.other_pid = int(student_reminders.add_member(202, self.other_gid, "Оля")["id"])
        payments._save_group_plan(
            101,
            {"pid": self.ids[0], "gid": self.gid, "name": "Алина",
             "type": "monthly", "amount": 9900},
            due=date(2026, 11, 2),
        )

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def callback_values(markup):
        return [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row if button.callback_data
        ]

    def test_group_hub_opens_each_payment_in_one_tap(self):
        p = self.payments
        text, markup = p._group_payment_hub(101, self.gid)
        self.assertIn("ОГЭ 2027", text)
        self.assertIn("Настроено: 1/3", text)
        for pid in self.ids:
            self.assertIn(f"gpay:member:{pid}", self.callback_values(markup))
            self.assertIn(f"gpay:setup:{pid}", self.callback_values(markup))
        self.assertIn(f"gmem:members:{self.gid}", self.callback_values(markup))
        self.assertIn(f"gmem:group:{self.gid}", self.callback_values(markup))
        self.assertNotIn(f"gpay:setup:{self.other_pid}", self.callback_values(markup))
        self.assertEqual(self.payments._plan(101, self.ids[0])["amount_rub"], 9900)

    def test_next_student_prioritizes_unconfigured_and_wraps(self):
        p = self.payments
        self.assertEqual(p._next_group_member(101, self.gid, self.ids[0], True)["id"], self.ids[1])
        self.assertEqual(p._next_group_member(101, self.gid, self.ids[2], True)["id"], self.ids[1])
        self.assertEqual(p._next_group_member(101, self.gid, self.ids[1], True)["id"], self.ids[2])
        self.assertIsNone(p._next_group_member(202, self.gid, self.ids[0], True))
        self.assertIsNone(p._group_payment_hub(202, self.gid)[0])
        markup = p._payment_next_markup(101, self.gid, self.ids[0])
        self.assertIn(f"gpay:setup:{self.ids[1]}", self.callback_values(markup))

    async def test_after_save_next_student_and_group_menu_are_one_tap(self):
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler
        p = self.payments
        response = self.AsyncMock()
        ctx = SimpleNamespace(user_data={
            "gpay": {"pid": self.ids[1], "gid": self.gid, "name": "Аня",
                     "type": "monthly", "amount": 9900},
        })
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=101),
            message=SimpleNamespace(text="02.11.2026", reply_text=response),
        )
        state = await p.setup_final(update, ctx)
        self.assertEqual(state, ConversationHandler.END)
        self.assertNotIn("gpay", ctx.user_data)
        self.assertEqual(p._plan(101, self.ids[1])["amount_rub"], 9900)
        self.assertEqual(p._plan(101, self.ids[0])["amount_rub"], 9900)
        markup = response.await_args.kwargs["reply_markup"]
        self.assertIn(f"gpay:setup:{self.ids[2]}", self.callback_values(markup))
        self.assertIn(f"gpay:group:{self.gid}", self.callback_values(markup))
        self.assertIn("Аня", response.await_args.args[0])
        self.assertIn("Арина", str(markup.inline_keyboard))

    async def test_hub_callback_renders_summary_without_mutating_payment(self):
        from types import SimpleNamespace
        from telegram.ext import ApplicationHandlerStop
        q = SimpleNamespace(
            from_user=SimpleNamespace(id=101),
            data=f"gpay:group:{self.gid}",
            answer=self.AsyncMock(),
            edit_message_text=self.AsyncMock(),
        )
        with self.assertRaises(ApplicationHandlerStop):
            await self.payments.group_view(SimpleNamespace(callback_query=q), None)
        self.assertIn("Настроено: 1/3", q.edit_message_text.await_args.args[0])
        self.assertIn(f"gpay:setup:{self.ids[1]}",
                      self.callback_values(q.edit_message_text.await_args.kwargs["reply_markup"]))
        self.assertIsNone(self.payments._plan(101, self.ids[1]))

    def test_group_with_everyone_configured_still_has_next_navigation(self):
        from datetime import date
        for pid in self.ids[1:]:
            self.payments._save_group_plan(
                101, {"pid": pid, "gid": self.gid,
                      "type": "monthly", "amount": 8000},
                due=date(2026, 11, 5))
        next_person = self.payments._next_group_member(101, self.gid, self.ids[0], True)
        self.assertIsNone(next_person)
        _, markup = self.payments._member_card(101, self.ids[0])
        self.assertIn(f"gpay:member:{self.ids[1]}", self.callback_values(markup))
        self.assertIn("Настроено: 3/3", self.payments._group_payment_hub(101, self.gid)[0])



class FullyPaidCoursePaymentsTest(unittest.IsolatedAsyncioTestCase):
    """Full-course receipts must not be treated as overdue single lessons."""

    def setUp(self):
        from unittest.mock import AsyncMock
        from datetime import date
        import teacher_product_group_payments as payments
        self.payments = payments
        self.AsyncMock = AsyncMock
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "course.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        payments.ensure_tables()
        base.upsert_teacher(
            101, name="Мария", subject="Химия",
            onboarding_completed_at="2026-10-20",
        )
        base.upsert_teacher(
            202, name="Другой учитель", subject="Физика",
            onboarding_completed_at="2026-10-20",
        )
        self.gid = groups.add_group(101, "ОГЭ 2027")
        self.pid = int(student_reminders.add_member(101, self.gid, "Алина")["id"])
        self.received = date(2026, 10, 18)

    def tearDown(self):
        self.tmp.cleanup()

    def _data(self, amount=85100):
        return {
            "pid": self.pid, "gid": self.gid, "name": "Алина",
            "type": "course_paid", "amount": amount,
        }

    def test_existing_group_payment_schema_is_extended_additively(self):
        with base.db() as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(group_member_payment_plans)")}
            self.assertIn("course_paid", columns)
            self.assertIn("course_paid_date", columns)
            conn.execute(
                "INSERT INTO group_member_payment_plans("
                "teacher_telegram_user_id,person_id,group_id,payment_type,amount_rub,"
                "next_due_date,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (101,self.pid,self.gid,"once",9900,"2026-11-02",1,"now","now"),
            )
            conn.commit()
        self.payments.ensure_tables()
        with base.db() as conn:
            plan = conn.execute(
                "SELECT amount_rub,course_paid FROM group_member_payment_plans WHERE person_id=?",
                (self.pid,),
            ).fetchone()
            self.assertEqual(int(plan["amount_rub"]), 9900)
            self.assertEqual(int(plan["course_paid"]), 0)

    def test_migration_preserves_real_legacy_plan_and_receipts(self):
        """Upgrade an old payment table without changing existing payment amounts."""
        original_path = base.DB_PATH
        base.DB_PATH = os.path.join(self.tmp.name, "legacy.sqlite3")
        try:
            base.ensure_tables()
            groups.ensure_tables()
            student_reminders.ensure_tables()
            with base.db() as conn:
                conn.execute("""
                    CREATE TABLE group_member_payment_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        teacher_telegram_user_id INTEGER NOT NULL,
                        person_id INTEGER NOT NULL,
                        group_id INTEGER NOT NULL,
                        payment_type TEXT NOT NULL CHECK(payment_type IN ('once','monthly','package')),
                        amount_rub INTEGER NOT NULL,
                        next_due_date TEXT,
                        lessons_total INTEGER,
                        lessons_remaining INTEGER,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(teacher_telegram_user_id, person_id)
                    )
                """)
                conn.execute(
                    "INSERT INTO group_member_payment_plans"
                    "(teacher_telegram_user_id,person_id,group_id,payment_type,"
                    "amount_rub,next_due_date,active,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (101, 777, 888, "monthly", 9900, "2026-11-02", 1, "old", "old"),
                )
                conn.execute("""
                    CREATE TABLE group_member_payment_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        teacher_telegram_user_id INTEGER NOT NULL,
                        person_id INTEGER NOT NULL,
                        group_id INTEGER NOT NULL,
                        amount_rub INTEGER NOT NULL,
                        payment_type TEXT NOT NULL,
                        due_date TEXT,
                        paid_at TEXT NOT NULL
                    )
                """)
                conn.execute(
                    "INSERT INTO group_member_payment_history"
                    "(teacher_telegram_user_id,person_id,group_id,amount_rub,"
                    "payment_type,due_date,paid_at) VALUES(?,?,?,?,?,?,?)",
                    (101, 777, 888, 9900, "monthly", "2026-10-02", "2026-10-02T12:00:00"),
                )
                conn.commit()
            self.payments.ensure_tables()
            with base.db() as conn:
                old = conn.execute(
                    "SELECT * FROM group_member_payment_plans WHERE person_id=777"
                ).fetchone()
                self.assertEqual(old["amount_rub"], 9900)
                self.assertEqual(old["payment_type"], "monthly")
                self.assertEqual(old["next_due_date"], "2026-11-02")
                self.assertEqual(old["course_paid"], 0)
                self.assertIsNone(old["course_paid_date"])
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM group_member_payment_history").fetchone()[0],
                    1,
                )
        finally:
            base.DB_PATH = original_path


    def test_full_course_is_paid_not_due_and_history_logged_once(self):
        p = self.payments
        p._save_group_plan(101, self._data(), received=self.received)
        plan = p._plan(101, self.pid)
        self.assertTrue(plan["active"])
        self.assertEqual(plan["payment_type"], "once")  # existing SQLite CHECK retained
        self.assertEqual(plan["course_paid"], 1)
        self.assertEqual(plan["course_paid_date"], self.received.isoformat())
        self.assertIsNone(plan["next_due_date"])
        self.assertEqual(plan["amount_rub"], 85100)
        self.assertIn("курс оплачен полностью", p._status(101, plan)[0])
        self.assertEqual(p._status(101, plan)[1], "ok")
        self.assertIn("Настроено: 1/1", p._group_payment_hub(101, self.gid)[0])
        self.assertIn("весь курс", p._group_payment_payload(101, self.pid)["hint"])
        self.assertIsNone(p._plan(202, self.pid))
        text, markup = p._member_card(101, self.pid)
        self.assertIn("весь курс", text)
        callbacks = [b.callback_data for line in markup.inline_keyboard for b in line]
        self.assertNotIn(f"gpay:paid:{self.pid}", callbacks)
        p._save_group_plan(101, self._data(), received=self.received)
        with base.db() as conn:
            history = conn.execute(
                "SELECT amount_rub,payment_type,paid_at FROM group_member_payment_history "
                "WHERE teacher_telegram_user_id=? AND person_id=?",
                (101,self.pid),
            ).fetchall()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["payment_type"], "course_paid")
            self.assertEqual(history[0]["amount_rub"], 85100)
            self.assertTrue(history[0]["paid_at"].startswith("2026-10-18"))

    def test_existing_receipt_cannot_silently_change_or_duplicate(self):
        p = self.payments
        p._save_group_plan(101, self._data(), received=self.received)
        with self.assertRaises(ValueError):
            p._save_group_plan(101, self._data(85110), received=self.received)
        self.assertEqual(int(p._plan(101, self.pid)["amount_rub"]), 85100)

    def test_regular_lesson_monthly_and_package_plan_still_work(self):
        from datetime import date
        p = self.payments
        p._save_group_plan(
            101, {"pid":self.pid,"gid":self.gid,"type":"monthly","amount":9900},
            due=date(2026,11,2),
        )
        self.assertEqual(p._plan(101, self.pid)["course_paid"], 0)
        self.assertEqual(p._plan(101, self.pid)["payment_type"], "monthly")
        p._save_group_plan(
            101, {"pid":self.pid,"gid":self.gid,"type":"package","amount":9000},
            lessons=8,
        )
        self.assertEqual(p._plan(101, self.pid)["lessons_remaining"], 8)
        self.assertEqual(p._plan(101, self.pid)["course_paid"], 0)

    def test_received_date_parser_rejects_future_and_accepts_past(self):
        from datetime import date
        parser = self.payments._parse_received_date
        today = date(2026,10,20)
        self.assertIsNone(parser("21.10.2026", today))
        self.assertIsNone(parser("нескоро", today))
        self.assertEqual(parser("18.10.2026", today), date(2026,10,18))
        self.assertEqual(parser("18.10", today), date(2026,10,18))

    async def test_full_course_wizard_saves_confirmed_receipt(self):
        from types import SimpleNamespace
        from telegram.ext import ConversationHandler
        ctx=SimpleNamespace(user_data={"gpay": self._data()})
        message=SimpleNamespace(text="18.10.2026", reply_text=self.AsyncMock())
        update=SimpleNamespace(effective_user=SimpleNamespace(id=101),message=message)
        state=await self.payments.setup_final(update,ctx)
        self.assertEqual(state,ConversationHandler.END)
        self.assertNotIn("gpay",ctx.user_data)
        self.assertIn("оплачен полностью",message.reply_text.await_args.args[0])
        self.assertIn("85 100",message.reply_text.await_args.args[0])
        self.assertIsNone(self.payments._plan(101,self.pid)["next_due_date"])

    async def test_future_receipt_date_does_not_save(self):
        from types import SimpleNamespace
        ctx=SimpleNamespace(user_data={"gpay":self._data()})
        message=SimpleNamespace(text="21.10.2026", reply_text=self.AsyncMock())
        update=SimpleNamespace(effective_user=SimpleNamespace(id=101),message=message)
        state=await self.payments.setup_final(update,ctx)
        self.assertEqual(state,self.payments.GPAY_FINAL)
        self.assertIsNone(self.payments._plan(101,self.pid))


if __name__ == "__main__":
    unittest.main()
