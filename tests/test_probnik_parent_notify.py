import os
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch
import probnik_parent_notify as parents
import probnik_result_notify as students


class ParentNoticeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = self.tmp.name+'/test.db'
        self.env = patch.dict(os.environ, {parents.FLAG:'1',parents.SINCE:'2026-10-31T00:00:00+00:00',students.ENV_FLAG:'1'})
        self.env.start()
        self.student = (1, 'TEST', '', '', '', None)
        self.live = types.ModuleType('run_bot_live56')
        self.live.bot = types.SimpleNamespace(COREAPP_DB_PATH=self.db)
        self.live._all_active_students = lambda: [self.student] if self.student else []
        self.live.unique_probnik_student_match = lambda name, rows: self.student if rows else None
        self.modules = patch.dict(sys.modules, {'run_bot_live56':self.live})
        self.modules.start()
        self.send = AsyncMock()
        self.ctx = types.SimpleNamespace(bot=types.SimpleNamespace(send_message=self.send))
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE parent_links(parent_telegram_user_id INTEGER,student_id INTEGER,active INTEGER)')
            c.executemany('INSERT INTO parent_links VALUES(?,?,?)',[(101,1,1),(102,1,1),(999,2,1),(103,1,0)])
            c.execute('CREATE TABLE probnik_results(student_name TEXT,event_name TEXT,event_date TEXT,primary_score REAL,secondary_score REAL)')
            c.execute("INSERT INTO probnik_results VALUES('TEST','TEST EVENT','31.10.2026',0,0)")
            students.queue_publication(c,student_name='TEST',event_name='TEST EVENT',event_date='31.10.2026',new_primary=0,new_secondary=0)
            c.execute("UPDATE probnik_result_notice_queue SET created_at='2026-10-31T01:00:00+00:00',status='blocked'")

    def tearDown(self):
        self.modules.stop(); self.env.stop(); self.tmp.cleanup()

    async def test_only_active_linked_parents_even_without_student_telegram(self):
        await parents.dispatch_pending(self.ctx)
        self.assertEqual({x.kwargs['chat_id'] for x in self.send.await_args_list},{101,102})
        self.assertIn('Вторичный балл: 0',self.send.await_args_list[0].kwargs['text'])
        self.assertIn('Первичный балл: 0',self.send.await_args_list[0].kwargs['text'])

    async def test_no_duplicates_after_correction(self):
        await parents.dispatch_pending(self.ctx)
        with sqlite3.connect(self.db) as c:c.execute('UPDATE probnik_results SET secondary_score=80')
        await parents.dispatch_pending(self.ctx)
        self.assertEqual(self.send.await_count,2)

    async def test_disabled_does_not_create_queue(self):
        with patch.dict(os.environ,{parents.FLAG:'0'}):await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()
        with sqlite3.connect(self.db) as c:self.assertFalse(c.execute("SELECT name FROM sqlite_master WHERE name='probnik_parent_notice_queue'").fetchall())

    async def test_cutoff_required_and_timezone_required(self):
        for value in ['', 'invalid','2026-10-31T00:00:00']:
            with patch.dict(os.environ,{parents.SINCE:value}):await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_historical_notice_not_replayed(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE probnik_result_notice_queue SET created_at='2026-10-30T23:00:00+00:00'")
        await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_ambiguous_student_not_sent(self):
        self.student=None
        await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_unlink_before_send_checked(self):
        calls=0
        def active():
            nonlocal calls
            calls+=1
            if calls==2:
                with sqlite3.connect(self.db) as c:c.execute('UPDATE parent_links SET active=0')
            return [self.student]
        self.live._all_active_students=active
        await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_one_failure_does_not_duplicate_successful_parent(self):
        async def send(**kw):
            if kw['chat_id']==101:raise RuntimeError('test')
        self.send.side_effect=send
        await parents.dispatch_pending(self.ctx)
        self.send.side_effect=None
        await parents.dispatch_pending(self.ctx)
        self.assertEqual([x.kwargs['chat_id'] for x in self.send.await_args_list].count(102),1)
        self.assertEqual([x.kwargs['chat_id'] for x in self.send.await_args_list].count(101),2)

    async def test_legacy_parent_schema(self):
        with sqlite3.connect(self.db) as c:c.execute('ALTER TABLE parent_links RENAME COLUMN parent_telegram_user_id TO telegram_user_id')
        await parents.dispatch_pending(self.ctx)
        self.assertEqual(self.send.await_count,2)

    async def test_no_parent_no_send(self):
        with sqlite3.connect(self.db) as c:c.execute('DELETE FROM parent_links')
        await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_missing_score_not_sent(self):
        with sqlite3.connect(self.db) as c:c.execute('UPDATE probnik_results SET primary_score=NULL,secondary_score=NULL')
        await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()

    async def test_student_flag_off_prevents_parent_delivery(self):
        with patch.dict(os.environ,{students.ENV_FLAG:'0'}):await parents.dispatch_pending(self.ctx)
        self.send.assert_not_awaited()
