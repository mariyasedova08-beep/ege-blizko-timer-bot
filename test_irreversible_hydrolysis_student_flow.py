"""Exercise the real hydrolysis handler with a simulated student and local SQLite.
No Telegram network calls and no production database access.
"""
import asyncio
import importlib.util
import sqlite3
import sys
import types
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, keyboard, **kwargs):
        self.inline_keyboard = keyboard
        self.keyboard = keyboard


class FakeMessage:
    def __init__(self):
        self.messages = []

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.messages.append((text, reply_markup))


class FakeQuery:
    def __init__(self):
        self.data = ""
        self.messages = []

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        self.messages.append((text, reply_markup))


def test_simulated_student_full_lifecycle(tmp_path, monkeypatch):
    telegram = types.ModuleType("telegram")
    telegram.InlineKeyboardButton = Button
    telegram.InlineKeyboardMarkup = Markup
    telegram.ReplyKeyboardMarkup = Markup
    monkeypatch.setitem(sys.modules, "telegram", telegram)

    calls = []
    async def fallback(*args, **kwargs):
        return None

    live7 = SimpleNamespace(
        STUDENT_KEYBOARD=Markup([["👤 Мой кабинет"], ["💳 Оплата"]]),
        trivial_callback=fallback,
        start_router=fallback,
        student_text_router=fallback,
    )
    live41 = SimpleNamespace(
        ensure_weekly_report_tables=lambda: None,
        register_weekly_trainer=lambda *a: calls.append(a),
        _weekly_trainer_stats=lambda *a: (0, 0, 0),
        _week_start=lambda now: now.date(),
    )
    live34 = SimpleNamespace(
        _trainer_metric=lambda *a: None,
        TRAINER_LOOKBACK_DAYS=7,
        TRAINER_MIN_SESSIONS=2,
    )
    live79 = SimpleNamespace(live7=live7, live41=live41, live34=live34)
    bot = SimpleNamespace(COREAPP_DB_PATH=str(tmp_path / "fake_student.sqlite"), TIMEZONE=ZoneInfo("UTC"))
    fake_runtime = types.ModuleType("run_bot_live85")
    fake_runtime.live79, fake_runtime.bot = live79, bot
    monkeypatch.setitem(sys.modules, "run_bot_live85", fake_runtime)

    # This is the actual trainer module, but imported with safe in-memory
    # Telegram stubs and a fresh temporary SQLite database.
    root = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("hydrolysis_simulated", root / "irreversible_hydrolysis_trainer.py")
    trainer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trainer)
    trainer.install()
    assert any(a[0] == "hydrolysis" for a in calls)
    assert any("🧪 Необратимый гидролиз" in row for row in live7.STUDENT_KEYBOARD.keyboard)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=314159, username="test_student", full_name="Тестовый ученик"),
        effective_chat=SimpleNamespace(type="private"),
        effective_message=FakeMessage(),
        message=FakeMessage(),
        callback_query=FakeQuery(),
    )
    context = SimpleNamespace(user_data={}, args=[])
    query = update.callback_query

    async def press(data):
        query.data = data
        await trainer.callback(update, context)

    async def trial():
        await trainer.show_menu(update, context)
        await press("triv:hydrolysis:start:10")
        for step in range(10):
            s = context.user_data["hydrolysis_session"]
            token, position = s["token"], s["index"]
            option = (s["correct_index"] + 1) % 4 if step == 0 else s["correct_index"]
            answer_data = f"triv:hydrolysis:a:{token}:{position}:{option}"
            await press(answer_data)
            if step == 0:
                # A second tap on the same old question must not be counted.
                await press(answer_data)
                with sqlite3.connect(bot.COREAPP_DB_PATH) as db:
                    assert db.execute("SELECT COUNT(*) FROM hydrolysis_attempts").fetchone()[0] == 1
            await press(f"triv:hydrolysis:next:{token}")
        assert "hydrolysis_session" not in context.user_data

        with sqlite3.connect(bot.COREAPP_DB_PATH) as db:
            assert db.execute("SELECT total,correct FROM hydrolysis_sessions").fetchone() == (10, 9)
            assert db.execute("SELECT COUNT(*) FROM hydrolysis_attempts").fetchone()[0] == 10
        assert len(trainer._unresolved_error_ids(update.effective_user.id)) == 1

        await press("triv:hydrolysis:start:errors")
        s = context.user_data["hydrolysis_session"]
        assert len(s["ids"]) == 1
        await press(f"triv:hydrolysis:a:{s['token']}:{s['index']}:{s['correct_index']}")
        await press(f"triv:hydrolysis:next:{s['token']}")
        assert trainer._unresolved_error_ids(update.effective_user.id) == []
        assert "11" in trainer._stats_text(update.effective_user.id)

    asyncio.run(trial())
