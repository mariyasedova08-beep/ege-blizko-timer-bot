import asyncio
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_reminders as reminders
import teacher_product_student_reminders as students
from telegram.ext import ApplicationHandlerStop


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))


class FakeQuery:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append(text)

    async def edit_message_reply_markup(self, **kwargs):
        pass


class StudentRemindersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = base.DB_PATH
        base.DB_PATH = os.path.join(self.temp.name, "pilot.sqlite")
        base.ensure_tables()
        schedule.ensure_tables()
        groups.ensure_tables()
        reminders.ensure_tables()
        base.upsert_teacher(11, name="Преподаватель", onboarding_completed_at=datetime.utcnow().isoformat())
        base.add_student(11, "Анна")
        self.sid = base.list_students(11)[0]["id"]
        self.person = students._individual(11, self.sid)
        with base.db() as conn:
            conn.execute("UPDATE student_reminder_people SET telegram_user_id=22 WHERE id=?", (self.person["id"],))
        self.bot = FakeBot()
        self.context = SimpleNamespace(bot=self.bot)

    def tearDown(self):
        base.DB_PATH = self.old
        self.temp.cleanup()

    def event(self, when, occurrence=None):
        return dict(kind="individual", slot_id=4, person_id=self.sid, name="Анна",
                    occurrence_key=occurrence or when.date().isoformat(), event_dt=when, moved=False)

    def test_default_off_then_send_once_and_record_reply(self):
        self.assertFalse(students.enabled(11))
        when = datetime.now(schedule.tz(11)).replace(second=0, microsecond=0) + timedelta(hours=1)
        event = self.event(when)
        asyncio.run(reminders.check_reminders(self.context))  # no scheduled slot, no student message
        students.toggle(11)
        asyncio.run(students.deliver(self.context, 11, event, when - timedelta(hours=1)))
        asyncio.run(students.deliver(self.context, 11, event, when - timedelta(hours=1)))
        self.assertEqual(len(self.bot.sent), 1)
        self.assertEqual(self.bot.sent[0][0], 22)
        with base.db() as conn:
            mid = conn.execute("SELECT id FROM student_lesson_messages").fetchone()["id"]
        # The callback is accepted only for an actual active schedule slot.
        with base.db() as conn:
            conn.execute("INSERT INTO schedule_slots(id,teacher_telegram_user_id,student_id,weekday,time_text,created_at) VALUES(?,?,?,?,?,?)",
                         (4, 11, self.sid, when.weekday(), when.strftime("%H:%M"), datetime.utcnow().isoformat()))
        q = FakeQuery(22, f"srem:reply:{mid}:yes")
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(students.reply(SimpleNamespace(callback_query=q), self.context))
        self.assertEqual(students.reply_for(self.person["id"], event), "yes")
        self.assertEqual(len(self.bot.sent), 2)  # teacher hears about the reply
        asyncio.run(students.deliver(self.context, 11, event, when - timedelta(minutes=60)))
        self.assertEqual(len(self.bot.sent), 2)

    def test_old_reply_rejected_after_move(self):
        when = (datetime.now(schedule.tz(11)) + timedelta(days=1)).replace(second=0, microsecond=0)
        event = self.event(when)
        with base.db() as conn:
            conn.execute("INSERT INTO schedule_slots(id,teacher_telegram_user_id,student_id,weekday,time_text,created_at) VALUES(?,?,?,?,?,?)",
                         (4, 11, self.sid, when.weekday(), when.strftime("%H:%M"), datetime.utcnow().isoformat()))
        students.toggle(11)
        asyncio.run(students.deliver(self.context, 11, event, when - timedelta(hours=1)))
        with base.db() as conn:
            mid = conn.execute("SELECT id FROM student_lesson_messages").fetchone()["id"]
        schedule.save_move(11, 4, when.date().isoformat(), (when + timedelta(days=1)).date().isoformat(), when.strftime("%H:%M"))
        q = FakeQuery(22, f"srem:reply:{mid}:yes")
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(students.reply(SimpleNamespace(callback_query=q), self.context))
        self.assertIsNone(students.reply_for(self.person["id"], event))

    def test_group_recipients_only_members_of_that_group(self):
        groups.add_group(11, "Группа А")
        groups.add_group(11, "Группа Б")
        a, b = [r["id"] for r in groups.groups(11)]
        row = students.add_member(11, a, "Мила")
        with base.db() as conn:
            conn.execute("UPDATE student_reminder_people SET telegram_user_id=33 WHERE id=?", (row["id"],))
        event = dict(kind="group", person_id=a)
        self.assertEqual(len(students.recipients(11, event)), 1)
        self.assertEqual(len(students.recipients(11, dict(kind="group", person_id=b))), 0)
        groups.archive_group(11, a)
        self.assertEqual(len(students.recipients(11, event)), 0)


if __name__ == "__main__":
    unittest.main()
