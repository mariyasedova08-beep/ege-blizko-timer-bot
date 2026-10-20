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

    def test_main_navigation_has_five_clear_destinations(self):
        html = webapp.HTML_PATH.read_text(encoding="utf-8")
        menu = html.split('<div class="bottom"><div class="nav">', 1)[1].split('</div></div>', 1)[0]
        self.assertEqual(menu.count('<button id="nav-'),5)
        for nav, label, view in (
            ('home','Главная','home'),('students','Ученики','students'),
            ('schedule','Занятия','schedule'),('tasks','Задачи','tasks'),
            ('more','Ещё','more'),
        ):
            self.assertIn(f'id="nav-{nav}"',menu)
            self.assertIn(f"openView('{view}')",menu)
            self.assertIn(label,menu)
        self.assertIn("grid-template-columns:repeat(5,minmax(0,1fr))",html)

    def test_large_tiles_removed_from_home_and_rare_functions_retained_in_more(self):
        html=webapp.HTML_PATH.read_text(encoding="utf-8")
        home=html.split("function renderHome(d){",1)[1].split("function renderStudents(d){",1)[0]
        self.assertNotIn("Все разделы",home)
        self.assertNotIn('<div class="actions">',home)
        self.assertIn("Всё остальное — во вкладке «Ещё»",home)
        self.assertIn("function renderMore()",html)
        self.assertIn('<details class="more-category">',html)
        for action in (
            "openView('homework')",
            "openView('attendance')",
            "openView('payments')",
            "openView('reports')",
            "openView('attention')",
            "openHomeLessonAction('transfer')",
            "openHomeLessonAction('cancel')",
            "openView('slots')",
            "openView('profile')",
            "openView('settings')",
        ):
            self.assertIn(action,html)
        self.assertIn('function openPrepadminBot()',html)
        self.assertIn("Материалы, напоминания, настройки рассылок и инструкция",html)

    def test_more_view_renders_client_side_without_unauthorized_api_routes(self):
        html=webapp.HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("if(view==='more'){renderMore();",html)
        self.assertIn("if(view==='more')return renderMore()",html)
        self.assertIn("'students':view==='lesson-picker'?'schedule'",html)
        self.assertIn("async function openHomeLessonAction(action)",html)
        self.assertIn("async function openGroupLessonFromHome(gid,action)",html)
        self.assertIn("await api('students')",html)
        self.assertIn("activeGroupTab='lessons'",html)
        self.assertIn("await openView('group:'+Number(gid))",html)
        self.assertIn('Перенести в группе',html)
        self.assertIn('Отменить в группе',html)
        self.assertNotIn("['transfer','Перенести занятие','bot','transfer']",html)
        self.assertNotIn("['cancel','Отменить занятие','bot','cancel']",html)

    def test_look_and_feel_retains_all_themable_css(self):
        html=webapp.HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("--paper",html)
        self.assertIn("var vars={'--milk':c.background",html)
        self.assertIn("background:var(--soft)",html)
        self.assertIn("function renderSettings(d)",html)
        self.assertIn("14 цветовых тем",html)

    def test_group_picker_api_only_displays_owned_groups(self):
        own=groups.add_group(501,"ОГЭ 2027")
        base.upsert_teacher(502,name="Анна",subject="Математика",
            onboarding_completed_at="2026-10-20")
        groups.add_group(502,"Чужая группа")
        group_rows=webapp._view(501,"students")["groups"]
        self.assertEqual(
            [{"id":int(x["id"]),"name":x["name"]} for x in group_rows],
            [{"id":own,"name":"ОГЭ 2027"}],
        )

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



    def test_member_navigation_and_attendance_history_in_existing_group(self):
        from datetime import datetime
        next_id = int(self.reminders.add_member(101, self.gid, "Аня")["id"])
        p = webapp._view(101, f"member:{self.pid}")
        self.assertEqual(p["group_size"], 2)
        self.assertEqual(p["member_ids"], [self.pid, next_id])
        self.assertEqual(p["member_index"], 0)
        self.assertIsNone(p["attendance"]["items"][0] if p["attendance"]["items"] else None)
        session_id = int(self.slot["id"])
        result = webapp._teacher_action(101, {
            "action":"group_attendance","group_id":self.gid,"member_id":self.pid,
            "slot_id":session_id,"date":self.day.isoformat(),"status":"present",
        })
        self.assertTrue(result["ok"])
        history = webapp._view(101, f"member:{self.pid}")["attendance"]
        self.assertEqual(history["present"], 1)
        self.assertEqual(history["absent"], 0)
        self.assertEqual(history["items"][0]["date"], self.day.isoformat())
        group = webapp._view(101, f"group:{self.gid}")
        self.assertEqual(group["member_count"], 2)
        self.assertEqual(group["members"][0]["id"], self.pid)
        self.assertIn("pending_homework",group["members"][0])

    def test_inline_monthly_update_is_optimistic_and_does_not_duplicate_history(self):
        old = webapp._view(101,f"member:{self.pid}")["payment"]
        self.assertTrue(old["version"])
        from datetime import timedelta
        new_due = (self.day + timedelta(days=13)).isoformat()
        data = {
            "action":"member_payment_update", "member_id":self.pid,
            "payment_type":"monthly","amount":10500,
            "due":new_due,"expected_version":old["version"],
        }
        result=webapp._teacher_action(101,data)
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["payment"]["amount"],10500)
        self.assertEqual(result["payment"]["due"],new_due)
        self.assertNotEqual(result["payment"]["version"],old["version"])
        self.assertEqual(webapp._teacher_action(101,data)["error"],"payment_changed_refresh")
        self.assertEqual(self.group_payments._plan(101,self.pid)["amount_rub"],10500)
        with base.db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM group_member_payment_history "
                "WHERE teacher_telegram_user_id=? AND person_id=?",
                (101,self.pid),
            ).fetchone()[0]
        self.assertEqual(count,0)

    def test_inline_payment_never_reaches_other_teacher_or_other_group(self):
        old=webapp._view(101,f"member:{self.pid}")["payment"]
        payload={
            "action":"member_payment_update","member_id":self.pid,
            "payment_type":"once","amount":1500,
            "due":self.day.isoformat(),"expected_version":old["version"],
        }
        self.assertEqual(webapp._teacher_action(202,payload)["error"],"member_not_found")
        self.assertEqual(webapp._teacher_action(101,{**payload,"member_id":999999})["error"],"member_not_found")
        self.assertEqual(webapp._teacher_action(101,{**payload,"amount":-1})["error"],"invalid_amount")
        self.assertEqual(webapp._teacher_action(101,{**payload,"due":"tomorrow"})["error"],"invalid_due_date")
        self.assertEqual(self.group_payments._plan(101,self.pid)["amount_rub"],9900)

    def test_inline_full_course_payment_requires_receipt_and_is_locked_after(self):
        old=webapp._view(101,f"member:{self.pid}")["payment"]
        request={
            "action":"member_payment_update","member_id":self.pid,
            "payment_type":"course_paid","amount":85100,
            "received_date":self.day.isoformat(),
            "expected_version":old["version"],
        }
        self.assertEqual(webapp._teacher_action(101,request)["error"],"receipt_confirmation_required")
        saved=webapp._teacher_action(101,{**request,"received_confirmed":True})
        self.assertTrue(saved["ok"],saved)
        self.assertEqual(saved["payment"]["type"],"course")
        self.assertIsNone(saved["payment"]["due"])
        locked=webapp._teacher_action(101,{
            "action":"member_payment_update","member_id":self.pid,
            "payment_type":"monthly","amount":9900,"due":self.day.isoformat(),
            "expected_version":saved["payment"]["version"],
        })
        self.assertEqual(locked["error"],"full_course_locked")
        with base.db() as conn:
            records=conn.execute(
                "SELECT amount_rub,payment_type FROM group_member_payment_history "
                "WHERE person_id=?",
                (self.pid,),
            ).fetchall()
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]["amount_rub"],85100)

    def test_package_receipt_requires_confirmation_and_replay_does_not_top_up(self):
        old=webapp._view(101,f"member:{self.pid}")["payment"]
        request={
            "action":"member_payment_update","member_id":self.pid,
            "payment_type":"package","amount":12000,"lessons":8,
            "expected_version":old["version"],
        }
        self.assertEqual(webapp._teacher_action(101,request)["error"],"receipt_confirmation_required")
        self.assertTrue(webapp._teacher_action(101,{**request,"received_confirmed":True})["ok"])
        self.assertEqual(
            webapp._teacher_action(101,{**request,"received_confirmed":True})["error"],
            "payment_changed_refresh",
        )
        saved=webapp._view(101,f"member:{self.pid}")["payment"]
        self.assertEqual(saved["remaining"],8)
        self.assertEqual(saved["lessons_total"],8)
        self.assertEqual(
            webapp._teacher_action(101,{
                **request,"received_confirmed":True,
                "expected_version":saved["version"],
            })["error"],
            "package_replacement_confirmation_required",
        )
        with base.db() as conn:
            records=conn.execute(
                "SELECT id FROM group_member_payment_history WHERE person_id=?",
                (self.pid,),
            ).fetchall()
        self.assertEqual(len(records),1)

    def test_group_and_member_frontend_use_compact_navigation(self):
        html_content=webapp.HTML_PATH.read_text(encoding="utf-8")
        for snippet in (
            "function setGroupTab(tab)",
            "function renderGroup(d)",
            "function renderMember(d)",
            "function toggleMemberPaymentForm()",
            "async function saveMemberPayment()",
            "member_payment_update",
            "Предыдущий",
            "Следующий",
            "id=\"member-payment-form\"",
            "data-gpanel",
        ):
            self.assertIn(snippet,html_content)


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




