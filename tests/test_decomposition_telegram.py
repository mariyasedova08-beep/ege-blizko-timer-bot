"""Real PTB 21.10 dispatcher/serialization with an in-memory Bot API transport.

No registered bot, real token, polling, network, production modules or student DB.
run_bot_live90 and the reporting module's run_bot_live40 dependency use synthetic hosts;
Telegram Update, Application, handlers, contexts, Bot and requests are genuine.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import telegram
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from telegram.request import BaseRequest

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_TOKEN = "900001:OFFLINE_ONLY_NEVER_A_REGISTERED_BOT_TOKEN"
BOT_USER = {"id": 900001, "is_bot": True, "first_name": "Offline", "username": "offline_decomposition"}


class MemoryBotAPI(BaseRequest):
    def __init__(self):
        self.calls = []
        self.messages = {}
        self.member_status = "member"
        self.sequence = 0

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        api_method = url.rsplit("/", 1)[-1]
        # Round-trip actual PTB serialization, including the nested keyboard JSON.
        params = json.loads(request_data.json_payload) if request_data else {}
        self.calls.append((api_method, params))
        if api_method == "getMe":
            result = BOT_USER
        elif api_method == "answerCallbackQuery":
            result = True
        elif api_method == "getChatMember":
            result = {"status": self.member_status, "user": {
                "id": int(params["user_id"]), "is_bot": False, "first_name": "Synthetic",
            }}
        elif api_method in {"sendMessage", "editMessageText"}:
            uid = int(params["chat_id"])
            if api_method == "sendMessage":
                self.sequence += 1
                mid = self.sequence
            else:
                mid = int(params["message_id"])
            markup = json.loads(params["reply_markup"]) if "reply_markup" in params else None
            if markup:
                for row in markup["inline_keyboard"]:
                    for button in row:
                        data = button.get("callback_data")
                        if data is not None and not 1 <= len(data.encode("utf-8")) <= 64:
                            raise AssertionError("Invalid Telegram callback_data size")
            result = {"message_id": mid, "date": 1792670400, "from": BOT_USER,
                      "chat": {"id": uid, "type": "private"}, "text": params["text"]}
            if markup:
                result["reply_markup"] = markup
            self.messages[uid, mid] = copy.deepcopy(result)
        else:
            # Unexpected APIs can never escape to real Telegram.
            raise AssertionError("Unexpected Bot API method: " + api_method)
        return 200, json.dumps({"ok": True, "result": result}).encode("utf-8")

    def last_message(self, uid=101):
        return copy.deepcopy(max((msg for (chat, _mid), msg in self.messages.items() if chat == uid),
                                 key=lambda msg: msg["message_id"]))


def load_source(name, host):
    spec = importlib.util.spec_from_file_location("ptb_offline_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"run_bot_live90": host}):
        spec.loader.exec_module(module)
    return module


class TelegramProtocolTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertEqual(telegram.__version__, "21.10")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "synthetic.sqlite")
        self.api = MemoryBotAPI()
        self.errors = []
        self.update_sequence = 0
        # Even an accidental real HTTP request would fail before network access.
        for target in ["socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo"]:
            blocker = patch(target, side_effect=AssertionError("Network forbidden in offline Telegram test"))
            blocker.start()
            self.addCleanup(blocker.stop)
        await self.create_app()

    async def asyncTearDown(self):
        await self.app.shutdown()
        self.assertEqual(self.errors, [], "PTB routed an exception to the error handler")

    async def create_app(self, public=False):
        settings = types.SimpleNamespace(COREAPP_DB_PATH=self.db, TIMEZONE=timezone.utc)
        async def fallback(update, context):
            await update.effective_message.reply_text("FALLBACK_OTHER_ROUTE")
        live7 = types.SimpleNamespace(start_router=fallback, trivial_callback=fallback,
                                     friday_trivial_tick=fallback)
        # Execute the actual reporting module, isolating only its legacy host.
        # No reporting SQL, registration, aggregation or link builder is replaced.
        settings.get_admin_id = lambda: None
        legacy = types.SimpleNamespace(bot=settings)
        for name in ("live39", "live37", "live35", "live31", "live24", "live17"):
            setattr(legacy, name, types.SimpleNamespace())
        legacy.live34 = types.SimpleNamespace(live7=live7, run_bot=types.SimpleNamespace())
        spec = importlib.util.spec_from_file_location(
            "ptb_offline_reporting", ROOT / "run_bot_live41.py")
        reporting = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"run_bot_live40": legacy}):
            spec.loader.exec_module(reporting)
        self.reporting = reporting
        # Existing trainers have their own tables before the new trainer installs.
        with sqlite3.connect(self.db) as conn:
            for table in ("trivial_sessions", "acid_sessions"):
                conn.execute(f"""CREATE TABLE IF NOT EXISTS {table}(
                    telegram_user_id INTEGER,total INTEGER,correct INTEGER,finished_at TEXT)""")
        host = types.SimpleNamespace(bot=settings, live79=types.SimpleNamespace(
            live7=live7, live41=reporting, live23=types.SimpleNamespace(),
        ))
        self.trainer = load_source("decomposition_trainer", host)
        self.trainer.install()
        if public:
            self.public = load_source("public_channel_trainers", host)
            self.public.ensure_tables()
            self.public._is_course_student = lambda uid: uid == 101
            self.public._previous_start_router = live7.start_router
            self.public._previous_trivial_callback = live7.trivial_callback
            live7.start_router, live7.trivial_callback = self.public.start_router, self.public.trivial_callback
        self.app = (Application.builder().token(OFFLINE_TOKEN).updater(None)
                    .request(self.api).get_updates_request(MemoryBotAPI()).build())
        self.app.add_handler(CommandHandler("start", live7.start_router))
        self.app.add_handler(CallbackQueryHandler(live7.trivial_callback, pattern=r"^triv:"))
        async def error_handler(update, context):
            self.errors.append(context.error)
        self.app.add_error_handler(error_handler)
        await self.app.initialize()

    async def process(self, data):
        self.update_sequence += 1
        data["update_id"] = self.update_sequence
        await self.app.process_update(Update.de_json(data, self.app.bot))
        self.assertEqual(self.errors, [])

    async def command(self, argument="decomposition", uid=101):
        text = "/start " + argument
        await self.process({"message": {
            "message_id": 100000 + self.update_sequence, "date": 1792670400,
            "from": {"id": uid, "is_bot": False, "first_name": "Synthetic"},
            "chat": {"id": uid, "type": "private"}, "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
        }})

    async def click(self, data, uid=101, message=None):
        await self.process({"callback_query": {
            "id": "synthetic_" + str(self.update_sequence), "chat_instance": "offline_chat",
            "from": {"id": uid, "is_bot": False, "first_name": "Synthetic"},
            "message": message or self.api.last_message(uid), "data": data,
        }})

    def button_data(self, text, uid=101, exact=False):
        for row in self.api.last_message(uid)["reply_markup"]["inline_keyboard"]:
            for button in row:
                if (button["text"] == text) if exact else (text in button["text"]):
                    return button["callback_data"]
        self.fail("Button not found: " + text)

    def answer_data(self, good=True, uid=101):
        state = self.trainer._load_state(uid)
        qid = state["ids"][state["index"]]
        correct = self.trainer.BY_ID[qid][2]
        for row in self.api.last_message(uid)["reply_markup"]["inline_keyboard"]:
            for button in row:
                if ":a:" in button.get("callback_data", "") and (button["text"] == correct) == good:
                    return button["callback_data"]
        self.fail("Answer button not found")

    def count(self, table):
        with sqlite3.connect(self.db) as conn:
            return conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    async def test_command_and_complete_all_four_modes_through_real_dispatcher(self):
        await self.command()
        self.assertIn("Реакции разложения", self.api.last_message()["text"])
        for label, size in [("⚡ 10 случайных", 10), ("НЕ ОВР · 25", 25), ("ОВР · 25", 25), ("🧪 Все 50", 50)]:
            with self.subTest(mode=label):
                if self.trainer._load_state(101) is None:
                    await self.command()
                await self.click(self.button_data(label, exact=True))
                for i in range(size):
                    await self.click(self.answer_data(good=i % 2 == 0))
                    self.assertIn("→", self.api.last_message()["text"])
                    if i < size - 1:
                        await self.click(self.button_data("Дальше"))
                self.assertIn(f"{(size + 1) // 2}/{size}", self.api.last_message()["text"])
                self.assertIsNone(self.trainer._load_state(101))
        await self.click(self.button_data("Статистика"))
        self.assertIn("Тренировок: 4", self.api.last_message()["text"])
        self.assertEqual(self.count("decomposition_attempts"), 110)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(self.reporting._weekly_trainer_stats(
                conn, 101, datetime.now(timezone.utc)), (4, 110, 56))
        methods = {name for name, _params in self.api.calls}
        self.assertEqual(methods, {"getMe", "sendMessage", "editMessageText", "answerCallbackQuery"})

    async def test_old_callbacks_and_second_user_cannot_change_current_question(self):
        await self.command()
        await self.click(self.button_data("10 случайных"))
        old_message, old_answer = self.api.last_message(), self.answer_data()
        await self.click(old_answer)
        await self.click(old_answer, message=old_message)
        old_next, old_explanation = self.button_data("Дальше"), self.api.last_message()
        await self.click(old_next)
        before = self.trainer._load_state(101)
        await self.click(old_answer, message=old_message)
        await self.click(old_next, message=old_explanation)
        self.assertEqual(self.trainer._load_state(101), before)
        await self.command(uid=202)
        await self.click(self.button_data("10 случайных", uid=202), uid=202)
        await self.click(old_answer, uid=202)
        self.assertEqual(self.count("decomposition_attempts"), 1)
        self.assertEqual(self.trainer._load_state(101), before)

    async def test_application_recreation_restores_question_and_explanation(self):
        await self.command()
        await self.click(self.button_data("10 случайных"))
        question = self.trainer._load_state(101)
        await self.app.shutdown()
        await self.create_app()
        self.assertEqual(dict(self.app.user_data), {})
        await self.command()
        await self.click(self.button_data("Продолжить"))
        self.assertEqual(self.trainer._load_state(101), question)
        await self.click(self.answer_data(good=False))
        answer = self.trainer._load_state(101)
        await self.app.shutdown()
        await self.create_app()
        await self.command()
        await self.click(self.button_data("Продолжить"))
        self.assertEqual(self.trainer._load_state(101), answer)
        self.assertIn("Верный ответ", self.api.last_message()["text"])
        self.assertEqual(self.count("decomposition_attempts"), 1)

    async def test_public_hub_link_membership_hidden_catalog_and_other_start(self):
        await self.app.shutdown()
        await self.create_app(public=True)
        await self.command("trainers", uid=202)
        urls = [b.get("url") for row in self.api.last_message(202)["reply_markup"]["inline_keyboard"] for b in row]
        self.assertIn("https://t.me/offline_decomposition?start=decomposition", urls)
        await self.command(uid=202)
        self.assertIn("Реакции разложения", self.api.last_message(202)["text"])
        self.api.member_status = "left"
        await self.command(uid=202)
        self.assertIn("Подпишись", self.api.last_message(202)["text"])
        self.public._set_public_active("decomposition", False)
        await self.command(uid=202)
        self.assertIn("временно скрыт", self.api.last_message(202)["text"])
        await self.command(uid=101)
        self.assertIn("Реакции разложения", self.api.last_message(101)["text"])
        await self.command("unrelated", uid=101)
        self.assertEqual(self.api.last_message(101)["text"], "FALLBACK_OTHER_ROUTE")
        self.assertIn("getChatMember", {method for method, _params in self.api.calls})

    async def test_real_weekly_report_preserves_existing_totals_and_registered_link(self):
        now = datetime.now(timezone.utc)
        start = datetime.combine(self.reporting._week_start(now), datetime.min.time(),
                                 tzinfo=timezone.utc)
        with sqlite3.connect(self.db) as conn:
            for table, total, correct in (("trivial_sessions", 10, 8), ("acid_sessions", 25, 20)):
                conn.execute(f"INSERT INTO {table} VALUES(?,?,?,?)",
                             (101, total, correct, now.isoformat()))
                conn.execute(f"INSERT INTO {table} VALUES(?,?,?,?)",
                             (202, 50, 50, now.isoformat()))
                conn.execute(f"INSERT INTO {table} VALUES(?,?,?,?)",
                             (101, 50, 50, (start - timedelta(seconds=1)).isoformat()))
        await self.command()
        await self.click(self.button_data("10 случайных"))
        for i in range(10):
            await self.click(self.answer_data(good=i < 7))
            if i < 9:
                await self.click(self.button_data("Дальше"))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(self.reporting._weekly_trainer_stats(
                conn, 101, datetime.now(timezone.utc)), (3, 45, 35))
        # Recreating the application re-registers without duplicate rows/counting.
        await self.app.shutdown()
        await self.create_app()
        self.assertEqual(self.count("weekly_trainer_catalog"), 1)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(self.reporting._weekly_trainer_stats(
                conn, 101, datetime.now(timezone.utc)), (3, 45, 35))
        markup = await self.reporting._weekly_report_markup(types.SimpleNamespace(bot=self.app.bot))
        self.assertEqual([b.url for row in markup.inline_keyboard for b in row],
                         ["https://t.me/offline_decomposition?start=decomposition"])
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE weekly_trainer_catalog SET active=0 WHERE code='decomposition'")
        self.assertIsNone(await self.reporting._weekly_report_markup(
            types.SimpleNamespace(bot=self.app.bot)))


if __name__ == "__main__":
    unittest.main()
