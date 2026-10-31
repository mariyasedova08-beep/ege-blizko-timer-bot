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

    def push(self, old_primary=None, old_secondary=None,
             new_primary=25, new_secondary=72):
        return notice.queue_score_change(
            self.conn, student_name="Тестовый ученик",
            event_name="Пробник", event_date="31.10.2026",
            old_primary=old_primary, old_secondary=old_secondary,
            new_primary=new_primary, new_secondary=new_secondary,
        )

    def count(self):
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

    def test_unchanged_score_not_queued(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertFalse(self.push(old_primary=25, old_secondary=72))
        self.assertEqual(self.count(), 0)

    def test_score_change_queued(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertTrue(self.push(old_primary=25, old_secondary=72,
                                      new_primary=26, new_secondary=74))
        self.assertEqual(self.count(), 1)

    def test_tasks_only_without_score_not_queued(self):
        with patch.dict(os.environ, {notice.ENV_FLAG: "1"}):
            self.assertFalse(self.push(new_primary=None, new_secondary=None))
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
