"""Isolated runtime-behavior tests for the production grade-11 rewards adapter."""
import ast
import asyncio
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


class Grade11RewardSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=os.path.join(self.tmp.name,"students.db")
        self.zone=ZoneInfo("Europe/Moscow")
        self.month=datetime.now(self.zone).strftime("%Y-%m")
        self.user=(1,"Ученица",None,None,None,50001)
        with sqlite3.connect(self.path) as c:
            c.executescript("""
                CREATE TABLE weekly_trainer_catalog(
                    code TEXT PRIMARY KEY, title TEXT, start_param TEXT,
                    sort_order INTEGER, active INTEGER
                );
                CREATE TABLE ege11_trainer_focus(
                    code TEXT PRIMARY KEY,enabled INTEGER
                );
            """)
            for i,(code,title) in enumerate([
                ("trivial","Тривиальные"),
                ("oxideprops","Свойства оксидов"),
                ("hydroxides","Свойства гидроксидов"),
                ("middlesalts","Средние соли"),
                ("specialsalts","Комплексные соли"),
            ]):
                c.execute(
                    "INSERT INTO weekly_trainer_catalog VALUES(?,?,?,?,1)",
                    (code,title,code,i*10),
                )
                if code!="trivial":
                    c.execute(
                        "INSERT INTO ege11_trainer_focus VALUES(?,?)",
                        (code,1 if code in ("oxideprops","hydroxides") else 0),
                    )
                c.execute(
                    f"CREATE TABLE {code}_sessions("
                    "telegram_user_id INTEGER,total INTEGER,"
                    "correct INTEGER,finished_at TEXT)"
                )
        self.table_map={code:code+"_sessions" for code in
                        ("trivial","oxideprops","hydroxides","middlesalts","specialsalts")}
        self.legacy_finish=(datetime.now(self.zone)-timedelta(days=2)).isoformat()
        for _ in range(3):
            self.add_attempt("trivial",self.legacy_finish)
        self.add_attempt("oxideprops",self.legacy_finish)
        self.add_attempt("middlesalts",self.legacy_finish)

        rewards=types.ModuleType("kulek_rewards")
        rewards.TRAINER_TABLES=self.table_map.copy()
        rewards._CACHE={"foo":"bar"}
        rewards._RANKING_CACHE={"data":{"stale":True}}
        rewards._month_key=lambda month_key=None:month_key or self.month
        rewards._student_rows=lambda:[self.user]
        rewards._trainer_goals=lambda month,students:[
            {"code":"trivial","title":"Тривиальные","table":"trivial_sessions",
             "students":{1:{"sessions":3,"earned":True,"remaining":0}}},
            {"code":"oxideprops","title":"Свойства оксидов",
             "table":"oxideprops_sessions",
             "students":{1:{"sessions":1,"earned":False,"remaining":2}}},
        ]
        rewards.student_progress_snapshot=lambda uid,key=None:{
            "trainer_sessions":0,"month":key or self.month}
        rewards.student_monthly_report_text=lambda uid,key=None:"🧪 Тренажёры: <b>0</b> завершённых тренировок"
        rewards.parent_monthly_report_text=lambda uid,key=None:"🧪 Тренажёры: <b>0</b>\n• тренажёры — 0 завершённых тренировок"
        rewards.course_monthly_report_text=lambda key=None:"🧪 Завершено тренировок: <b>0</b>"

        webapp=types.ModuleType("ege_student_webapp")
        webapp._trainer_rows=lambda student:[]
        webapp._payload=lambda uid:{"trainers":webapp._trainer_rows(self.user),
                                   "month":{"trainer_sessions":0,
                                            "trainer_total":0,
                                            "trainer_correct":0}}

        cab=types.ModuleType("run_bot_live23")
        cab._admin_private=lambda update:True
        async def old_callback(update,context):
            value=update.callback_query.data
            if value.startswith("cab:e11:toggle:"):
                code=value.split(":")[-1]
                with sqlite3.connect(self.path) as c:
                    c.execute(
                        "UPDATE ege11_trainer_focus SET enabled=1-enabled WHERE code=?",
                        (code,),
                    )
        cab.cabinet_callback=old_callback

        tree=ast.parse(Path("run_bot_production.py").read_text(encoding="utf-8"))
        installer=next(node for node in tree.body
                       if isinstance(node,ast.FunctionDef)
                       and node.name=="install_ege11_rewards_and_stats_sync")
        compiled=compile(ast.Module(body=[installer],type_ignores=[]),
                         "run_bot_production.py","exec")
        globals_={"live90":types.SimpleNamespace(
            bot=types.SimpleNamespace(
                COREAPP_DB_PATH=self.path,TIMEZONE=self.zone))}
        exec(compiled,globals_)
        with patch.dict(sys.modules,{"kulek_rewards":rewards,
                                     "ege_student_webapp":webapp,
                                     "run_bot_live23":cab}):
            globals_["install_ege11_rewards_and_stats_sync"]()
        self.rewards=rewards
        self.webapp=webapp
        self.cab=cab

    def add_attempt(self,code,finished,total=10,correct=8):
        with sqlite3.connect(self.path) as c:
            c.execute(
                f"INSERT INTO {code}_sessions VALUES(?,?,?,?)",
                (50001,total,correct,finished),
            )

    def rows(self):
        return {r["code"]:r for r in
                self.rewards._trainer_goals(self.month,[self.user])}

    def toggle(self,code):
        update=types.SimpleNamespace(
            callback_query=types.SimpleNamespace(data="cab:e11:toggle:"+code))
        asyncio.run(self.cab.cabinet_callback(update,None))

    def test_month_history_and_legacy_credit(self):
        previous=f"{int(self.month[:4]):04d}-{int(self.month[-2:])-1:02d}" \
            if self.month[-2:]!="01" else f"{int(self.month[:4])-1:04d}-12"
        self.assertEqual(len(self.rewards._trainer_goals(previous,[self.user])),2)
        with sqlite3.connect(self.path) as c:
            legacy=c.execute(
                "SELECT code,sessions FROM ege11_reward_legacy_credits"
            ).fetchall()
            self.assertEqual(legacy,[("trivial",3)])
            self.assertEqual(c.execute(
                "SELECT COUNT(*) FROM trivial_sessions"
            ).fetchone()[0],3)
        goals=self.rows()
        self.assertTrue(goals["trivial"]["students"][1]["earned"])
        self.assertFalse(goals["oxideprops"]["students"][1]["earned"])
        self.assertNotIn("middlesalts",goals)
        self.assertNotIn("specialsalts",goals)

    def test_assignment_counters_and_student_statistics(self):
        with sqlite3.connect(self.path) as c:
            start=c.execute(
                "SELECT start_at FROM ege11_reward_config WHERE id=1"
            ).fetchone()[0]
        future=(datetime.fromisoformat(start)+timedelta(hours=1)).isoformat()
        for _ in range(3):
            self.add_attempt("oxideprops",future)
        goals=self.rows()
        self.assertEqual(goals["oxideprops"]["students"][1]["sessions"],3)
        self.assertTrue(goals["oxideprops"]["students"][1]["earned"])
        rows=self.webapp._trainer_rows(self.user)
        by_title={r["title"]:r for r in rows}
        self.assertEqual(by_title["Свойства оксидов"]["sessions"],4)
        self.assertEqual(by_title["Тривиальные"]["sessions"],3)
        self.assertEqual(
            self.webapp._payload(50001)["month"]["trainer_sessions"],
            len(rows)+4+3-2 if False else sum(x["sessions"] for x in rows),
        )
        self.assertEqual(
            self.rewards.student_progress_snapshot(1,self.month)["trainer_sessions"],
            sum(x["sessions"] for x in rows),
        )
        self.assertIn("<b>8</b>",self.rewards.student_monthly_report_text(1,self.month))
        self.assertIn("<b>8</b>",self.rewards.parent_monthly_report_text(1,self.month))
        self.assertIn("<b>8</b>",self.rewards.course_monthly_report_text(self.month))

    def test_topic_switch_keeps_credit_and_respects_assignment_dates(self):
        self.toggle("middlesalts")
        goals=self.rows()
        self.assertIn("middlesalts",goals)
        self.assertEqual(goals["middlesalts"]["students"][1]["sessions"],0)
        self.assertEqual(goals["middlesalts"]["students"][1]["remaining"],3)
        with sqlite3.connect(self.path) as c:
            enabled=c.execute(
                "SELECT enabled_at FROM ege11_reward_assignments"
                " WHERE code='middlesalts' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        future=(datetime.fromisoformat(enabled)+timedelta(hours=1)).isoformat()
        for _ in range(3):
            self.add_attempt("middlesalts",future)
        goals=self.rows()
        self.assertEqual(goals["middlesalts"]["students"][1]["sessions"],3)
        self.assertTrue(goals["middlesalts"]["students"][1]["earned"])
        self.toggle("middlesalts")
        self.assertTrue(self.rows()["middlesalts"]["students"][1]["earned"])
        # An unearned deactivated topic must not remain an obligation.
        self.toggle("specialsalts")
        self.toggle("specialsalts")
        self.assertNotIn("specialsalts",self.rows())
        # Legacy credit for trivia survives all teacher changes.
        self.assertTrue(self.rows()["trivial"]["students"][1]["earned"])


if __name__=="__main__":
    unittest.main()
