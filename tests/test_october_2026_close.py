import asyncio
from datetime import datetime, date
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
m=load('october',ROOT/'october_2026_close.py')
p=load('patcher',ROOT/'deploy/october_close_patch.py')

class CalendarTests(unittest.TestCase):
    def test_no_october_close_november_1_to_4(self):
        for day in range(1,5):
            self.assertIsNone(m.scheduled_close_key(datetime(2026,11,day,23,59,tzinfo=m.TZ)))
    def test_close_november_5_at_existing_hour_and_catchup(self):
        self.assertIsNone(m.scheduled_close_key(datetime(2026,11,5,8,59,tzinfo=m.TZ)))
        for day in (5,6,30):
            self.assertEqual(m.scheduled_close_key(datetime(2026,11,day,9,tzinfo=m.TZ)),m.MONTH)
    def test_other_months_unchanged(self):
        self.assertEqual(m.scheduled_close_key(datetime(2026,10,1,9,tzinfo=m.TZ)),'2026-09')
        self.assertEqual(m.scheduled_close_key(datetime(2026,12,1,9,tzinfo=m.TZ)),'2026-11')
        self.assertIsNone(m.scheduled_close_key(datetime(2026,12,5,9,tzinfo=m.TZ)))
    def test_manual_awards_blocked_until_result_date(self):
        self.assertTrue(m.blocked(m.MONTH,datetime(2026,11,4,23,59,59,tzinfo=m.TZ)))
        self.assertFalse(m.blocked(m.MONTH,m.CLOSE_AT))
        self.assertFalse(m.blocked('2026-09',datetime(2026,11,1,tzinfo=m.TZ)))
    def test_message_dates_and_length(self):
        self.assertLess(len(m.MESSAGE),4096)
        for text in ('31 октября','4 ноября','5 ноября','7 ноября','61 балла','80%','3 тренировки'):
            self.assertIn(text,m.MESSAGE)

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'db.sqlite'
        with sqlite3.connect(self.db) as c:
            c.executescript(m.SCHEMA+'''
CREATE TABLE homework_submissions(received_at,user_id,user_email,lesson_id,lesson_name,correct_count,total_count);
CREATE TABLE students(id,active,course_id,telegram_user_id);
CREATE TABLE probnik_results(event_date,secondary_score);
CREATE TABLE weekly_trainer_catalog(code,title);
CREATE TABLE acid_sessions(telegram_user_id,finished_at,total,correct);
CREATE TABLE ege11_trainer_assignment_periods(code,starts_at,ends_at);
''')
            c.execute("INSERT INTO ege11_trainer_assignment_periods VALUES('acid','2026-10-01T00:00:00+03:00',NULL)")
        self.student=(1,None,'Student','s@example.org','core',101)
        self.kr=types.SimpleNamespace(bot=types.SimpleNamespace(COREAPP_DB_PATH=str(self.db)),
            _parse_dt=lambda v:datetime.fromisoformat(v),
            _student_matches_submission=lambda s,u,e:u=='core',
            _final_catalog=lambda:[{'lesson_id':'f1','title':'Final 1'},{'lesson_id':'f2','title':'Final 2'}],
            TRAINER_TABLES={'acid':'acid_sessions'},MONTHLY_EXCLUDED_TRAINERS={'decomposition'})
        self.kr.deadlines=types.SimpleNamespace(_course_dates=lambda:(date(2026,10,28),),
            due_lesson_for_source=lambda d:(date(2026,11,2),2),
            _explicit_match=lambda lid,name,*args:lid=='hw1')
        self.card={'id':1,'monthly_payment':True,'categories':{
            'trainers':{'items':[{'code':'acid','title':'Acids','sessions':2}]},
            'probnik':{'items':[{'event':'October exam','date':'31.10.2026','score':61}]}}}
    def insert(self,sql,values=()):
        with sqlite3.connect(self.db) as c:c.execute(sql,values)
    def test_grace_includes_november_4_excludes_november_5(self):
        self.insert('INSERT INTO homework_submissions VALUES(?,?,?,?,?,?,?)',('2026-11-04T23:59:59+03:00','core','s@example.org','hw1','HW',1,1))
        self.assertTrue(m.conditions(self.kr,self.student,self.card)[0]['done'])
        self.insert('DELETE FROM homework_submissions')
        self.insert('INSERT INTO homework_submissions VALUES(?,?,?,?,?,?,?)',('2026-11-05T00:00:00+03:00','core','s@example.org','hw1','HW',1,1))
        self.assertFalse(m.conditions(self.kr,self.student,self.card)[0]['done'])
    def test_final_late_improvement_and_november_only_task_excluded(self):
        for stamp,lid,correct in [('2026-10-20T12:00:00+03:00','f1',7),('2026-11-04T23:00:00+03:00','f1',8),('2026-11-01T12:00:00+03:00','f2',10)]:
            self.insert('INSERT INTO homework_submissions VALUES(?,?,?,?,?,?,?)',(stamp,'core','s@example.org',lid,lid,correct,10))
        final=m.conditions(self.kr,self.student,self.card)[1]
        self.assertEqual((final['earned'],final['total']),(1,1))
    def test_training_grace_respects_assignment_interval_and_cutoff(self):
        self.insert('INSERT INTO acid_sessions VALUES(?,?,?,?)',(101,'2026-11-04T23:59:59+03:00',10,10))
        self.assertTrue(m.conditions(self.kr,self.student,self.card)[2]['done'])
        self.insert("UPDATE ege11_trainer_assignment_periods SET ends_at='2026-11-01T00:00:00+03:00'")
        self.assertFalse(m.conditions(self.kr,self.student,self.card)[2]['done'])
    def test_missing_october31_exam_cannot_qualify(self):
        self.card['categories']['probnik']['items']=[]
        self.assertFalse(m.conditions(self.kr,self.student,self.card)[3]['done'])
    def test_exam_threshold_61_and_nonmonthly_payment(self):
        self.card['categories']['probnik']['items'][0]['score']=60
        self.assertFalse(m.conditions(self.kr,self.student,self.card)[3]['done'])
        self.card['monthly_payment']=False
        self.assertFalse(m.status_from_card(self.kr,self.student,self.card)['eligible'])
    def test_send_once_restart_no_duplicates(self):
        m._queue(self.kr,m.NOTICE_KEY,'student',101)
        bot=types.SimpleNamespace(send_message=AsyncMock(return_value=types.SimpleNamespace(message_id=7)))
        ctx=types.SimpleNamespace(bot=bot)
        asyncio.run(m._send_once(self.kr,ctx,m.NOTICE_KEY,'student',101,'text'))
        asyncio.run(m._send_once(self.kr,ctx,m.NOTICE_KEY,'student',101,'text'))
        self.assertEqual(bot.send_message.await_count,1)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT status,message_id FROM october_2026_deliveries').fetchone(),('sent',7))
    def test_ambiguous_failure_not_retried(self):
        m._queue(self.kr,m.NOTICE_KEY,'student',101)
        ctx=types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock(side_effect=TimeoutError)))
        for _ in range(2):asyncio.run(m._send_once(self.kr,ctx,m.NOTICE_KEY,'student',101,'text'))
        self.assertEqual(ctx.bot.send_message.await_count,1)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT status FROM october_2026_deliveries').fetchone()[0],'uncertain')
    def test_no_delivery_before_notice_time(self):
        with patch.object(m,'now',return_value=datetime(2026,10,27,18,59,tzinfo=m.TZ)):
            ctx=types.SimpleNamespace(bot=types.SimpleNamespace(send_message=AsyncMock()))
            asyncio.run(m.campaign_tick(self.kr,ctx));ctx.bot.send_message.assert_not_awaited()
    def test_readiness_requires_imported_exam(self):
        self.assertFalse(m.probnik_ready(self.kr))
        self.insert("INSERT INTO probnik_results VALUES('31.10.2026',61)")
        self.assertTrue(m.probnik_ready(self.kr))