class GroupHomeworkMiniAppTest(unittest.IsolatedAsyncioTestCase):
    """Issue homework through existing teacher-scoped tables on temporary SQLite."""

    def setUp(self):
        from datetime import datetime
        import teacher_product_learning as learning
        import teacher_product_webapp_homework as hwapp
        import teacher_product_student_reminders as student_reminders
        self.learning = learning
        self.hwapp = hwapp
        self.student_reminders = student_reminders
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "group_homework.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        student_reminders.ensure_tables()
        hwapp.ensure_tables()
        import teacher_product_group_payments as group_payments
        group_payments.ensure_tables()
        base.upsert_teacher(101, name="Мария", subject="Химия", onboarding_completed_at="2026-10-20")
        base.upsert_teacher(202, name="Другая", subject="Биология", onboarding_completed_at="2026-10-20")
        self.gid = groups.add_group(101, "ОГЭ 2027")
        self.mid = int(student_reminders.add_member(101, self.gid, "Алина")["id"])
        self.other_gid = groups.add_group(101, "ЕГЭ 2027")
        self.other_mid = int(student_reminders.add_member(101, self.other_gid, "Ева")["id"])
        self.empty_gid = groups.add_group(101, "Пустая группа")
        self.due = datetime.now(schedule.tz(101)).date().isoformat()
        self.payload = {
            "action": "group_homework_create", "group_id": self.gid,
            "homework_text": "Решить 10 задач", "due_date": self.due,
            "request_key": "prepodmin-work-001",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_group_homework_is_saved_once_and_reported_in_existing_views(self):
        from unittest.mock import patch
        with patch.object(self.learning, "_send_assignment") as sender:
            first = webapp._teacher_action(101, self.payload)
            second = webapp._teacher_action(101, self.payload)
            sender.assert_not_called()  # HTTP handler never sends student messages
        self.assertTrue(first["ok"], first)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["assignment_id"], second["assignment_id"])
        a = self.learning._assignment(first["assignment_id"], 101)
        self.assertEqual(a["homework_text"], "Решить 10 задач")
        self.assertEqual(a["due_date"], self.due)
        with base.db() as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM teacher_homework WHERE target_id=?",
                             (self.gid,)).fetchone()[0], 1,
            )
        group = webapp._view(101, f"group:{self.gid}")
        self.assertEqual(group["homework"][0]["total"], 1)
        self.assertEqual(group["homework"][0]["delivery"]["state"], "pending")
        self.assertEqual(group["members"][0]["pending_homework"], 1)
        person = webapp._view(101, f"member:{self.mid}")
        self.assertEqual(person["homework"][0]["id"], first["assignment_id"])
        self.assertEqual(person["homework"][0]["status"], "pending")

    def test_scope_validation_dates_and_idempotency_key_conflict(self):
        self.assertEqual(webapp._teacher_action(202,self.payload)["error"],"group_not_found")
        self.assertEqual(webapp._teacher_action(101,{**self.payload,"group_id":self.empty_gid})["error"],"empty_group")
        self.assertEqual(webapp._teacher_action(101,{**self.payload,"homework_text":" "})["error"],"invalid_homework_text")
        self.assertEqual(webapp._teacher_action(101,{**self.payload,"due_date":"2010-01-01"})["error"],"invalid_due_date")
        self.assertEqual(webapp._teacher_action(101,{**self.payload,"request_key":"!"})["error"],"invalid_request_key")
        self.assertTrue(webapp._teacher_action(101,self.payload)["ok"])
        changed = webapp._teacher_action(101,{**self.payload,"homework_text":"Другое задание"})
        self.assertEqual(changed["error"],"request_key_conflict")
        self.assertIsNone(self.learning._assignment(99999, 101))
        self.assertIsNone(self.learning._assignment(
            webapp._teacher_action(101,self.payload)["assignment_id"], 202
        ))

    def test_member_completion_marks_correct_assignment_without_cross_group_leak(self):
        first=webapp._teacher_action(101,self.payload)
        data={
            "action":"group_homework_mark",
            "assignment_id":first["assignment_id"],
            "member_id":self.mid,"status":"done",
        }
        self.assertEqual(webapp._teacher_action(202,data)["error"],"assignment_not_found")
        self.assertEqual(webapp._teacher_action(101,{**data,"member_id":self.other_mid})["error"],"member_not_found")
        self.assertEqual(webapp._teacher_action(101,{**data,"status":"unsafe"})["error"],"invalid_homework_status")
        self.assertTrue(webapp._teacher_action(101,data)["ok"])
        self.assertTrue(webapp._teacher_action(101,data)["unchanged"])
        self.assertEqual(webapp._view(101,f"group:{self.gid}")["homework"][0]["done"],1)
        self.assertEqual(webapp._view(101,f"member:{self.mid}")["homework"][0]["status"],"done")
        self.assertEqual(webapp._view(101,f"group:{self.gid}")["members"][0]["pending_homework"],0)
        self.assertTrue(webapp._teacher_action(101,{**data,"status":"pending"})["ok"])
        self.assertEqual(webapp._view(101,f"group:{self.gid}")["homework"][0]["done"],0)

    async def test_delivery_worker_uses_existing_send_once_not_in_http_thread(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        response = webapp._teacher_action(101,self.payload)
        self.assertEqual(response["delivery_state"],"pending")
        send=AsyncMock(return_value=(1,0,1))
        with patch.object(self.learning,"_send_assignment",send):
            await self.hwapp.delivery_tick(SimpleNamespace(bot=object()))
            await self.hwapp.delivery_tick(SimpleNamespace(bot=object()))
        send.assert_awaited_once()
        state = self.hwapp.delivery_state(101,response["assignment_id"])
        self.assertEqual(state["state"],"done")
        self.assertEqual(state["linked"],1)
        self.assertEqual(state["sent"],1)
        self.assertEqual(webapp._view(101,f"group:{self.gid}")["homework"][0]["delivery"]["state"],"done")

    async def test_failed_delivery_is_visible_but_not_automatically_retried(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        response=webapp._teacher_action(101,self.payload)
        send=AsyncMock(return_value=(0,1,1))
        with patch.object(self.learning,"_send_assignment",send):
            await self.hwapp.delivery_tick(SimpleNamespace(bot=object()))
            await self.hwapp.delivery_tick(SimpleNamespace(bot=object()))
        send.assert_awaited_once()
        self.assertEqual(self.hwapp.delivery_state(101,response["assignment_id"])["state"],"failed")

    def test_ui_uses_inline_homework_form_and_marking(self):
        body = webapp.HTML_PATH.read_text(encoding="utf-8")
        for marker in (
            "function toggleGroupHomeworkForm(gid)",
            "async function saveGroupHomework(gid)",
            "async function setMemberHomework(aid,pid,status)",
            "group_homework_create",
            "group_homework_mark",
            "teacherAction({",
        ):
            self.assertIn(marker,body)




class GroupLessonsMiniAppTest(unittest.IsolatedAsyncioTestCase):
    """One-off lesson changes on a temporary database, notifications fully mocked."""

    def setUp(self):
        from datetime import datetime, timedelta
        import teacher_product_webapp_lessons as lessons
        import teacher_product_learning as learning
        import teacher_product_cancellations as cancellations
        import teacher_product_group_payments as group_payments

        self.lessons=lessons
        self.learning=learning
        self.cancellations=cancellations
        self.tmp=tempfile.TemporaryDirectory()
        base.DB_PATH=os.path.join(self.tmp.name,"group_lessons.sqlite3")
        base.ensure_tables()
        groups.ensure_tables()
        schedule.ensure_tables()
        learning.ensure_tables()
        group_payments.ensure_tables()
        lessons.ensure_tables()
        base.upsert_teacher(101,name="Мария",subject="Химия",onboarding_completed_at="2026-10-20")
        base.upsert_teacher(202,name="Другая",subject="История",onboarding_completed_at="2026-10-20")
        self.gid=groups.add_group(101,"ОГЭ 2027")
        self.other_gid=groups.add_group(101,"ЕГЭ 2027")
        self.member=int(__import__("teacher_product_student_reminders").add_member(101,self.gid,"Алина")["id"])
        self.today=datetime.now(schedule.tz(101)).date()
        self.occurrence=self.today+timedelta(days=3)
        groups.add_group_slot(101,self.gid,self.occurrence.weekday(),"18:00")
        self.slot_id=int(next(s["id"] for s in groups.group_slots(101) if int(s["group_id"])==self.gid))
        self.original=self.occurrence.isoformat()
        self.key="webapp-lesson-0001"

    def tearDown(self):
        self.tmp.cleanup()

    def mutation(self,**changes):
        return {
            "action":"group_lesson_mutate",
            "lesson_action":"move","group_id":self.gid,
            "request_key":self.key,"slot_id":self.slot_id,
            "occurrence_key":self.original,"expected_date":self.original,
            "expected_time":"18:00","new_date":self.original,
            "new_time":"19:00",**changes,
        }

    def test_upcoming_identifies_single_occurrence_and_group(self):
        records=self.lessons.upcoming(101,self.gid)
        self.assertTrue(records)
        self.assertEqual(records[0]["slot_id"],self.slot_id)
        self.assertEqual(records[0]["occurrence_key"],self.original)
        self.assertEqual(records[0]["time"],"18:00")
        self.assertEqual(self.lessons.upcoming(202,self.gid),[])
        self.assertIn("lesson_occurrences",webapp._view(101,f"group:{self.gid}"))

    def test_add_weekly_lesson_is_idempotent_and_keeps_old_slot(self):
        data={"action":"group_lesson_mutate","lesson_action":"add",
              "group_id":self.gid,"request_key":"webapp-add-lesson-01",
              "weekday":1,"time":"17:30"}
        first=webapp._teacher_action(101,data)
        second=webapp._teacher_action(101,data)
        self.assertTrue(first["ok"],first)
        self.assertTrue(second["duplicate"],second)
        rows=[s for s in groups.group_slots(101) if int(s["group_id"])==self.gid]
        self.assertEqual(len(rows),2)
        self.assertEqual(webapp._teacher_action(101,{**data,"request_key":"webapp-add-lesson-02"})["error"],"slot_already_exists")
        self.assertEqual(
            webapp._teacher_action(101,{**data,"weekday":2})["error"],
            "request_key_conflict",
        )
        self.assertEqual(webapp._teacher_action(202,data)["error"],"group_not_found")
        self.assertEqual(webapp._teacher_action(101,{**data,"time":"not time"})["error"],"invalid_time")

    def test_move_specific_occurrence_and_preserve_next_week(self):
        result=webapp._teacher_action(101,self.mutation())
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["state"],"pending")
        dup=webapp._teacher_action(101,self.mutation())
        self.assertTrue(dup["duplicate"],dup)
        events=self.lessons.upcoming(101,self.gid)
        first=next(e for e in events if e["occurrence_key"]==self.original)
        self.assertEqual(first["time"],"19:00")
        self.assertTrue(first["moved"])
        following=next(e for e in events if e["occurrence_key"]!=self.original)
        self.assertEqual(following["time"],"18:00")
        self.assertFalse(following["moved"])
        self.assertEqual(
            webapp._teacher_action(101,self.mutation(request_key="webapp-lesson-0002"))["error"],
            "lesson_changed_refresh",
        )
        self.assertEqual(
            webapp._teacher_action(101,self.mutation(group_id=self.other_gid,request_key="webapp-lesson-0003"))["error"],
            "slot_not_found",
        )

    def test_cancel_one_future_lesson_without_archiving_schedule(self):
        result=webapp._teacher_action(101,{
            "action":"group_lesson_mutate","lesson_action":"cancel",
            "group_id":self.gid,"request_key":"webapp-cancel-0001",
            "slot_id":self.slot_id,"occurrence_key":self.original,
            "expected_date":self.original,"expected_time":"18:00",
        })
        self.assertTrue(result["ok"],result)
        self.assertTrue(self.cancellations.is_cancelled(101,"group",self.slot_id,self.original))
        occurrences=self.lessons.upcoming(101,self.gid)
        self.assertTrue(all(x["occurrence_key"]!=self.original for x in occurrences))
        self.assertTrue(any(x["occurrence_key"]!=self.original for x in occurrences))
        self.assertIsNotNone(groups.group_slot(101,self.slot_id))
        self.assertEqual(
            webapp._teacher_action(101,self.mutation(request_key="webapp-lesson-0004"))["error"],
            "lesson_cancelled",
        )

    def test_attendance_and_stale_form_protection(self):
        self.assertEqual(
            webapp._teacher_action(101,self.mutation(expected_time="20:00"))["error"],
            "lesson_changed_refresh",
        )
        self.learning._set_attendance(
            101,"group",self.slot_id,self.occurrence,"group_member",self.member,"present",
        )
        self.assertEqual(
            webapp._teacher_action(101,self.mutation())["error"],
            "attendance_already_recorded",
        )
        self.assertEqual(
            webapp._teacher_action(101,{
                "action":"group_lesson_mutate","lesson_action":"cancel",
                "group_id":self.gid,"request_key":"webapp-cancel-0002",
                "slot_id":self.slot_id,"occurrence_key":self.original,
                "expected_date":self.original,"expected_time":"18:00",
            })["error"],"attendance_already_recorded",
        )

    async def test_lesson_notification_worker_sends_once_through_existing_helpers(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock,patch
        p=webapp._teacher_action(101,self.mutation())
        self.assertTrue(p["ok"],p)
        async_send=AsyncMock(return_value=(1,0,1))
        with patch("teacher_product_transfer_enhancements._notify_transfer",async_send):
            await self.lessons.delivery_tick(SimpleNamespace(bot=object()))
            await self.lessons.delivery_tick(SimpleNamespace(bot=object()))
        async_send.assert_awaited_once()
        with base.db() as conn:
            rec=conn.execute("SELECT state,linked_count,sent_count FROM teacher_webapp_lesson_actions WHERE id=?",(p["action_id"],)).fetchone()
        self.assertEqual(rec["state"],"done")
        self.assertEqual(rec["sent_count"],1)
        self.assertEqual(rec["linked_count"],1)

    async def test_lesson_cancel_notification_worker_uses_original_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock,patch
        p=webapp._teacher_action(101,{
            "action":"group_lesson_mutate","lesson_action":"cancel",
            "group_id":self.gid,"request_key":"webapp-cancel-0003",
            "slot_id":self.slot_id,"occurrence_key":self.original,
            "expected_date":self.original,"expected_time":"18:00",
        })
        self.assertTrue(p["ok"],p)
        send=AsyncMock(return_value=(1,0,1))
        with patch.object(self.cancellations,"_notify_students",send):
            await self.lessons.delivery_tick(SimpleNamespace(bot=object()))
        send.assert_awaited_once()
        args=send.await_args.args
        self.assertEqual(args[2]["actual_date"],self.occurrence)
        self.assertEqual(args[2]["occurrence_key"],self.original)


    def test_lesson_notification_choice_validated_and_preserved_on_replay(self):
        data=self.mutation(notification_choice="draft")
        self.assertEqual(
            webapp._teacher_action(101,{**data,"notification_choice":"surprise"})["error"],
            "invalid_notification_choice",
        )
        first=webapp._teacher_action(101,data)
        self.assertTrue(first["ok"],first)
        self.assertEqual(first["state"],"pending")
        self.assertEqual(first["notification_choice"],"draft")
        self.assertTrue(webapp._teacher_action(101,data)["duplicate"])
        self.assertEqual(
            webapp._teacher_action(101,{**data,"notification_choice":"send"})["error"],
            "request_key_conflict",
        )
        with base.db() as conn:
            row=conn.execute(
                "SELECT notification_choice,state FROM teacher_webapp_lesson_actions WHERE id=?",
                (first["action_id"],),
            ).fetchone()
        self.assertEqual(row["notification_choice"],"draft")
        self.assertEqual(row["state"],"pending")

    async def test_send_now_overrides_global_off_only_for_this_lesson(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import teacher_product_student_messaging as messaging
        with base.db() as conn:
            conn.execute(
                "UPDATE student_reminder_people SET telegram_user_id=303 WHERE id=?",
                (self.member,),
            )
            conn.commit()
        messaging.set_mode(101,"off")
        result=webapp._teacher_action(101,self.mutation(notification_choice="send"))
        self.assertTrue(result["ok"],result)
        send=AsyncMock()
        await self.lessons.delivery_tick(SimpleNamespace(bot=SimpleNamespace(send_message=send)))
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["chat_id"],303)
        self.assertIn("занятие перенесено",send.await_args.kwargs["text"])
        self.assertEqual(messaging.get_mode(101),"off")
        with base.db() as conn:
            stored=conn.execute(
                "SELECT state,sent_count FROM teacher_webapp_lesson_actions WHERE id=?",
                (result["action_id"],),
            ).fetchone()
        self.assertEqual(stored["state"],"done")
        self.assertEqual(stored["sent_count"],1)

    async def test_draft_override_never_sends_directly_to_students(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import teacher_product_student_messaging as messaging
        with base.db() as conn:
            conn.execute(
                "UPDATE student_reminder_people SET telegram_user_id=303 WHERE id=?",
                (self.member,),
            )
            conn.commit()
        messaging.set_mode(101,"auto")
        response=webapp._teacher_action(101,self.mutation(notification_choice="draft"))
        self.assertTrue(response["ok"],response)
        send=AsyncMock()
        await self.lessons.delivery_tick(SimpleNamespace(bot=SimpleNamespace(send_message=send)))
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["chat_id"],101)
        self.assertIn("Черновик",send.await_args.kwargs["text"])
        with base.db() as conn:
            outbox=conn.execute(
                "SELECT recipient_chat_id,status,category FROM teacher_student_message_outbox "
                "WHERE teacher_telegram_user_id=?",
                (101,),
            ).fetchall()
        self.assertEqual(len(outbox),1)
        self.assertEqual(outbox[0]["status"],"draft")
        self.assertEqual(outbox[0]["recipient_chat_id"],303)
        self.assertEqual(outbox[0]["category"],"transfer")
        self.assertEqual(messaging.get_mode(101),"auto")

    async def test_no_notification_keeps_schedule_change_but_sends_nothing(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import teacher_product_student_messaging as messaging
        with base.db() as conn:
            conn.execute(
                "UPDATE student_reminder_people SET telegram_user_id=303 WHERE id=?",
                (self.member,),
            )
            conn.commit()
        messaging.set_mode(101,"auto")
        data=self.mutation(notification_choice="off")
        p=webapp._teacher_action(101,data)
        self.assertTrue(p["ok"],p)
        self.assertEqual(p["state"],"none")
        self.assertEqual(
            next(x for x in self.lessons.upcoming(101,self.gid)
                 if x["occurrence_key"]==self.original)["time"],"19:00",
        )
        send=AsyncMock()
        await self.lessons.delivery_tick(SimpleNamespace(bot=SimpleNamespace(send_message=send)))
        send.assert_not_awaited()
        with base.db() as conn:
            row=conn.execute(
                "SELECT state FROM teacher_webapp_lesson_actions WHERE id=?",
                (p["action_id"],),
            ).fetchone()
            count=conn.execute(
                "SELECT COUNT(*) FROM teacher_student_message_outbox",
            ).fetchone()[0]
        self.assertEqual(row["state"],"none")
        self.assertEqual(count,0)
        self.assertEqual(messaging.get_mode(101),"auto")

    async def test_cancellation_draft_uses_existing_gateway_without_student_send(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        import teacher_product_student_messaging as messaging
        with base.db() as conn:
            conn.execute(
                "UPDATE student_reminder_people SET telegram_user_id=303 WHERE id=?",
                (self.member,),
            )
            conn.commit()
        messaging.set_mode(101,"auto")
        payload={
            "action":"group_lesson_mutate","lesson_action":"cancel",
            "group_id":self.gid,"request_key":"webapp-cancel-draft-01",
            "slot_id":self.slot_id,"occurrence_key":self.original,
            "expected_date":self.original,"expected_time":"18:00",
            "notification_choice":"draft",
        }
        p=webapp._teacher_action(101,payload)
        self.assertTrue(p["ok"],p)
        send=AsyncMock()
        await self.lessons.delivery_tick(SimpleNamespace(bot=SimpleNamespace(send_message=send)))
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs["chat_id"],101)
        with base.db() as conn:
            rows=conn.execute(
                "SELECT category,status FROM teacher_student_message_outbox WHERE teacher_telegram_user_id=?",
                (101,),
            ).fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["category"],"cancellation")
        self.assertEqual(rows[0]["status"],"draft")
        self.assertTrue(self.cancellations.is_cancelled(101,"group",self.slot_id,self.original))

    def test_existing_legacy_lesson_action_table_is_migrated_in_place(self):
        with base.db() as conn:
            conn.execute("DROP TABLE teacher_webapp_lesson_actions")
            conn.execute(
                "CREATE TABLE teacher_webapp_lesson_actions ("
                "id INTEGER PRIMARY KEY,teacher_telegram_user_id INTEGER,"
                "group_id INTEGER,request_key TEXT,kind TEXT,slot_id INTEGER,"
                "original_date TEXT,old_date TEXT,old_time TEXT,new_date TEXT,"
                "new_time TEXT,group_name TEXT,moved_before INTEGER,"
                "state TEXT,created_at TEXT)"
            )
            conn.execute(
                "INSERT INTO teacher_webapp_lesson_actions ("
                "id,teacher_telegram_user_id,group_id,request_key,kind,"
                "slot_id,original_date,group_name,moved_before,state,created_at"
                ") VALUES(1,101,?,?,?,? ,?,?,? ,?,?)",
                (self.gid,"old-key-123456","add",self.slot_id,
                 None,"ОГЭ 2027",0,"none","2026-10-20T00:00:00"),
            )
            conn.commit()
        self.lessons.ensure_tables()
        with base.db() as conn:
            row=conn.execute("SELECT request_key,notification_choice FROM teacher_webapp_lesson_actions WHERE id=1").fetchone()
        self.assertEqual(row["request_key"],"old-key-123456")
        self.assertEqual(row["notification_choice"],"legacy")

    def test_lesson_form_ui_declares_real_controls(self):
        html=webapp.HTML_PATH.read_text(encoding="utf-8")
        for token in (
            "function startGroupLessonForm(","async function saveGroupLesson(",
            "group_lesson_mutate","lesson_occurrences","Перенести одно занятие",
            "Отменить одно занятие",
            "name=\"gl-notify\"",
            'value="draft" checked',
            "data.notification_choice=selectedNotification.value",
        ):
            self.assertIn(token,html)




if __name__ == "__main__":
    unittest.main()
