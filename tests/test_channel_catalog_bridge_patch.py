import ast
import importlib.util
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('patch', ROOT / 'deploy/channel_catalog_bridge_patch.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

# Minimal fixture, with no private VPS module or application constants.
SOURCE = b'''# unrelated bytes must stay unchanged

def _bridge_catalog():
    original_rows = pub._catalog_rows
    def public_rows(include_hidden=False):
        rows = list(original_rows(include_hidden=include_hidden))
        own = _public_tuple()
        if (include_hidden or own[4]) and not any(str(row[0]) == CODE for row in rows):
            rows.append(own)
        return sorted(rows, key=lambda row: (int(row[3]), str(row[1])))
    pub._catalog_rows = public_rows
'''


def adapter(source, visible=True, existing=False):
    calls = []
    own = ('oge', 'OGE', 'oge', 2, int(visible))
    def rows(include_hidden=False, assigned_only=False):
        calls.append((include_hidden, assigned_only))
        return [('ege', 'EGE', 'ege', 1, 1)] + ([own] if existing else [])
    pub = types.SimpleNamespace(_catalog_rows=rows)
    tree = ast.parse(source)
    bridge = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_bridge_catalog')
    namespace = {'pub': pub, 'CODE': 'oge', '_public_tuple': lambda: own}
    exec(compile(ast.Module(body=[bridge], type_ignores=[]), 'isolated-adapter', 'exec'), namespace)
    namespace['_bridge_catalog']()
    return pub._catalog_rows, calls


class BridgeTests(unittest.TestCase):
    def test_original_reproduces_subscriber_button_failure(self):
        rows, _ = adapter(SOURCE)
        with self.assertRaisesRegex(TypeError, 'assigned_only'):
            rows(include_hidden=True, assigned_only=True)

    def test_assigned_metrics_exclude_public_only_oge(self):
        for hidden in (False, True):
            for assigned in (False, True):
                with self.subTest(hidden=hidden, assigned=assigned):
                    rows, calls = adapter(patch.transform(SOURCE))
                    result = rows(include_hidden=hidden, assigned_only=assigned)
                    self.assertEqual(calls, [(hidden, assigned)])
                    self.assertEqual('oge' in [r[0] for r in result], not assigned)

    def test_hidden_oge_only_in_admin_catalog(self):
        rows, _ = adapter(patch.transform(SOURCE), visible=False)
        self.assertEqual([r[0] for r in rows()], ['ege'])
        self.assertEqual([r[0] for r in rows(include_hidden=True)], ['ege', 'oge'])

    def test_default_call_and_repeated_calls_no_duplicates(self):
        rows, _ = adapter(patch.transform(SOURCE), existing=True)
        for _ in range(3):
            self.assertEqual([r[0] for r in rows()], ['ege', 'oge'])

    def test_idempotent_and_preserves_other_bytes(self):
        result = patch.transform(SOURCE)
        self.assertEqual(result, SOURCE.replace(patch.OLD, patch.NEW))
        self.assertEqual(result, patch.transform(result))

    def test_rejects_changed_or_missing_anchor(self):
        with self.assertRaises(ValueError):
            patch.transform(SOURCE.replace(patch.OLD, patch.OLD.replace(b'False', b'True')))

    def test_other_function_is_not_changed(self):
        other = b'\ndef unrelated():\n' + patch.OLD + b'        return rows\n'
        result = patch.transform(SOURCE + other)
        self.assertTrue(result.endswith(other))


from unittest.mock import patch as mock
import tempfile
import os
import stat


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.target = root / 'oge.py'
        self.target.write_bytes(SOURCE)
        self.target.chmod(0o640)
        self.public = root / 'public.py'
        self.public.write_bytes(b'reviewed public router')
        self.state = root / 'backup'
        values = {'TARGET': self.target, 'STATE': self.state, 'PUBLIC': self.public,
                  'BEFORE': patch.digest(SOURCE), 'AFTER': patch.digest(patch.transform(SOURCE)),
                  'PUBLIC_HASH': patch.digest(self.public.read_bytes())}
        context = mock.multiple(patch, **values)
        context.start()
        self.addCleanup(context.stop)
        owner = mock.object(patch.os, 'fchown', wraps=os.fchown) if os.geteuid() == 0 else mock.object(patch.os, 'fchown')
        owner.start()
        self.addCleanup(owner.stop)

    def test_install_and_manual_rollback_preserve_original_and_permissions(self):
        with mock.object(patch, 'restart') as restart, mock.object(patch, 'healthy', return_value=True):
            patch.release()
            self.assertEqual(self.target.read_bytes(), patch.transform(SOURCE))
            self.assertEqual((self.state / 'original.py').read_bytes(), SOURCE)
            self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
            patch.release(rollback=True)
            self.assertEqual(self.target.read_bytes(), SOURCE)
            self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
            self.assertEqual(restart.call_count, 2)

    def test_failed_health_restores_original(self):
        with mock.object(patch, 'restart') as restart, mock.object(patch, 'healthy', side_effect=[True, False, True]):
            with self.assertRaisesRegex(ValueError, 'HEALTH_FAILED_AFTER_PATCH'):
                patch.release()
            self.assertEqual(self.target.read_bytes(), SOURCE)
            self.assertEqual(restart.call_count, 2)

    def test_changed_production_is_rejected_without_backup_or_restart(self):
        self.target.write_bytes(SOURCE + b'\n# later VPS edit\n')
        with mock.object(patch, 'restart') as restart:
            with self.assertRaisesRegex(ValueError, 'PRODUCTION_FILE_CHANGED'):
                patch.release()
            restart.assert_not_called()
            self.assertFalse(self.state.exists())

    def test_repeated_install_does_not_restart(self):
        with mock.object(patch, 'restart') as restart, mock.object(patch, 'healthy', return_value=True):
            patch.release()
            patch.release()
            self.assertEqual(restart.call_count, 1)

    def test_symlink_target_is_rejected(self):
        real = self.target.with_suffix('.real')
        self.target.rename(real)
        self.target.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'NON_REGULAR_FILE'):
            patch.release()


if __name__ == '__main__':
    unittest.main()
