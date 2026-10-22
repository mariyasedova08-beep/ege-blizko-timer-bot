"""Offline scenarios: real handlers and SQLite; no token, network or production DB."""
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


class Button:
    def __init__(self, text, callback_data=None, url=None, **kwargs):
        self.text, self.callback_data, self.url = text, callback_data, url
        if callback_data is not None and len(callback_data.encode()) > 64:
            raise ValueError("Telegram callback_data exceeds 64 bytes")


class Markup:
    def __init__(self, rows, **kwargs):
        self.inline_keyboard = rows


def load_module(path, modules):
    spec = importlib.util.spec_from_file_location("offline_" + path[:-3], ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class RuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "test.sqlite")
        self.bot = types.SimpleNamespace(COREAPP_DB_PATH=self.db, TIMEZONE=timezone.utc)
        self.previous_start, self.previous_callback = AsyncMock(), AsyncMock()
        self.live7 = types.SimpleNamespace(
            start_router=self.previous_start, trivial_callback=self.previous_callback,
        )
        self.live41 = types.SimpleNamespace(
            register_weekly_trainer=self.register,
            ensure_weekly_report_tables=self.ensure_catalog,
            _weekly_trainer_stats=lambda conn, uid, now: (2, 20, 15),
            _week_start=lambda now: now.date() - timedelta(days=6),
        )
        live79 = types.SimpleNamespace(
            live7=self.live7, live41=self.live41, live23=types.SimpleNamespace(),
            live34=types.SimpleNamespace(), live56=types.SimpleNamespace(),
        )
        self.modules = {
            "telegram": types.SimpleNamespace(
                InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup,
                KeyboardButton=Button, ReplyKeyboardMarkup=Markup,
            ),
            "run_bot_live90": types.SimpleNamespace(bot=self.bot, live79=live79),
        }
        self.d = load_module("decomposition_trainer.py", self.modules)
        self.d.install()
        self.context = self.new_context()
        self.update = self.new_update(101)

    def new_context(self):
        return types.SimpleNamespace(
            user_data={}, args=[], bot=types.SimpleNamespace(
                get_me=AsyncMock(return_value=types.SimpleNamespace(username="test_bot")),
                get_chat_member=AsyncMock(return_value=types.SimpleNamespace(status="member")),
            ),
        )

    def new_update(self, uid):
        message = types.SimpleNamespace(reply_text=AsyncMock())
        return types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=uid),
            effective_chat=types.SimpleNamespace(type="private"),
            effective_message=message, message=message,
            callback_query=types.SimpleNamespace(
                data="", answer=AsyncMock(), edit_message_text=AsyncMock(),
            ),
        )

    def ensure_catalog(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS weekly_trainer_catalog (
                code TEXT PRIMARY KEY,title TEXT,start_param TEXT,sort_order INTEGER,active INTEGER)""")

    def register(self, code, title, start_param, sort_order=100, active=True):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT OR REPLACE INTO weekly_trainer_catalog VALUES(?,?,?,?,?)",
                         (code, title, start_param, sort_order, int(active)))

    def scalar(self, sql, args=()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, args).fetchone()[0]

    async def click(self, data, update=None, context=None):
        update, context = update or self.update, context or self.context
        update.callback_query.data = data
        await self.live7.trivial_callback(update, context)

    async def start(self, mode="10", update=None, context=None):
        await self.click(self.d.PREFIX + "start:" + mode, update, context)

    def answer_data(self, uid=101, good=True):
        s = self.d._load_state(uid)
        qid = s["ids"][s["index"]]
        correct = self.d.BY_ID[qid][2]
        index = s["choices"].index(correct)
        if not good:
            index = (index + 1) % 4
        return f"{self.d.PREFIX}a:{s['token']}:{qid}:{index}"

    def next_data(self, uid=101):
        s = self.d._load_state(uid)
        return f"{self.d.PREFIX}next:{s['token']}:{s['ids'][s['index']]}"

    def record(self, uid, qid, good):
        with sqlite3.connect(self.db) as conn:
            self.d._record_answer(conn, uid, qid, good)

    async def test_all_modes_complete_without_extra_final_click(self):
        for mode, size in [("10", 10), ("non_ovr", 25), ("ovr", 25), ("all", 50)]:
            with self.subTest(mode=mode):
                await self.start(mode)
                s = self.d._load_state(101)
                self.assertEqual(len(s["ids"]), size)
                self.assertEqual(len(set(s["ids"])), size)
                if mode in {"ovr", "non_ovr"}:
                    self.assertTrue(all(self.d.DECOMPOSITION_GROUPS[q] == mode for q in s["ids"]))
                for i in range(size):
                    await self.click(self.answer_data(good=i % 2 == 0))
                    text = self.update.callback_query.edit_message_text.call_args.args[0]
                    self.assertIn("→", text)
                    if i < size - 1:
                        self.assertNotIn("Готово!", text)
                        await self.click(self.next_data())
                self.assertIsNone(self.d._load_state(101))
                self.assertIn(f"{(size + 1) // 2}/{size}", text)
                with sqlite3.connect(self.db) as conn:
                    total, correct, finished = conn.execute(
                        "SELECT total,correct,finished_at FROM decomposition_sessions ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                self.assertEqual((total, correct), (size, (size + 1) // 2))
                self.assertIsNotNone(finished)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 110)
        self.assertIn("Тренировок: 4", self.d._stats_text(101))

    async def test_duplicate_and_stale_answer_and_next_are_ignored(self):
        await self.start()
        first = self.answer_data()
        await self.click(first)
        await self.click(first)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 1)
        old_next = self.next_data()
        await self.click(old_next)
        before = self.d._load_state(101)
        await self.click(first)  # replay question 1 on question 2
        await self.click(old_next)
        self.assertEqual(self.d._load_state(101), before)
        await self.click(self.answer_data())
        before = self.d._load_state(101)
        await self.click(old_next)  # stale next must not skip question 2's explanation
        self.assertEqual(self.d._load_state(101), before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 2)

    async def test_new_session_invalidates_old_buttons_and_bad_callbacks(self):
        await self.start()
        old = self.answer_data()
        await self.start("ovr")
        before = self.d._load_state(101)
        for data in [old, "triv:decomp:a:old:0", "triv:decomp:next:old", "triv:decomp:start:invalid",
                     self.answer_data().rsplit(":", 1)[0] + ":-1",
                     self.answer_data().rsplit(":", 1)[0] + ":four"]:
            await self.click(data)
        self.assertEqual(self.d._load_state(101), before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 0)

    async def test_latest_answer_controls_error_repeat_and_user_isolation(self):
        qid = "decomp001"
        for good in [True, True, False]:
            self.record(101, qid, good)
        self.assertEqual(self.d._error_ids(101), [qid])
        self.assertEqual(self.d._error_ids(202), [])
        self.record(101, qid, False)
        self.record(101, qid, True)
        self.assertEqual(self.d._error_ids(101), [])
        self.record(101, qid, False)
        await self.start("errors")
        self.assertEqual(self.d._load_state(101)["ids"], [qid])
        await self.click(self.answer_data())
        self.assertEqual(self.d._error_ids(101), [])
        self.assertIn("1/1", self.d._stats_text(101))

    async def test_error_queue_over_twenty_has_no_duplicates_or_lost_remainder(self):
        qids = list(self.d.BY_ID)[:25]
        for qid in qids:
            self.record(101, qid, False)
        await self.start("errors")
        ids = self.d._load_state(101)["ids"]
        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20)
        for i in range(20):
            await self.click(self.answer_data())
            if i < 19:
                await self.click(self.next_data())
        self.assertEqual(len(self.d._error_ids(101)), 5)
        await self.start("errors")
        self.assertEqual(len(self.d._load_state(101)["ids"]), 5)

    async def test_empty_error_mode_does_not_destroy_existing_progress(self):
        await self.start()
        before = self.d._load_state(101)
        await self.start("errors")
        self.assertEqual(before, self.d._load_state(101))
        self.assertIn("Ошибок на повторение пока нет", self.update.callback_query.edit_message_text.call_args.args[0])

    async def test_resume_after_restart_menu_and_intermediate_edit_failure(self):
        await self.start()
        before = self.d._load_state(101)
        await self.click(self.d.PREFIX + "menu")
        self.assertEqual(before, self.d._load_state(101))
        self.context = self.new_context()  # process/user_data loss
        self.d = load_module("decomposition_trainer.py", self.modules)
        await self.d.callback(self._callback_update(self.d.PREFIX + "resume"), self.context)
        self.assertEqual(before, self.d._load_state(101))
        self.update.callback_query.edit_message_text.side_effect = RuntimeError("Telegram unavailable")
        with self.assertRaises(RuntimeError):
            await self.d.callback(self._callback_update(self.answer_data()), self.context)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 1)
        saved = self.d._load_state(101)
        self.assertTrue(saved["answered"])
        self.update.callback_query.edit_message_text.side_effect = None
        await self.d.callback(self._callback_update(self.d.PREFIX + "resume"), self.context)
        self.assertIn("→", self.update.callback_query.edit_message_text.call_args.args[0])
        self.assertEqual(saved, self.d._load_state(101))

    def _callback_update(self, data):
        self.update.callback_query.data = data
        return self.update

    async def test_final_save_survives_telegram_failure_and_replay(self):
        self.record(101, "decomp001", False)
        await self.start("errors")
        last = self.answer_data()
        self.update.callback_query.edit_message_text.side_effect = RuntimeError("edit failed")
        with self.assertRaises(RuntimeError):
            await self.click(last)
        self.assertIsNone(self.d._load_state(101))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_sessions WHERE finished_at IS NOT NULL"), 1)
        self.update.callback_query.edit_message_text.side_effect = None
        await self.click(last)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 2)
        self.assertIn("Правильно: 1/1", self.d._stats_text(101))

    async def test_answer_write_failure_rolls_back_entire_transaction(self):
        await self.start()
        before = self.d._load_state(101)
        with patch.object(self.d, "_save_state", side_effect=sqlite3.OperationalError("write failed")):
            with self.assertRaises(sqlite3.OperationalError):
                await self.click(self.answer_data())
        self.assertEqual(self.d._load_state(101), before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_attempts"), 0)
        self.assertEqual(self.d._error_ids(101), [])

    async def test_two_users_cannot_answer_each_others_questions(self):
        second = self.new_update(202)
        await self.start()
        await self.start(update=second)
        first = self.d._load_state(101)
        second_state = self.d._load_state(202)
        await self.click(self.answer_data(), update=second)
        self.assertEqual(self.d._load_state(101), first)
        self.assertEqual(self.d._load_state(202), second_state)
        await self.click(self.answer_data(uid=202), update=second)
        self.assertEqual(self.d._load_state(101), first)
        self.assertTrue(self.d._load_state(202)["answered"])

    async def test_weekly_stats_exclude_abandoned_other_users_and_outside_window(self):
        now = datetime.now(timezone.utc)
        rows = [(101, 10, 7, now.isoformat()), (101, 25, 20, None),
                (202, 50, 50, now.isoformat()),
                (101, 50, 50, (now - timedelta(days=8)).isoformat()),
                (101, 50, 50, (now + timedelta(days=1)).isoformat())]
        with sqlite3.connect(self.db) as conn:
            for uid, total, correct, finished in rows:
                conn.execute("INSERT INTO decomposition_sessions(telegram_user_id,mode,total,correct,started_at,finished_at) VALUES(?,?,?,?,?,?)",
                             (uid, "10", total, correct, now.isoformat(), finished))
            self.assertEqual(self.live41._weekly_trainer_stats(conn, 101, now), (3, 30, 22))
        self.assertIn("Тренировок: 3", self.d._stats_text(101))  # lifetime includes old/future finished rows

    async def test_install_idempotent_and_other_routes_preserved(self):
        before = self.live7.trivial_callback
        self.d.install()
        self.assertIs(self.live7.trivial_callback, before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM weekly_trainer_catalog WHERE code='decomposition'"), 1)
        await self.click("triv:other")
        self.previous_callback.assert_awaited_once()
        self.context.args = ["other"]
        await self.live7.start_router(self.update, self.context)
        self.previous_start.assert_awaited_once()
        self.context.args = ["decomposition"]
        await self.live7.start_router(self.update, self.context)
        self.assertIn("Реакции разложения", self.update.message.reply_text.call_args.args[0])
        self.update.effective_chat.type = "group"
        await self.live7.start_router(self.update, self.context)
        self.assertEqual(self.previous_start.await_count, 2)
        count = self.scalar("SELECT COUNT(*) FROM decomposition_sessions")
        await self.start()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM decomposition_sessions"), count)

    def load_public(self):
        public = load_module("public_channel_trainers.py", self.modules)
        public.ensure_tables()
        public._is_course_student = lambda uid: uid == 101
        public._previous_start_router = self.live7.start_router
        public._previous_trivial_callback = self.live7.trivial_callback
        return public

    async def test_real_public_catalog_deep_link_gate_visibility_and_stats(self):
        public = self.load_public()
        markup = await public._hub_markup(self.context)
        self.assertEqual(sum(b.url == "https://t.me/test_bot?start=decomposition"
                             for row in markup.inline_keyboard for b in row), 1)
        self.context.args = ["decomposition"]
        channel_user = self.new_update(202)
        await public.start_router(channel_user, self.context)
        self.assertIn("Реакции разложения", channel_user.message.reply_text.call_args.args[0])
        self.context.bot.get_chat_member.return_value.status = "left"
        await public.start_router(channel_user, self.context)
        self.assertIn("Подпишись", channel_user.message.reply_text.call_args.args[0])
        public._set_public_active("decomposition", False)
        self.assertFalse(any(row[0] == "decomposition" for row in public._catalog_rows()))
        await public.start_router(channel_user, self.context)
        self.assertIn("временно скрыт", channel_user.message.reply_text.call_args.args[0])
        await public.start_router(self.update, self.context)  # course students retain access
        self.assertIn("Реакции разложения", self.update.message.reply_text.call_args.args[0])
        public._set_public_active("decomposition", True)
        self.record(101, "decomp001", False)
        await self.start("errors")
        await self.click(self.answer_data())
        self.assertIn("1 трен. · 100%", public._user_stats_text(101))
        self.assertIn("Всего тренировок: <b>0</b>", public._user_stats_text(202))

    async def test_monthly_goals_unchanged_after_three_decomposition_sessions(self):
        modules = dict(self.modules)
        modules.update({name: types.ModuleType(name) for name in [
            "run_bot_live49", "homework_deadline_logic", "payment_schedule",
            "payment_name_aliases", "ege_admin_webapp",
        ]})
        rewards = load_module("kulek_rewards.py", modules)
        self.register("trivial", "Existing trainer", "trivial")
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE trivial_sessions(telegram_user_id INTEGER,finished_at TEXT)")
            for _ in range(3):
                conn.execute("INSERT INTO trivial_sessions VALUES(101,'2026-10-22T12:00:00+00:00')")
        students = [(1, "Student", "", "", "", 101)]
        before = rewards._trainer_goals("2026-10", students)
        with sqlite3.connect(self.db) as conn:
            for _ in range(3):
                conn.execute("INSERT INTO decomposition_sessions(telegram_user_id,mode,total,correct,started_at,finished_at) VALUES(101,'10',10,10,'2026-10-22','2026-10-22')")
        after = rewards._trainer_goals("2026-10", students)
        self.assertEqual(after, before)
        self.assertEqual([g["code"] for g in after], ["trivial"])
        self.assertTrue(after[0]["students"][1]["earned"])


if __name__ == "__main__":
    unittest.main()
