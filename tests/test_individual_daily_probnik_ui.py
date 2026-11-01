import importlib.util
import os
from pathlib import Path
import types
import unittest
from unittest.mock import AsyncMock, patch


class DailyProbnikUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base = AsyncMock()
        self.live23 = types.SimpleNamespace(cabinet_callback=self.base, _admin_private=lambda u: True)
        live79 = types.SimpleNamespace(live67=types.SimpleNamespace(), live41=None,
            live23=self.live23, live7=types.SimpleNamespace(friday_trivial_tick=AsyncMock()))
        telegram = types.SimpleNamespace(
            InlineKeyboardButton=lambda text, **kw: types.SimpleNamespace(text=text, **kw),
            InlineKeyboardMarkup=lambda rows: types.SimpleNamespace(inline_keyboard=rows))
        fake90 = types.SimpleNamespace(live79=live79, bot=types.SimpleNamespace())
        with patch.dict('sys.modules', {'telegram': telegram, 'run_bot_live90': fake90}):
            spec = importlib.util.spec_from_file_location('daily_ui_test',
                Path(__file__).resolve().parents[1] / 'individual_trainer_daily.py')
            self.daily = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.daily)
        self.daily.ensure_individual_daily_tables = lambda: None

    def buttons(self, enabled, telegram_id):
        with patch.dict(os.environ, {'INDIVIDUAL_PROBNIK_ENABLED': enabled}):
            return [b for row in self.daily._individual_detail_markup(7, telegram_id).inline_keyboard for b in row]

    async def test_enabled_keeps_trainers_and_adds_probnik_for_same_individual(self):
        buttons = self.buttons('1', 101)
        self.assertEqual([b.callback_data for b in buttons], [
            'cab:individual:probnik:7', 'cab:individual:stats:7',
            'cab:individual:send:7', 'cab:individual:link:7', 'cab:individuals'])

    async def test_disabled_retains_original_buttons(self):
        self.assertFalse(any('probnik' in b.callback_data for b in self.buttons('0', 101)))

    async def test_unlinked_individual_can_still_view_saved_probnik(self):
        self.assertEqual([b.callback_data for b in self.buttons('1', None)], [
            'cab:individual:probnik:7', 'cab:individual:link:7', 'cab:individuals'])

    async def test_later_daily_install_delegates_probnik_to_existing_handler(self):
        self.daily.install()
        first = self.live23.cabinet_callback
        self.daily.install()
        self.assertIs(first, self.live23.cabinet_callback)
        update = types.SimpleNamespace(callback_query=types.SimpleNamespace(data='cab:individual:probnik:7'))
        context = object()
        await self.live23.cabinet_callback(update, context)
        self.base.assert_awaited_once_with(update, context)

    async def test_unauthorized_callback_uses_existing_access_control(self):
        self.daily.install()
        self.live23._admin_private = lambda u: False
        update = types.SimpleNamespace(callback_query=types.SimpleNamespace(data='cab:individual:probnik:7'))
        context = object()
        await self.live23.cabinet_callback(update, context)
        self.base.assert_awaited_once_with(update, context)
