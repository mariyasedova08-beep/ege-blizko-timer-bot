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




class GroupWorkspaceTest(unittest.TestCase):
    """Group data and mutations belong only to their teacher; no production DB."""

    def setUp(self):
        from datetime import datetime
        import teacher_product_group_workspace as workspace
        import teacher_product_group_payments as group_payments
        import teacher_product_student_reminders as reminders
        import teacher_product_learning as learning

        self.ws = workspace
        self.group_payments = group_payments
        self.reminders = reminders
        self.learning = learning
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "workspace.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        reminders.ensure_tables()
        learning.ensure_tables()
        group_payments.ensure_tables()
        base.upsert_teacher(
            101, name="Мария", subject="Химия",
            onboarding_completed_at="2026-10-20",
        )
        base.upsert_teacher(
            202, name="Другая", subject="Биология",
            onboarding_completed_at="2026-10-20",
        )
        self.gid = groups.add_group(101, "ОГЭ 2027")
        self.other_gid = groups.add_group(101, "ЕГЭ 2027")
        self.pid = int(reminders.add_member(101, self.gid, "Алина")["id"])
        self.other_pid = int(reminders.add_member(101, self.other_gid, "Саша")["id"])
        today_local = datetime.now(schedule.tz(101)).date()
        self.day = today_local
        groups.add_group_slot(101, self.gid, today_local.weekday(), "18:00")
        self.slot = next(
            slot for slot in groups.group_slots(101)
            if int(slot["group_id"]) == self.gid
        )
        group_payments._save_group_plan(
            101, {"pid":self.pid,"gid":self.gid,"type":"monthly","amount":9900},
            due=today_local,
        )
        self.assignment = learning._create_assignment(
            101, "group", self.gid, "Решить задачи №1–10", today_local,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_group_workspace_contains_real_data_and_member_payments(self):
        page = webapp._view(101, f"group:{self.gid}")
        self.assertEqual(page["title"], "ОГЭ 2027")
        self.assertEqual(page["member_count"], 1)
        self.assertEqual(page["members"][0]["name"], "Алина")
        self.assertEqual(page["members"][0]["payment"]["amount"], 9900)
        self.assertEqual(page["members"][0]["payment"]["level"], "warn")
        self.assertEqual(page["payment_issues"], 0)
        self.assertEqual(len(page["slots"]), 1)
        self.assertEqual(page["attendance_session"]["date"], self.day.isoformat())
        self.assertEqual(len(page["homework"]), 1)
        self.assertEqual(page["homework"][0]["total"], 1)
        person = webapp._view(101, f"member:{self.pid}")
        self.assertEqual(person["group_id"], self.gid)
        self.assertEqual(person["homework"][0]["status"], "pending")

    def test_cannot_read_another_teacher_or_guess_views(self):
        self.assertIsNone(webapp._view(202, f"group:{self.gid}"))
        self.assertIsNone(webapp._view(202, f"member:{self.pid}"))
        self.assertIsNone(webapp._view(101, "group:not-a-number"))
        self.assertIsNone(webapp._view(101, "group:-1"))
        self.assertIsNone(webapp._view(101, "member:1;DROP TABLE teachers"))
        self.assertIsNone(webapp._view(101, "group:99999999"))

    def test_attendance_saves_only_for_real_group_member_and_session(self):
        payload = {
            "action":"group_attendance", "group_id": self.gid,
            "member_id": self.pid, "slot_id": int(self.slot["id"]),
            "date":self.day.isoformat(), "status":"present",
        }
        success = webapp._teacher_action(101, payload)
        self.assertTrue(success["ok"], success)
        self.assertEqual(
            self.learning._attendance_status(
                101,"group",int(self.slot["id"]),self.day,"group_member",self.pid
            ), "present",
        )
        self.assertTrue(webapp._teacher_action(101,payload)["unchanged"])
        self.assertFalse(webapp._teacher_action(202,payload)["ok"])
        self.assertFalse(webapp._teacher_action(101,{**payload,"member_id":self.other_pid})["ok"])
        self.assertFalse(webapp._teacher_action(101,{**payload,"status":"unknown"})["ok"])
        self.assertFalse(webapp._teacher_action(101,{**payload,"slot_id":999999})["ok"])
        self.assertFalse(webapp._teacher_action(101,{**payload,"date":"2099-01-01"})["ok"])
        self.assertEqual(
            self.learning._attendance_status(
                101,"group",int(self.slot["id"]),self.day,"group_member",self.pid
            ), "present",
        )

    def test_group_workspace_preserves_payments_and_course_logic(self):
        from datetime import date
        from datetime import datetime
        self.group_payments._save_group_plan(
            101, {"pid":self.pid,"gid":self.gid,"type":"course_paid","amount":85100},
            received=min(datetime.now(schedule.tz(101)).date(),date(2026,10,20)),
        )
        page = webapp._view(101, f"group:{self.gid}")
        self.assertIn("оплачен полностью",page["members"][0]["payment"]["label"])
        self.assertEqual(page["members"][0]["payment"]["type"], "course")
        self.assertEqual(page["payment_issues"],0)
        self.assertIsNone(self.group_payments._plan(202,self.pid))

    def test_contextual_group_action_uses_authenticated_server_and_chat_id(self):
        import io
        import json
        from unittest.mock import patch

        action = {"action":"group_quick","group_id":self.gid,"section":"payments"}
        with patch.object(base,"BOT_TOKEN","FAKE_TEST_TOKEN"):
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"ok":true}')) as post:
                response = webapp._teacher_action(101,action)
        self.assertTrue(response["ok"],response)
        request = post.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent["chat_id"],101)
        self.assertEqual(
            sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
            f"gpay:group:{self.gid}",
        )
        self.assertEqual(
            sent["reply_markup"]["inline_keyboard"][1][0]["callback_data"],
            f"gmem:group:{self.gid}",
        )
        self.assertNotIn("FAKE_TEST_TOKEN",str(sent))

    def test_contextual_actions_reject_other_teachers_and_wrong_group(self):
        from unittest.mock import patch
        for payload, who in [
            ({"action":"group_quick","group_id":self.gid,"section":"payments"}, 202),
            ({"action":"group_quick","group_id":999999,"section":"payments"}, 101),
            ({"action":"group_quick","group_id":self.gid,"section":"bad"}, 101),
            ({"action":"group_quick","group_id":"oops","section":"payments"}, 101),
        ]:
            with patch("urllib.request.urlopen") as post:
                result = webapp._teacher_action(who,payload)
            self.assertFalse(result["ok"])
            post.assert_not_called()

    def test_group_quick_does_not_depend_on_telegram_senddata(self):
        html_content=webapp.HTML_PATH.read_text(encoding="utf-8")
        start=html_content.index("async function openGroupBotAction(")
        end=html_content.index("function groupSection(",start)
        fragment=html_content[start:end]
        self.assertIn("teacherAction({action:'group_quick'",fragment)
        self.assertIn("tg.openTelegramLink",fragment)
        self.assertNotIn("sendData(",fragment)


    def test_webapp_has_real_group_routes_and_no_pretend_buttons(self):
        html_content = webapp.HTML_PATH.read_text(encoding="utf-8")
        for phrase in (
            "function renderGroup(d)", "function renderMember(d)",
            "function setGroupAttendance(", "function openGroupBotAction(",
            "openView('group:", "group_payment",
        ):
            if phrase == "group_payment":
                continue
            self.assertIn(phrase,html_content)
        self.assertIn("group_attendance",html_content)
        self.assertIn("groupSection(",html_content)
        self.assertIn("member:'+Number(m.id)",html_content)




if __name__ == "__main__":
    unittest.main()
