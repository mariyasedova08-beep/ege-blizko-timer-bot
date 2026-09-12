"""Payment schedule tests use a temporary database and block network access."""
import copy
import os
import socket
import sqlite3
import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class PaymentScheduleTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ege-payments-")
        cls.env = patch.dict(os.environ, {"COREAPP_DB_PATH": cls.tmp.name + "/payments.sqlite3"})
        cls.env.start()
        cls.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network disabled"))
        cls.network.start()
        import run_bot_live90
        cls.app = run_bot_live90
        cls.schedule = run_bot_live90.payment_schedule
        cls.db_patch = patch.object(cls.app.bot, "COREAPP_DB_PATH", cls.tmp.name + "/payments.sqlite3")
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        cls.network.stop()
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.clock = patch.object(self.app.bot, "today_moscow", return_value=date(2026, 9, 12))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.schedule.ensure_payment_plans()
        with sqlite3.connect(self.app.bot.COREAPP_DB_PATH) as conn:
            for table in ("payment_plans", "payment_coverage", "payment_students"):
                conn.execute("DELETE FROM " + table)
            conn.execute("UPDATE payment_import_status SET imported_at=NULL,student_count=0,coverage_count=0")
        periods = self.app.live85.PAYMENT_PERIODS
        self.data = [
            {"source_key": "monthly", "display_name": "Test Monthly", "monthly_amount": 13200,
             "coverage": {"2026-09": 13200}},
            {"source_key": "quarterly", "display_name": "Test Quarterly", "monthly_amount": 12000,
             "coverage": {p: 12000 for p, _label in periods[:3]}},
            {"source_key": "prepaid", "display_name": "Test Prepaid", "monthly_amount": 12000,
             "coverage": {p: 12000 for p, _label in periods}},
        ]

    def import_data(self, data=None):
        return self.app.live85.save_payment_snapshot(data or self.data, "test.xlsx")

    def rows(self, as_of=None):
        return {row["name"]: row for row in self.schedule.schedule_rows(as_of)}

    def db_snapshot(self):
        with sqlite3.connect(self.app.bot.COREAPP_DB_PATH) as conn:
            return tuple(conn.iterdump())

    async def test_initial_cadences_amounts_and_full_payment_exclusion(self):
        self.import_data()
        rows = self.rows()
        self.assertEqual(Counter(r["cadence"] for r in rows.values()), {"monthly":1,"quarterly":1,"prepaid":1})
        self.assertEqual(rows["Test Monthly"]["next_invoice"]["remaining_cents"], 1320000)
        self.assertEqual(rows["Test Monthly"]["next_invoice"]["due_date"], date(2026,10,7))
        self.assertEqual(rows["Test Quarterly"]["next_invoice"]["remaining_cents"], 3600000)
        self.assertEqual(rows["Test Quarterly"]["next_invoice"]["due_date"], date(2026,12,7))
        self.assertIsNone(rows["Test Prepaid"]["next_invoice"])
        self.assertEqual(rows["Test Prepaid"]["overdue_cents"], 0)

    async def test_due_date_inclusive_and_quarterly_not_monthly_debt(self):
        self.import_data()
        self.assertEqual(self.rows(date(2026,10,7))["Test Monthly"]["overdue_cents"], 0)
        self.assertEqual(self.rows(date(2026,10,8))["Test Monthly"]["overdue_cents"], 1320000)
        self.assertEqual(self.rows(date(2026,11,8))["Test Quarterly"]["overdue_cents"], 0)
        self.assertEqual(self.rows(date(2026,12,7))["Test Quarterly"]["overdue_cents"], 0)
        self.assertEqual(self.rows(date(2026,12,8))["Test Quarterly"]["overdue_cents"], 3600000)

    async def test_calendar_month_end_and_year_rollover(self):
        for period, notice, due in [
            ("2026-10", date(2026,9,27), date(2026,10,7)),
            ("2026-11", date(2026,10,28), date(2026,11,7)),
            ("2026-12", date(2026,11,27), date(2026,12,7)),
            ("2027-01", date(2026,12,28), date(2027,1,7)),
            ("2027-02", date(2027,1,28), date(2027,2,7)),
            ("2027-03", date(2027,2,25), date(2027,3,7)),
        ]:
            self.assertEqual(self.schedule.period_dates(period), (notice,due))

    async def test_cadence_persists_after_accumulated_monthly_payments(self):
        self.import_data()
        updated = copy.deepcopy(self.data)
        updated[0]["coverage"].update({"2026-10":13200,"2026-11":13200})
        updated[1]["coverage"].update({"2026-12":12000,"2027-01":12000,"2027-02":12000})
        with patch.object(self.app.bot,"today_moscow",return_value=date(2026,12,1)):
            self.import_data(updated)
        rows = self.rows(date(2026,12,1))
        self.assertEqual(rows["Test Monthly"]["cadence"], "monthly")
        self.assertEqual(rows["Test Monthly"]["next_invoice"]["remaining_cents"], 1320000)
        self.assertEqual(rows["Test Quarterly"]["cadence"], "quarterly")
        self.assertEqual(rows["Test Quarterly"]["next_invoice"]["due_date"], date(2027,3,7))

    async def test_prepaid_stays_excluded_after_incomplete_refresh(self):
        self.import_data()
        updated = copy.deepcopy(self.data)
        updated[2]["coverage"] = {"2026-09":12000}
        self.import_data(updated)
        row = self.rows(date(2027,4,10))["Test Prepaid"]
        self.assertIsNone(row["next_invoice"])
        self.assertEqual(row["overdue_cents"],0)
        self.assertIn("Напоминание не требуется", self.schedule.reminder_draft(row["id"]))

    async def test_partial_payment_and_cents(self):
        self.import_data()
        updated = copy.deepcopy(self.data)
        updated[0]["coverage"]["2026-10"] = 6000.25
        updated[1]["coverage"]["2026-12"] = 12000
        self.import_data(updated)
        rows = self.rows(date(2026,12,8))
        self.assertEqual(rows["Test Monthly"]["next_invoice"]["remaining_cents"],719975)
        self.assertEqual(rows["Test Quarterly"]["next_invoice"]["remaining_cents"],2400000)
        self.assertEqual(self.schedule.money(719975),"7 199,75 ₽")

    async def test_ambiguous_or_late_initial_snapshot_needs_review(self):
        student = copy.deepcopy(self.data[0])
        student["coverage"]["2026-11"] = 13200
        periods = self.app.live85.PAYMENT_PERIODS
        self.assertEqual(self.schedule.infer_initial_cadence(student,periods,date(2026,9,12)),"review")
        self.assertEqual(self.schedule.infer_initial_cadence(self.data[1],periods,date(2026,11,1)),"review")

    async def test_drafts_do_not_write_data_or_send_messages(self):
        self.import_data()
        rows = self.rows()
        before = self.db_snapshot()
        sid = rows["Test Quarterly"]["id"]
        query = SimpleNamespace(data=f"cab:payments:draft:{sid}",answer=AsyncMock(),edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query,effective_chat=SimpleNamespace(type="private"))
        context = SimpleNamespace(user_data={},bot=SimpleNamespace(send_message=AsyncMock()))
        with patch.object(self.app.bot,"user_is_admin",return_value=True):
            await self.app.live23.cabinet_callback(update,context)
        text = query.edit_message_text.await_args.args[0]
        self.assertIn("36 000 ₽",text)
        self.assertIn("07.12.2026",text)
        self.assertIn("27.11.2026",text)
        context.bot.send_message.assert_not_awaited()
        self.assertEqual(self.db_snapshot(),before)

    async def test_private_admin_access_only_and_alert_hook_preserved(self):
        self.import_data()
        query = SimpleNamespace(data="cab:payments",answer=AsyncMock(),edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query,effective_chat=SimpleNamespace(type="private"))
        context = SimpleNamespace(user_data={})
        with patch.object(self.app.bot,"user_is_admin",return_value=False):
            await self.app.live23.cabinet_callback(update,context)
        query.edit_message_text.assert_not_awaited()
        self.assertIs(self.app.bot.Application.builder()._post_init,self.app.live79.live70._post_init)

    async def test_actual_workbook_if_available(self):
        path = Path(__file__).parent.parent / "upload" / "Доход.xlsx"
        if not path.exists():
            self.skipTest("Private source workbook is not committed")
        students = self.app.live85.parse_payment_workbook(path.read_bytes())
        self.import_data(students)
        rows = self.schedule.schedule_rows(date(2026,9,12))
        self.assertEqual(len(rows),13)
        self.assertEqual(Counter(row["cadence"] for row in rows),{"monthly":10,"quarterly":2,"prepaid":1})
        self.assertEqual(sum(row["next_invoice"]["remaining_cents"] for row in rows if row["cadence"]=="monthly"),13134000)
        self.assertEqual(sum(row["next_invoice"]["remaining_cents"] for row in rows if row["cadence"]=="quarterly"),7200000)
        self.assertEqual(sum(row["overdue_cents"] for row in rows),0)
        self.assertIn("131 340 ₽",self.schedule.summary_text())
        print("Source workbook verified: 13 students; monthly=10; quarterly=2; prepaid=1; no overdue payments")


if __name__ == "__main__":
    unittest.main()
