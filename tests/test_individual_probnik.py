import os
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch
import individual_probnik as ind


def match(name, rows):
    hits=[row for row in rows if ind.norm(name) in {ind.norm(row[1]),ind.norm(row[2])} or ind.norm(name) in ind.norm(row[1]) or ind.norm(row[1]) in ind.norm(name)]
    return hits[0] if len(hits)==1 else None


def payload(name='АЛИНА', status='Опубликовано', primary=25, secondary=70):
    return {'spreadsheet_title':'ЕГЭ','sheets':[{'student_name':name,'sheet_name':name,'results':[{
        'event_name':'ПРОБНИК №1','event_date':'31.10.2026','primary_score':primary,
        'secondary_score':secondary,'publication_status':status,'tasks':{'1':1}}]}]}


class RoutingTests(unittest.TestCase):
    individuals=[(1,'Алина',101),(2,'Оля',102)]
    def split(self,p,regular=(),individuals=None):
        return ind.split_payload(p,self.individuals if individuals is None else individuals,regular,match)

    def test_individual_removed_from_group_payload(self):
        groups,rows=self.split(payload());self.assertEqual(groups['sheets'],[]);self.assertEqual(rows[0][0],1)
        self.assertEqual(groups['spreadsheet_title'],'ЕГЭ')
    def test_group_unchanged(self):
        p=payload('Степан');groups,rows=self.split(p);self.assertEqual(groups,p);self.assertEqual(rows,[])
    def test_mixed_payload(self):
        p=payload();p['sheets']+=payload('Степан')['sheets'];groups,rows=self.split(p)
        self.assertEqual([x['student_name'] for x in groups['sheets']],['Степан']);self.assertEqual(len(rows),1)
    def test_draft_and_missing_status_never_leave_individual_route(self):
        for status in ['Черновик','Не проверено','',None]:
            groups,rows=self.split(payload(status=status));self.assertFalse(groups['sheets']);self.assertFalse(rows)
    def test_duplicate_individual_name_blocked(self):
        with self.assertRaises(ValueError):self.split(payload(),individuals=[(1,'Алина',101),(2,'АЛИНА',102)])
    def test_group_name_collision_blocked_even_multiple_regular_matches(self):
        for regular in [[(9,'Алина','Алина','','',999)],[(9,'Алина','Алина','','',999),(10,'Алина','Алина','','',998)]]:
            with self.assertRaises(ValueError):self.split(payload(),regular=regular)
    def test_group_telegram_collision_blocked(self):
        with self.assertRaises(ValueError):self.split(payload(),regular=[(9,'Другое имя','Другое имя','','',101)])
    def test_partial_individual_name_rejected_not_routed_to_group(self):
        with self.assertRaises(ValueError):self.split(payload(),individuals=[(1,'Алина Иванова',101)])
    def test_invalid_scores_rejected(self):
        for score in ['nan','inf',-1,'неизвестно']:
            with self.assertRaises(ValueError):self.split(payload(primary=score))
    def test_invalid_date_rejected(self):
        p=payload();p['sheets'][0]['results'][0]['event_date']='31.02.2026'
        with self.assertRaises(ValueError):self.split(p)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=self.tmp.name+'/test.db'
        self.env=patch.dict(os.environ,{ind.FLAG:'1'});self.env.start()
        self.previous=ind._live
        ind._live=types.SimpleNamespace(bot=types.SimpleNamespace(COREAPP_DB_PATH=self.db))
        self.sender=AsyncMock();self.ctx=types.SimpleNamespace(bot=types.SimpleNamespace(send_message=self.sender))
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE individual_students(id INTEGER,display_name TEXT,telegram_user_id INTEGER,active INTEGER)')
            c.executemany('INSERT INTO individual_students VALUES(?,?,?,1)',[(1,'Алина',101),(2,'Оля',102)])
            c.execute('CREATE TABLE students(id INTEGER,display_name TEXT,user_name TEXT,user_email TEXT,coreapp_user_id TEXT,telegram_user_id INTEGER,active INTEGER)')
            c.execute("INSERT INTO students VALUES(1,'Степан','Степан','','',999,1)")
            c.execute('CREATE TABLE parent_links(student_id INTEGER,parent_telegram_user_id INTEGER,active INTEGER)')
            c.execute('INSERT INTO parent_links VALUES(1,555,1)')
            _,rows=ind.split_payload(payload(),[(1,'Алина',101),(2,'Оля',102)],[],match)
            ind.save_individual_results(c,rows)
    def tearDown(self):
        ind._live=self.previous;self.env.stop();self.tmp.cleanup()
    def save(self,p):
        _,rows=ind.split_payload(p,[(1,'Алина',101),(2,'Оля',102)],[],match)
        with sqlite3.connect(self.db) as c:ind.save_individual_results(c,rows)
    async def test_only_individual_receives_even_if_ids_collide_with_group_and_parent(self):
        await ind.dispatch_pending(self.ctx)
        self.sender.assert_awaited_once();self.assertEqual(self.sender.await_args.kwargs['chat_id'],101)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM students').fetchone()[0],1)
    async def test_repeat_sync_and_correction_do_not_resend(self):
        await ind.dispatch_pending(self.ctx);self.save(payload(secondary=80));await ind.dispatch_pending(self.ctx)
        self.sender.assert_awaited_once()
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT secondary_score FROM individual_probnik_results').fetchone()[0],80)
    async def test_zero_scores_delivered(self):
        self.save(payload(primary=0,secondary=0));await ind.dispatch_pending(self.ctx)
        self.assertIn('Вторичный балл: 0',self.sender.await_args.kwargs['text'])
    async def test_individuals_only_see_own_results(self):
        self.save(payload('ОЛЯ',secondary=90))
        with sqlite3.connect(self.db) as c:
            a=ind.results_text(c,1);o=ind.results_text(c,2)
        self.assertIn('70',a);self.assertNotIn('90',a);self.assertIn('90',o);self.assertNotIn('70',o)
    async def test_no_telegram_remains_pending_then_sends_after_link(self):
        with sqlite3.connect(self.db) as c:c.execute('UPDATE individual_students SET telegram_user_id=NULL WHERE id=1')
        await ind.dispatch_pending(self.ctx);self.sender.assert_not_awaited()
        with sqlite3.connect(self.db) as c:c.execute('UPDATE individual_students SET telegram_user_id=101 WHERE id=1')
        await ind.dispatch_pending(self.ctx);self.sender.assert_awaited_once()
    async def test_inactive_not_sent(self):
        with sqlite3.connect(self.db) as c:c.execute('UPDATE individual_students SET active=0 WHERE id=1')
        await ind.dispatch_pending(self.ctx);self.sender.assert_not_awaited()
    async def test_duplicate_group_telegram_not_sent(self):
        with sqlite3.connect(self.db) as c:c.execute('UPDATE students SET telegram_user_id=101')
        await ind.dispatch_pending(self.ctx);self.sender.assert_not_awaited()
    async def test_retry_after_failure(self):
        self.sender.side_effect=RuntimeError('test');await ind.dispatch_pending(self.ctx)
        self.sender.side_effect=None;await ind.dispatch_pending(self.ctx);self.assertEqual(self.sender.await_count,2)
    async def test_disabled_no_send(self):
        with patch.dict(os.environ,{ind.FLAG:'0'}):await ind.dispatch_pending(self.ctx)
        self.sender.assert_not_awaited()
    async def test_overlapping_ticks_not_duplicated(self):
        import asyncio
        entered=asyncio.Event();release=asyncio.Event()
        async def slow(**kw):entered.set();await release.wait()
        self.sender.side_effect=slow
        first=asyncio.create_task(ind.dispatch_pending(self.ctx));await entered.wait()
        second=asyncio.create_task(ind.dispatch_pending(self.ctx));await asyncio.sleep(0);release.set()
        await asyncio.gather(first,second);self.sender.assert_awaited_once()
    async def test_tasks_only_no_notification(self):
        with sqlite3.connect(self.db) as c:
            c.execute('DELETE FROM individual_probnik_results');c.execute('DELETE FROM individual_probnik_notices')
        self.save(payload(primary=None,secondary=None))
        await ind.dispatch_pending(self.ctx);self.sender.assert_not_awaited()
    async def test_empty_sync_preserves_results(self):
        with sqlite3.connect(self.db) as c:
            ind.save_individual_results(c,[])
            self.assertIn('70',ind.results_text(c,1))

