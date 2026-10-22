"""Read-only release-preflight unit tests; no Timeweb/Telegram access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "decomposition_preflight", ROOT / "deploy/ege-decomposition-readonly-preflight.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ReleasePreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parent = Path(self.tmp.name)
        self.live = parent / "live"
        self.candidate = parent / "candidate"
        self.live.mkdir()
        self.candidate.mkdir()
        self.entry = self.live / "run_bot_production.py"
        self.original = (
            "import run_bot_live85\n"
            "def main():\n"
            "    import middle_salts_trainer\n"
            "    middle_salts_trainer.install()\n"
            "    import real_server_feature\n"
            "    real_server_feature.install()\n"
            "    return True\n"
        )
        self.entry.write_text(self.original, encoding="utf-8")
        (self.live / "run_bot_live85.py").write_text("pass\n", encoding="utf-8")
        for name in mod.CANDIDATES:
            (self.candidate / name).write_text(
                f"FAKE_DATA = '{name}'\n", encoding="utf-8"
            )

    def test_read_only_check_preserves_server_and_private_extensions(self):
        prior = self.entry.read_bytes()
        details = mod.check(self.live, self.candidate)
        self.assertEqual(self.entry.read_bytes(), prior)
        self.assertTrue(details["status"].endswith("NOT_DEPLOYED"))
        self.assertEqual(details["new_python_files"], 2)
        self.assertFalse(details["bot_restarted"])
        self.assertFalse(details["student_data_read"])
        changed = mod.proposed_patch(*mod.read_source(self.live, mod.APP_NAME)[1:])
        self.assertEqual(changed.count("decomposition_trainer.install()"), 1)
        self.assertIn("real_server_feature.install()", changed)
        self.assertIn("middle_salts_trainer.install()", changed)
        self.assertLess(
            changed.index("middle_salts_trainer.install()"),
            changed.index("decomposition_trainer.install()"),
        )

    def test_no_legacy_anchor_no_release(self):
        self.entry.write_text("def main():\n    pass\n")
        with self.assertRaisesRegex(mod.StagingBlocked, "ANCHOR"):
            mod.check(self.live, self.candidate)

    def test_duplicate_anchor_no_release(self):
        self.entry.write_text(self.original.replace(
            "    middle_salts_trainer.install()\n",
            "    middle_salts_trainer.install()\n    middle_salts_trainer.install()\n"
        ))
        with self.assertRaises(mod.StagingBlocked):
            mod.check(self.live, self.candidate)

    def test_existing_trainer_file_no_overwrite(self):
        (self.live / "decomposition_trainer.py").write_text(
            "SERVER_ONLY_SECRET = 'DO_NOT_OVERWRITE'\n"
        )
        with self.assertRaisesRegex(mod.StagingBlocked, "ALREADY_EXISTS"):
            mod.check(self.live, self.candidate)
        self.assertIn("DO_NOT_OVERWRITE",
                      (self.live / "decomposition_trainer.py").read_text())

    def test_existing_installer_no_double_registration(self):
        self.entry.write_text(self.original.replace(
            "    middle_salts_trainer.install()\n",
            "    middle_salts_trainer.install()\n"
            "    import decomposition_trainer\n"
            "    decomposition_trainer.install()\n"
        ))
        with self.assertRaisesRegex(mod.StagingBlocked, "ALREADY_BE_INSTALLED"):
            mod.check(self.live, self.candidate)

    def test_missing_imported_base_module_no_release(self):
        (self.live / "run_bot_live85.py").unlink()
        with self.assertRaises(mod.StagingBlocked):
            mod.check(self.live, self.candidate)

    def test_symlinked_source_no_release(self):
        (self.candidate / mod.CANDIDATES[0]).unlink()
        (self.candidate / mod.CANDIDATES[0]).symlink_to(self.entry)
        with self.assertRaisesRegex(mod.StagingBlocked, "SYMLINK"):
            mod.check(self.live, self.candidate)

    def test_syntax_error_no_release(self):
        self.entry.write_text("def main(: pass\n")
        with self.assertRaisesRegex(mod.StagingBlocked, "PYTHON_PARSE_FAILED"):
            mod.check(self.live, self.candidate)

    def test_crlf_patch_preserved(self):
        text = self.original.replace("\n", "\r\n")
        import ast
        patched = mod.proposed_patch(text, ast.parse(text))
        self.assertIn("\r\n    decomposition_trainer.install()\r\n", patched)
        self.assertNotIn("\n    decomposition_trainer.install()\n", patched.replace("\r\n", ""))


if __name__ == "__main__":
    unittest.main()
