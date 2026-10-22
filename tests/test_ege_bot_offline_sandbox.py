"""Offline-only smoke tests for the disposable EGE BLIZKO rehearsal area."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "ege-bot-offline-sandbox.py"
spec = importlib.util.spec_from_file_location("ege_offline_sandbox", SCRIPT)
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)


class OfflineSandboxTests(unittest.TestCase):
    def make_root(self, root):
        root.mkdir()
        (root / "run_bot_production.py").write_text(
            'import helper\nimport teacher_product_payments\n'
            'from requests import get\n'
            'from importlib import import_module\n'
            'import_module("dynamic_local")\n'
            'raise RuntimeError("THIS_PRODUCTION_ENTRYPOINT_MUST_NOT_RUN")\n',
            encoding="utf-8",
        )
        (root / "ege_lab_webapp.py").write_text(
            "import helper\n", encoding="utf-8"
        )
        (root / "helper.py").write_text(
            "def return_fake():\n    return 42\n", encoding="utf-8"
        )
        (root / "dynamic_local.py").write_text(
            "def synthetic_only():\n    return True\n", encoding="utf-8"
        )
        (root / "teacher_product_payments.py").write_text(
            "PRIVATE_OTHER_PRODUCT = 'SECRET_TO_NEVER_COPY'\n", encoding="utf-8"
        )
        (root / ".env").write_text("BOT_TOKEN=NEVER_COPY_THIS\n")
        (root / "real_students.sqlite").write_bytes(b"NEVER_COPY_THE_REAL_DATABASE")
        (root / "question_bank.json").write_text('{"student": "NEVER_COPY"}')

    def test_copy_only_public_python_and_keep_real_data_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            self.make_root(root)
            output = base / "offline-staging"
            report = sandbox.build(root, output)
            self.assertEqual(report["copied_python_modules"], 4)
            self.assertIn("teacher_product_payments", report["excluded_separate_product_imports"])
            self.assertIn("requests", report["unverified_external_imports"])
            self.assertEqual(report["real_student_data_used"], False)
            self.assertEqual(report["telegram_bot_started"], False)
            self.assertTrue((output / "source" / "run_bot_production.py").exists())
            self.assertFalse((output / "source" / "teacher_product_payments.py").exists())
            for name in (".env", "real_students.sqlite", "question_bank.json"):
                self.assertFalse((output / name).exists())
                self.assertFalse((output / "source" / name).exists())
            self.assertTrue((output / "preflight.json").exists())
            with sqlite3.connect(output / "fixtures" / "synthetic-only.sqlite") as con:
                rows = con.execute("SELECT id, label FROM synthetic_students").fetchall()
            self.assertEqual(rows, [(1001, "FAKE_STUDENT_FOR_TESTS")])
            self.assertIn("NOT_READY", report["status"])

    def test_never_overwrite_checkout_or_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            self.make_root(root)
            for output in (root, root / "would_modify_source", base):
                with self.assertRaises(ValueError):
                    sandbox.build(root, output)

    def test_static_imports_are_not_execution(self):
        import ast
        code = ('import helper\nimportlib.import_module("dynamic_local")\n'
                '__import__(find_next_module())\n'
                'raise RuntimeError("never execute me")')
        names, unresolved_calls = sandbox.static_imports(ast.parse(code))
        self.assertIn("helper", names)
        self.assertIn("dynamic_local", names)
        self.assertEqual(unresolved_calls, 1)

    def test_symlinked_application_module_not_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            self.make_root(root)
            (root / "helper.py").unlink()
            outside = base / "private-other-code.py"
            outside.write_text("SECRET_CANARY = 'NEVER_READ'\n")
            (root / "helper.py").symlink_to(outside)
            output = base / "sandbox"
            report = sandbox.build(root, output)
            self.assertIn("helper", report["refused_or_unreadable"])
            self.assertFalse((output / "source" / "helper.py").exists())
            self.assertNotIn("NEVER_READ", json.dumps(report))

    def test_missing_seed_is_reported_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "checkout"
            root.mkdir()
            (root / "run_bot_production.py").write_text("import missing_dependency\n")
            report = sandbox.build(root, base / "sandbox")
            self.assertIn("ege_lab_webapp", report["missing_entrypoint_or_traversal_modules"])
            self.assertIn("missing_dependency", report["unverified_external_imports"])
            self.assertEqual(report["status"], "PREPARATION_ONLY_NOT_READY_TO_RUN_BOT")


if __name__ == "__main__":
    unittest.main()