if __name__=='__main__':unittest.main()

class InstalledIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=self.tmp.name+'/integration.db'
        self.previous=ind._live
        self.env=patch.dict(os.environ,{ind.FLAG:'1'});self.env.start()
        self.telegram=patch.dict('sys.modules',{'telegram':types.SimpleNamespace(
            ReplyKeyboardMarkup=lambda *a,**k:types.SimpleNamespace(rows=a[0]),
            InlineKeyboardButton=lambda *a,**k:types.SimpleNamespace(text=a[0],**k),
            InlineKeyboardMarkup=lambda rows:rows)})
        self.telegram.start()
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE individual_students(id,display_name,telegram_user_id,active)')
            c.executemany('INSERT INTO individual_students VALUES(?,?,?,1)',[(1,'Алина',101),(2,'Оля',102)])
            c.execute('CREATE TABLE students(id,display_name,user_name,user_email,coreapp_user_id,telegram_user_id,active)')
            c.execute('CREATE TABLE probnik_sync_status(id,last_rows,last_students)');c.execute('INSERT INTO probnik_sync_status VALUES(1,0,0)')
        self.base_payloads=[]
        def base_sync(p):
            self.base_payloads.append(p)
            return len(p['sheets']),len(p['sheets'])
        def individual(uid):
            with sqlite3.connect(self.db) as c:return c.execute('SELECT id,display_name,telegram_user_id FROM individual_students WHERE telegram_user_id=? AND active=1',(uid,)).fetchone()
        self.live=types.SimpleNamespace(bot=types.SimpleNamespace(COREAPP_DB_PATH=self.db),
            live10=types.SimpleNamespace(save_probnik_sync=base_sync),
            live56=types.SimpleNamespace(unique_probnik_student_match=match),
            live7=types.SimpleNamespace(start_router=AsyncMock(),student_text_router=AsyncMock()),
            live23=types.SimpleNamespace(cabinet_callback=AsyncMock(),_admin_private=lambda u:False),
            _individual_by_telegram=individual)
        self.old_start=self.live.live7.start_router;self.old_text=self.live.live7.student_text_router
        self.live.live24=types.SimpleNamespace(live10=self.live.live10)
        ind.install(self.live)
    def tearDown(self):
        ind._live=self.previous;self.telegram.stop();self.env.stop();self.tmp.cleanup()
    def update(self,uid,text):
        message=types.SimpleNamespace(text=text,reply_text=AsyncMock())
        return types.SimpleNamespace(effective_chat=types.SimpleNamespace(type='private'),
            effective_user=types.SimpleNamespace(id=uid),effective_message=message)
    async def test_full_sync_routes_and_aggregates_counts(self):
        p=payload();p['sheets']+=payload('Степан')['sheets']
        self.assertEqual(self.live.live10.save_probnik_sync(p),(2,2))
        self.assertEqual([s['student_name'] for s in self.base_payloads[0]['sheets']],['Степан'])
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT last_rows,last_students FROM probnik_sync_status').fetchone(),(2,2))
    async def test_start_individual_gets_both_buttons(self):
        u=self.update(101,'/start');await self.live.live7.start_router(u,types.SimpleNamespace(args=[]))
        self.assertEqual(u.effective_message.reply_text.await_args.kwargs['reply_markup'].rows,[['🧪 Тренажёры'],['📝 Пробники']])
        self.old_start.assert_not_awaited()
    async def test_normal_student_router_preserved(self):
        u=self.update(999,'📝 Пробники');await self.live.live7.student_text_router(u,types.SimpleNamespace())
        self.old_text.assert_awaited_once();u.effective_message.reply_text.assert_not_awaited()
    async def test_ui_uses_requesting_telegram_identity(self):
        self.live.live10.save_probnik_sync(payload());self.live.live10.save_probnik_sync(payload('ОЛЯ',secondary=90))
        u=self.update(102,'📝 Пробники');await self.live.live7.student_text_router(u,types.SimpleNamespace())
        text=u.effective_message.reply_text.await_args.args[0]
        self.assertIn('90',text);self.assertNotIn('70',text)
    async def test_install_idempotent(self):
        first=self.live.live10.save_probnik_sync;ind.install(self.live)
        self.assertIs(first,self.live.live10.save_probnik_sync)
    async def test_validation_precedes_all_group_writes(self):
        p=payload(primary='nan');p['sheets']+=payload('Степан')['sheets']
        with self.assertRaises(ValueError):self.live.live10.save_probnik_sync(p)
        self.assertFalse(self.base_payloads)
