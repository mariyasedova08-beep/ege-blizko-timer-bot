import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram import ReplyKeyboardMarkup

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_transfer_button as transfer


class FakeApp:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))


class TransferButtonTests(unittest.TestCase):
    def test_button_opens_both_existing_transfer_pickers(self):
        original = base.MAIN_KB
        base.MAIN_KB = ReplyKeyboardMarkup([
            ["➕ Быстрая задача"], ["👥 Ученики и группы", "📅 Расписание"],
            ["🔔 Напоминания", "💳 Оплаты"],
        ], resize_keyboard=True)
        try:
            app = FakeApp()
            transfer.install(app)
            rows = [[button.text for button in row] for row in base.MAIN_KB.keyboard]
            self.assertEqual(rows[2], [transfer.BUTTON])
            self.assertEqual(rows.count([transfer.BUTTON]), 1)
            self.assertEqual([group for group, _ in app.handlers], [-12, -12, -12])
            self.assertIs(app.handlers[1][1].callback, schedule.transfer_picker)
            self.assertIs(app.handlers[2][1].callback, groups.group_transfer_picker)
        finally:
            base.MAIN_KB = original

    def test_teacher_gets_format_selector(self):
        reply = AsyncMock()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=12),
            message=SimpleNamespace(reply_text=reply),
        )
        with patch.object(base, "teacher", return_value={"onboarding_completed_at": "2026-09-16"}):
            asyncio.run(transfer.transfer_menu(update, None))
        markup = reply.await_args.kwargs["reply_markup"]
        self.assertEqual(
            [row[0].callback_data for row in markup.inline_keyboard],
            ["transfer:individual", "transfer:group"],
        )


if __name__ == "__main__":
    unittest.main()
