import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compatibility', ROOT / 'deploy/decomposition_compatibility_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
START = '''# synthetic local changes must survive
raise RuntimeError("MUST_NEVER_EXECUTE_SOURCE_SENTINEL")
def local_feature():
    return "PRIVATE_LITERAL_SENTINEL"
def main():
    import middle_salts_trainer
    middle_salts_trainer.install()
    local_feature()
    import public_channel_trainers
    public_channel_trainers.install()
'''
REWARDS = '''TRAINER_TABLES = {}
def _trainer_goals(month_key, students):
    catalog = [('existing', 'Existing')]
    result = []
    for code, title in catalog:
        code = str(code)
        table = TRAINER_TABLES.get(code, f"{code}_sessions")
        result.append((code, title, table))
    return result
'''
ROUTES = '''async def start_router(update, context):
    pass
async def trivial_callback(update, context):
    pass
'''


class CompatibilityAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, text in [('run_bot_production.py', START), ('kulek_rewards.py', REWARDS),
                           ('run_bot_live7.py', ROUTES), ('public_channel_trainers.py', ROUTES)]:
            (self.root / name).write_text(text)

    def test_only_two_startup_statements_added_all_local_text_preserved(self):
        proposed = audit.plan_startup(START)
        insertion = '    import decomposition_trainer\n    decomposition_trainer.install()\n'
        self.assertEqual(proposed.replace(insertion, '', 1), START)
        self.assertLess(proposed.index('decomposition_trainer.install()'),
                        proposed.index('public_channel_trainers.install()'))

    def test_reward_insertion_preserves_every_other_byte(self):
        proposed = audit.plan_rewards(REWARDS)
        self.assertEqual(proposed.replace('        if code == "decomposition":\n            continue\n', '', 1), REWARDS)

    def test_no_source_execution_exports_or_writes(self):
        (self.root / '.env').write_text('SECRET_FILE_SENTINEL')
        (self.root / 'students.sqlite').write_text('DATABASE_FILE_SENTINEL')
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()}
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'INSERTIONS_POSSIBLE_ROUTING_BEHAVIOR_STILL_UNVERIFIED')
        self.assertFalse(result['approved_for_release'])
        self.assertFalse(result['routing_behavior_verified'])
        output = json.dumps(result)
        for sentinel in ['PRIVATE_LITERAL_SENTINEL', 'MUST_NEVER_EXECUTE_SOURCE_SENTINEL',
                         'SECRET_FILE_SENTINEL', 'DATABASE_FILE_SENTINEL', 'local_feature']:
            self.assertNotIn(sentinel, output)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.iterdir()})
        self.assertEqual(set(result['files']), set(audit.FILES))

    def test_missing_duplicate_and_reordered_anchors_are_blocked(self):
        variants = [START.replace('    middle_salts_trainer.install()\n', ''),
                    START.replace('    middle_salts_trainer.install()\n', '    middle_salts_trainer.install()\n' * 2),
                    START.replace('    middle_salts_trainer.install()\n', '    public_channel_trainers.install()\n')]
        for source in variants:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    audit.plan_startup(source)
        with self.assertRaises(ValueError):
            audit.plan_startup(audit.plan_startup(START))

    def test_colliding_new_file_blocks_release(self):
        (self.root / 'decomposition_trainer.py').write_text('# unknown existing file')
        self.assertEqual(audit.audit(self.root)['status'], 'BLOCKED_REVIEW_REQUIRED')

    def test_changed_handler_signature_blocks_release(self):
        (self.root / 'run_bot_live7.py').write_text(ROUTES.replace('update, context', 'update, context, extra'))
        self.assertEqual(audit.audit(self.root)['status'], 'BLOCKED_REVIEW_REQUIRED')

    def test_symlink_and_invalid_python_are_refused(self):
        target = self.root / 'run_bot_production.py'
        target.unlink()
        target.symlink_to(self.root / '.env')
        with self.assertRaises(ValueError):
            audit.audit(self.root)
        target.unlink()
        target.write_text('INVALID PYTHON !')
        result = audit.audit(self.root)
        self.assertEqual(result['plans']['run_bot_production.py']['reason'], 'SyntaxError')
        self.assertEqual(result['status'], 'BLOCKED_REVIEW_REQUIRED')

    def test_crlf_is_preserved(self):
        source = START.replace('\n', '\r\n')
        proposed = audit.plan_startup(source)
        self.assertNotIn('\n', proposed.replace('\r\n', ''))


if __name__ == '__main__':
    unittest.main()
