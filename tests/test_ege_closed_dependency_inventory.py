"""Offline regression: no VPS or credential access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "deploy/ege-closed-dependency-inventory.py"
spec = importlib.util.spec_from_file_location("ege_closed_dependencies", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DependenciesTests(unittest.TestCase):
    def test_seeds_fixed_and_unique(self):
        self.assertEqual(len(mod.SEEDS), 7)
        self.assertEqual(len(set(mod.SEEDS)), 7)

    def test_follow_local_imports_and_resources_without_reading_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run_bot_production.py").write_text(
                "import helper\nimport thirdparty\n"
                "RESOURCE = 'banks/questions.json'\n"
                "DATABASE = 'students.sqlite'\n"
                "SECRET = 'DO_NOT_EXPOSE_PRIVATE_CODE'\n", encoding="utf8")
            (root / "helper.py").write_text("from addon import entry\n")
            (root / "addon.py").write_text("def entry(): return 1\n")
            (root / "banks").mkdir()
            (root / "banks/questions.json").write_text('{"secret": "STUDENT_PRIVATE_DATA"}')
            report = mod.audit(root)
            self.assertEqual(report["modules"]["helper"]["status"], "present")
            self.assertEqual(report["modules"]["addon"]["status"], "present")
            self.assertNotIn("thirdparty", report["modules"])
            self.assertIn("students.sqlite", report["database_references_only"])
            self.assertEqual(report["assets"]["banks/questions.json"]["status"], "present")
            payload = json.dumps(report)
            self.assertNotIn("DO_NOT_EXPOSE_PRIVATE_CODE", payload)
            self.assertNotIn("STUDENT_PRIVATE_DATA", payload)

    def test_no_source_or_asset_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run_bot_production.py").symlink_to(root / "external.py")
            (root / "external.py").write_text("SECRET = 10")
            (root / "oge_classification_trainer.py").write_text('BANK="assets/trainer.json"\n')
            (root / "assets").symlink_to(root / "elsewhere")
            report = mod.audit(root)
            self.assertEqual(report["modules"]["run_bot_production"]["status"], "symlink")
            self.assertEqual(report["assets"]["assets/trainer.json"]["status"], "symlink_skipped")

    def test_no_path_escape(self):
        for name in ("../private.json", "/private/file.json", "https://site.local/private.json"):
            self.assertIsNone(mod.safe_resource(name))
        self.assertEqual(mod.safe_resource("assets/chart.svg"), ("assets/chart.svg", False))
        self.assertEqual(mod.safe_resource("payments.sqlite"), ("payments.sqlite", True))

    def test_separate_product_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "run_bot_production.py").write_text("import teacher_product_payments\n")
            (root / "teacher_product_payments.py").write_text('PRIVATE = "confidential"\n')
            report = mod.audit(root)
            self.assertNotIn("teacher_product_payments", report["modules"])

    def test_cms_encryption_has_no_plaintext(self):
        cert = Path(__file__).resolve().parents[1] / "deploy/sealed-audit-public-cert.crt"
        plaintext = b"TOP_PRIVATE_SERVER_CONTENT"
        encrypted = mod.encrypt_in_memory(plaintext, cert.read_bytes())
        self.assertTrue(encrypted.startswith(b"\x30"))
        self.assertNotIn(plaintext, encrypted)


if __name__ == "__main__":
    unittest.main()