class PatchTests(unittest.TestCase):
    def test_scoped_patch_idempotent(self):
        source=('async def monthly_close_tick(context):\n'+p.HEADER+'    pass\n\n'
                +'async def breakthrough_prompt_tick(context):\n'+p.HEADER+'    pass\n\n'
                +'def install():\n'+p.INSTALL)
        out=p.transform(source.encode())
        self.assertEqual(out,p.transform(out))
        self.assertEqual(out.count(p.REPLACEMENT.encode()),2)
        self.assertIn(p.NEW_INSTALL.encode(),out)
    def test_unknown_anchor_rejected(self):
        source=('async def monthly_close_tick(context):\n'+p.HEADER.replace('time(9, 0)','time(8, 0)')+'    pass\n\n'
                +'async def breakthrough_prompt_tick(context):\n'+p.HEADER+'    pass\n\n'
                +'def install():\n'+p.INSTALL)
        with self.assertRaises(ValueError):p.transform(source.encode())

import sys
from unittest.mock import Mock

class WrapperTests(unittest.TestCase):
    def fake(self):
        kr=types.SimpleNamespace(SEPTEMBER_DISCOUNT_KEY='2026-09',_CACHE={},
            _month_key=lambda key=None:key or '2026-11',
            month_payload=Mock(return_value={'students':[]}),_student_rows=lambda:[],
            discount_status=Mock(return_value={'legacy':True}),
            active_discount_status=Mock(return_value=None),_discount_cutoff=lambda key:None,
            choose_student_of_month=Mock(return_value={'ok':True}),
            choose_breakthrough=Mock(return_value={'ok':True}),draw_discount=Mock(return_value={'ok':True}),
            freeze_discount_pool=Mock(return_value={'ok':True}),
            announce_breakthrough_course=AsyncMock(),discount_notice_text=Mock(return_value='legacy'),
            discount_pool_text=Mock(return_value='legacy'),discount_draw_tick=AsyncMock(),
            bot=types.SimpleNamespace(get_admin_id=lambda:0))
        kr.live79=types.SimpleNamespace(live23=types.SimpleNamespace(cabinet_callback=AsyncMock(),_admin_private=lambda u:True))
        return kr
    def test_october_manual_actions_blocked_and_other_month_preserved(self):
        kr=self.fake();old=kr.choose_student_of_month
        with patch.dict(sys.modules,{'kulek_rewards':kr}),patch.object(m,'_INSTALLED',False),patch.object(m,'now',return_value=datetime(2026,11,1,12,tzinfo=m.TZ)):
            m.install()
            for name in ('choose_student_of_month','choose_breakthrough','draw_discount','freeze_discount_pool'):
                self.assertFalse(getattr(kr,name)(m.MONTH)['ok'])
            self.assertTrue(kr.choose_student_of_month('2026-09')['ok'])
            old.assert_called_once_with('2026-09')
            query=types.SimpleNamespace(data='cab:kulek:breakthroughpick:2026-10:1',answer=AsyncMock())
            asyncio.run(kr.live79.live23.cabinet_callback(types.SimpleNamespace(callback_query=query),None))
            query.answer.assert_awaited_once()
            self.assertTrue(query.answer.await_args.kwargs['show_alert'])
    def test_only_october_payload_is_enriched_not_original_metrics(self):
        kr=self.fake()
        card={'id':1,'categories':{'homework':{'earned':0,'total':1}},'draw_eligible':False}
        kr.month_payload=Mock(return_value={'students':[card],'eligible_draw_count':0})
        kr._student_rows=lambda:[(1,None,None,None,None,101)]
        with patch.dict(sys.modules,{'kulek_rewards':kr}),patch.object(m,'_INSTALLED',False),patch.object(m,'status_from_card',return_value={'eligible':True}):
            m.install()
            result=kr.month_payload('2026-10',force=True,with_breakthrough=False)
            self.assertEqual(result['students'][0]['categories']['homework']['earned'],0)
            self.assertEqual(result['eligible_draw_count'],1)

