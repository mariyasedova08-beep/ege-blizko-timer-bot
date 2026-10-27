import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
m = load('snapshot_test', ROOT/'cabinet_schedule_snapshot.py')
p = load('snapshot_patcher', ROOT/'deploy/cabinet_snapshot_patch.py')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        self.dates = (date(2026,10,5), date(2026,10,7))
        self.transfer = types.ModuleType('ege11_lesson_transfer')
        def effective():
            self.calls += 1
            return tuple(self.dates)
        self.transfer._effective_dates = effective
        self.deadlines = types.ModuleType('homework_deadline_logic')
        def due(day):
            return next((d for d in self.transfer._effective_dates() if d > day), None)
        self.deadlines.due_lesson_for_source = due
        self.registry = {'ege11_lesson_transfer': self.transfer,
                         'homework_deadline_logic': self.deadlines}
        self.guard = patch.dict(sys.modules, self.registry)
        self.guard.start(); self.addCleanup(self.guard.stop)

    def test_one_schedule_read_for_thirteen_students_and_nested_reports(self):
        with m.read_snapshot():
            for student in range(13):
                with m.read_snapshot():
                    for _ in range(50):
                        self.assertEqual(self.deadlines.due_lesson_for_source(self.dates[0]), self.dates[1])
                        self.transfer._effective_dates()
        self.assertEqual(self.calls, 1)

    def test_next_request_sees_new_transfer_no_ttl(self):
        with m.read_snapshot():
            self.assertEqual(self.transfer._effective_dates(), self.dates)
        self.dates = (date(2026,10,6), date(2026,10,8))
        with m.read_snapshot():
            self.assertEqual(self.transfer._effective_dates(), self.dates)
        self.assertEqual(self.calls, 2)

    def test_outside_scope_reads_are_not_cached(self):
        with m.read_snapshot():
            self.transfer._effective_dates()
        self.transfer._effective_dates(); self.transfer._effective_dates()
        self.assertEqual(self.calls, 3)

    def test_exception_clears_scope(self):
        with self.assertRaises(ValueError):
            with m.read_snapshot():
                self.transfer._effective_dates()
                raise ValueError('test')
        self.assertIsNone(m._snapshot.get())
        with m.read_snapshot():
            self.transfer._effective_dates()
        self.assertEqual(self.calls, 2)

    def test_concurrent_requests_have_separate_snapshots(self):
        barrier = threading.Barrier(2)
        def request(_):
            with m.read_snapshot():
                barrier.wait(timeout=5)
                for _ in range(100):
                    self.transfer._effective_dates()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(request, range(2)))
        self.assertEqual(self.calls, 2)

    def test_install_wraps_full_read_only_views_and_is_idempotent(self):
        rewards = types.ModuleType('kulek_rewards')
        admin = types.ModuleType('ege_admin_webapp')
        student = types.ModuleType('ege_student_webapp')
        rewards.month_payload = lambda: self.transfer._effective_dates()
        def view(name):
            for _ in range(13): rewards.month_payload()
            return name
        admin._view = view
        student._payload = lambda uid: (rewards.month_payload(), uid)
        with patch.dict(sys.modules, {'kulek_rewards': rewards,
              'ege_admin_webapp': admin, 'ege_student_webapp': student}):
            m.install(); wrapped = rewards.month_payload; m.install()
            self.assertIs(rewards.month_payload, wrapped)
            self.assertEqual(admin._view('home'), 'home')
            self.assertEqual(self.calls, 1)
            student._payload(1)
            self.assertEqual(self.calls, 2)

    def test_late_transfer_install_is_resolved_on_request(self):
        with patch.dict(sys.modules, {'ege11_lesson_transfer': None}):
            with m.read_snapshot(): pass
        with m.read_snapshot():
            self.transfer._effective_dates(); self.transfer._effective_dates()
        self.assertEqual(self.calls, 1)

    def test_patch_scoped_and_idempotent(self):
        original = b'_INSTALLED = False\ndef install():\n    global _INSTALLED\n    _INSTALLED = True\n    print("ready")\n'
        updated = p.transform(original)
        self.assertEqual(p.transform(updated), updated)
        self.assertEqual(updated.replace(p.HOOK.encode(), b''), original)
        with self.assertRaises(ValueError): p.transform(b'def install():\n    pass\n')


if __name__ == '__main__':
    unittest.main()
