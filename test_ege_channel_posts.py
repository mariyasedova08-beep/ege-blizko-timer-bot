"""Offline tests: no Telegram API, no EGE BLIZKO production database.

Use a stub of the existing public trainer catalog to keep tests independent
of the dozens of runtime wrappers in the actual EGE bot.
"""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
import sys


class TestHarness:
    def setUp(self):
        self.tmp = TemporaryDirectory()
        hub = ModuleType("public_channel_trainers")
        hub.CHANNEL_USERNAME = "@egeblizko_chem"
        hub._catalog_rows = lambda include_hidden=False: [
            ("middlesalts", "🧂 Свойства средних солей", "middlesalts", 55, 1),
            ("oxides", "🧪 Оксиды", "oxides", 40, 1),
        ]
        hub.bot = SimpleNamespace(
            COREAPP_DB_PATH=str(Path(self.tmp.name) / "test.sqlite3"),
            user_is_admin=lambda update: update.effective_user.id == 42,
        )
        hub.live7 = SimpleNamespace(student_text_router=AsyncMock())
        hub.live23 = SimpleNamespace(cabinet_callback=AsyncMock())
        self.old_hub = sys.modules.get("public_channel_trainers")
        sys.modules["public_channel_trainers"] = hub
        spec = importlib.util.spec_from_file_location(
            "_ege_channel_posts_test", Path(__file__).with_name("ege_channel_posts.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.p = module
        self.p.ensure_tables()

    def tearDown(self):
        if self.old_hub is None:
            sys.modules.pop("public_channel_trainers", None)
        else:
            sys.modules["public_channel_trainers"] = self.old_hub
        self.tmp.cleanup()

    def update(self, uid=42, data=""):
        q = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=uid),
            effective_chat=SimpleNamespace(type="private"),
            callback_query=q,
        )

    def ctx(self, can_post=True):
        return SimpleNamespace(
            bot=SimpleNamespace(
                id=1001,
                username="ege_blizko_timer_bot",
                get_chat_member=AsyncMock(return_value=SimpleNamespace(
                    status="administrator", can_post_messages=can_post
                )),
                send_message=AsyncMock(return_value=SimpleNamespace(message_id=1234)),
            )
        )


class DraftTests(TestHarness, TestCase):
    def test_initial_state_no_post_and_safe_deeplink(self):
        draft_id, body, url = self.p.create_draft(
            42, self.p._trainer("middlesalts"), "ege_blizko_timer_bot"
        )
        self.assertIn("100 вопросов", body)
        self.assertIn("start=middlesalts", url)
        self.assertEqual(self.p._draft(draft_id, 42)["status"], "draft")

    def test_admin_owner_bound_and_atomic_one_time_send(self):
        draft_id, _, _ = self.p.create_draft(42, self.p._trainer("oxides"), "ege_blizko_timer_bot")
        self.assertFalse(self.p.claim_draft(draft_id, 43))
        self.assertTrue(self.p.claim_draft(draft_id, 42))
        self.assertFalse(self.p.claim_draft(draft_id, 42))
        self.p._finish(draft_id, 42, "sent", 345)
        self.assertEqual(self.p._draft(draft_id, 42)["message_id"], 345)

    def test_cancelled_draft_cannot_send(self):
        draft_id, _, _ = self.p.create_draft(42, self.p._trainer("oxides"), "ege_blizko_timer_bot")
        self.assertTrue(self.p._cancel(draft_id, 42))
        self.assertFalse(self.p.claim_draft(draft_id, 42))

    def test_escaped_untrusted_catalog_title(self):
        _, body = self.p._make_post(
            ("test", "<h1>Привет</h1>", "test"), "ege_blizko_timer_bot"
        )
        self.assertIn("&lt;h1&gt;", body)
        self.assertNotIn("<h1>", body)

    def test_no_startup_publish_side_effect(self):
        self.assertFalse(self.p._INSTALLED)
        with self.p._db() as db:
            n = db.execute("SELECT COUNT(*) FROM ege_channel_post_drafts").fetchone()[0]
        self.assertEqual(n, 0)


class TelegramFlowTests(TestHarness, IsolatedAsyncioTestCase):
    async def test_only_admin_private_and_manual_confirm_can_publish(self):
        ctx = self.ctx()
        upd = self.update(data="cab:post:new:middlesalts")
        await self.p.cabinet_callback(upd, ctx)
        ctx.bot.send_message.assert_not_awaited()
        with self.p._db() as db:
            draft_id = db.execute("SELECT id FROM ege_channel_post_drafts").fetchone()[0]
        upd.callback_query.data = f"cab:post:send:{draft_id}"
        await self.p.cabinet_callback(upd, ctx)
        ctx.bot.send_message.assert_awaited_once()
        self.assertEqual(ctx.bot.send_message.await_args.kwargs["chat_id"], "@egeblizko_chem")
        self.assertEqual(self.p._draft(draft_id, 42)["status"], "sent")
        await self.p.cabinet_callback(upd, ctx)
        self.assertEqual(ctx.bot.send_message.await_count, 1)

    async def test_non_admin_cannot_publish(self):
        ctx = self.ctx()
        upd = self.update(uid=9, data="cab:post:new:oxides")
        await self.p.cabinet_callback(upd, ctx)
        ctx.bot.send_message.assert_not_awaited()
        with self.p._db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ege_channel_post_drafts").fetchone()[0], 0)

    async def test_missing_channel_permission_blocks_publish(self):
        ctx = self.ctx(can_post=False)
        draft_id, _, _ = self.p.create_draft(42, self.p._trainer("oxides"), "ege_blizko_timer_bot")
        upd = self.update(data=f"cab:post:send:{draft_id}")
        await self.p.cabinet_callback(upd, ctx)
        ctx.bot.send_message.assert_not_awaited()
        self.assertEqual(self.p._draft(draft_id, 42)["status"], "draft")

    async def test_unknown_send_result_does_not_retry(self):
        ctx = self.ctx()
        ctx.bot.send_message.side_effect = TimeoutError("network")
        draft_id, _, _ = self.p.create_draft(42, self.p._trainer("oxides"), "ege_blizko_timer_bot")
        upd = self.update(data=f"cab:post:send:{draft_id}")
        await self.p.cabinet_callback(upd, ctx)
        self.assertEqual(self.p._draft(draft_id, 42)["status"], "unknown")
        await self.p.cabinet_callback(upd, ctx)
        self.assertEqual(ctx.bot.send_message.await_count, 1)
