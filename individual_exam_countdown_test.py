import asyncio
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import individual_exam_countdown as countdown


class AtNine(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 16, 9, 1, tzinfo=tz or ZoneInfo("Europe/Moscow"))


class IndividualCountdownTests(unittest.TestCase):
    def test_text_contains_exam_days_without_group_lessons(self):
        with patch.object(countdown.bot, "days_left", return_value=258), patch.object(
            countdown.bot, "get_daily_phrase", return_value="Каждый день — шаг вперёд."
        ):
            text = countdown.countdown_text()
        self.assertIn("258 дней", text)
        self.assertIn("Каждый день — шаг вперёд.", text)
        for forbidden in ("Прогресс курса", "урок №", "Сегодня на курсе", "Расписание"):
            self.assertNotIn(forbidden, text)

    def test_daily_sends_only_linked_individual_once(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            countdown.bot, "COREAPP_DB_PATH", directory + "/test.db"
        ), patch.object(countdown, "datetime", AtNine), patch.object(
            countdown.live67, "_individual_rows", return_value=[
                (1, "Аня", 321, ""), (2, "Борис", None, ""),
            ]
        ), patch.object(countdown.bot, "days_left", return_value=258):
            countdown.ensure_delivery_table()
            client = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
            asyncio.run(countdown.daily_tick(client))
            asyncio.run(countdown.daily_tick(client))
            client.bot.send_message.assert_awaited_once()
            kwargs = client.bot.send_message.await_args.kwargs
            self.assertEqual(kwargs["chat_id"], 321)
            self.assertNotIn("урок", kwargs["text"].lower())


if __name__ == "__main__":
    unittest.main()
