import os
import sqlite3
import unittest
from unittest.mock import patch

import probnik_result_notify as notice


class ProbnikResultNotificationQueueTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def push(self, new_primary=25, new_secondary=72):
        return notice.queue_publication(
            self.conn, student_name="Тестовый ученик",
            event_name="Пробник", event_date="31.10.2026",
            new_primary=new_primary, new_secondary=new_secondary,
        )

    def count(self):
        notice.ensure_tables(self.conn)
        return self.conn.execute(
            "SELECT COUNT(*) FROM probnik_result_notice_queue"
        ).fetchone()[0]

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(self.push())
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='probnik_result_notice_queue'"
            ).fetchone()[0], 0
        )

    def test_new_result_queued_once(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertTrue(self.push())
            self.assertFalse(self.push())
        self.assertEqual(self.count(), 1)

    def test_repeat_and_score_correction_never_duplicate(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertTrue(self.push())
            self.assertFalse(self.push(new_primary=27, new_secondary=77))
        self.assertEqual(self.count(), 1)

    def test_tasks_only_without_score_not_queued(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertFalse(self.push(new_primary=None, new_secondary=None))
        self.assertEqual(self.count(), 0)


import asyncio
import sys
import tempfile
import types
from unittest.mock import AsyncMock

class ProbnikDispatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = self.tmp.name + '/isolated.db'
        self.env = patch.dict(os.environ, {notice.ENV_FLAG: '1'})
        self.env.start()
        self.student = ('test', None, None, None, None, 123)
        self.live = types.ModuleType('run_bot_live56')
        self.live.bot = types.SimpleNamespace(COREAPP_DB_PATH=self.db)
        self.live._all_active_students = lambda: []
        self.live.unique_probnik_student_match = lambda name, rows: self.student
        self.modules = patch.dict(sys.modules, {'run_bot_live56': self.live})
        self.modules.start()
        self.sender = AsyncMock()
        self.context = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=self.sender))
        with sqlite3.connect(self.db) as conn:
            notice.queue_publication(conn, student_name='Тест', event_name='Пробник',
                event_date='31.10.2026', new_primary=25, new_secondary=72)

    def tearDown(self):
        self.modules.stop()
        self.env.stop()
        self.tmp.cleanup()

    def status(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute('SELECT status FROM probnik_result_notice_queue').fetchone()[0]

    async def test_success_not_resent(self):
        await notice.dispatch_pending(self.context)
        await notice.dispatch_pending(self.context)
        self.assertEqual(self.sender.await_count, 1)
        self.assertEqual(self.status(), 'sent')

    async def test_failure_retries(self):
        self.sender.side_effect = RuntimeError('simulated failure')
        await notice.dispatch_pending(self.context)
        self.assertEqual(self.status(), 'pending')
        self.sender.side_effect = None
        await notice.dispatch_pending(self.context)
        self.assertEqual(self.status(), 'sent')
        self.assertEqual(self.sender.await_count, 2)

    async def test_missing_student_blocked(self):
        self.student = None
        await notice.dispatch_pending(self.context)
        self.sender.assert_not_awaited()
        self.assertEqual(self.status(), 'blocked')

    async def test_missing_link_blocked(self):
        self.student = ('test', None, None, None, None, None)
        await notice.dispatch_pending(self.context)
        self.sender.assert_not_awaited()
        self.assertEqual(self.status(), 'blocked')

    async def test_disabled_keeps_pending(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: '0'}):
            await notice.dispatch_pending(self.context)
        self.sender.assert_not_awaited()
        self.assertEqual(self.status(), 'pending')

    async def test_overlapping_dispatch_no_duplicate(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def send(**kwargs):
            entered.set()
            await release.wait()
        self.sender.side_effect = send
        first = asyncio.create_task(notice.dispatch_pending(self.context))
        await entered.wait()
        second = asyncio.create_task(notice.dispatch_pending(self.context))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(self.sender.await_count, 1)
        self.assertEqual(self.status(), 'sent')


if __name__ == "__main__":
    unittest.main()