class ScheduledDeliveryTests(unittest.TestCase):
    setUp = DatabaseTests.setUp
    # Reuse only setUp; avoid duplicating inherited regression methods.
    def test_due_time_sends_one_group_and_thirteen_private_messages_once(self):
        with sqlite3.connect(self.db) as c:
            c.executemany('INSERT INTO students VALUES(?,1,?,?)',[(u,m.COURSE,u) for u in range(101,114)])
            c.executemany('INSERT INTO october_2026_config VALUES(?,?)',[('enabled','1'),('chat_id','-100123'),('thread_id','7')])
        m._queue(self.kr,m.NOTICE_KEY,'course',-100123)
        for u in range(101,114):m._queue(self.kr,m.NOTICE_KEY,'student',u)
        bot=types.SimpleNamespace(send_message=AsyncMock(return_value=types.SimpleNamespace(message_id=7)),
            get_chat=AsyncMock(return_value=types.SimpleNamespace(type='supergroup')),
            get_chat_member=AsyncMock(return_value=types.SimpleNamespace(status='member')))
        with patch.object(m,'now',return_value=m.NOTICE_AT):
            for _ in range(2):asyncio.run(m.campaign_tick(self.kr,types.SimpleNamespace(bot=bot)))
        self.assertEqual(bot.send_message.await_count,14)
        group=[call for call in bot.send_message.await_args_list if call.kwargs['chat_id']==-100123]
        self.assertEqual(len(group),1);self.assertEqual(group[0].kwargs['message_thread_id'],7)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute("SELECT count(*) FROM october_2026_deliveries WHERE status='sent'").fetchone()[0],14)

if __name__=='__main__':unittest.main()
