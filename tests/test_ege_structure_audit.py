"""Ensure source-private structural inventory is read-only and safe."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "ege-blizko-structure-audit.py"
spec = importlib.util.spec_from_file_location("ege_structure_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StructureAuditTests(unittest.TestCase):
    def test_fixed_allowlist(self):
        self.assertEqual(len(mod.FILES), 7)
        self.assertEqual(len(mod.FILES), len(set(mod.FILES)))
        self.assertTrue(all(Path(name).name == name and name.endswith(".py") for name in mod.FILES))

    def test_no_server_literals_or_symbol_names_in_output(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / "run_bot_production.py").write_text(
                "API_KEY = 'TOP_PRIVATE_VALUE_NOT_FOR_LOGS'\n"
                "def hidden_personal_function():\n"
                "    return 'TOP_PRIVATE_VALUE_NOT_FOR_LOGS'\n",
                encoding="utf-8",
            )
            source = mod.analyse(root, include_public_names=False)
            combined = "\n".join("\t".join(row) for row in source)
            self.assertNotIn("TOP_PRIVATE_VALUE_NOT_FOR_LOGS", combined)
            self.assertNotIn("hidden_personal_function", combined)
            data = mod.parse_report(combined, remote=True)
            self.assertEqual(data["run_bot_production.py"]["file"], "EXISTS")

    def test_compare_only_reports_public_github_names(self):
        with tempfile.TemporaryDirectory() as p1, tempfile.TemporaryDirectory() as p2:
            local, remote = Path(p1), Path(p2)
            (local / "run_bot_production.py").write_text(
                "def known_public_function():\n    return 1\n", encoding="utf-8"
            )
            (remote / "run_bot_production.py").write_text(
                "def secret_server_only_symbol():\n    pass\n"
                "def known_public_function():\n    if True:\n        return 1\n",
                encoding="utf-8",
            )
            a = mod.parse_report(
                "\n".join("\t".join(row) for row in mod.analyse(local, True)),
                remote=False,
            )
            b = mod.parse_report(
                "\n".join("\t".join(row) for row in mod.analyse(remote, False)),
                remote=True,
            )
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                with self.assertRaisesRegex(SystemExit, "STRUCTURAL_DRIFT_REQUIRES_MANUAL_REVIEW"):
                    mod.compare(a, b)
            output = capture.getvalue()
            self.assertIn("known_public_function", output)
            self.assertNotIn("secret_server_only_symbol", output)
            self.assertIn("NO_SERVER_SOURCE_EXPORTED", output)

    def test_symbolic_link_is_refused(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            target = root / "another.py"
            target.write_text("secret = 1", encoding="utf-8")
            (root / "run_bot_production.py").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "SYMLINK_SOURCE_REJECTED"):
                mod.analyse(root, include_public_names=False)

    def test_remote_report_rejects_names(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            (root / "run_bot_production.py").write_text("def test_name():\n    pass\n")
            local = "\n".join("\t".join(row) for row in mod.analyse(root, True))
            with self.assertRaisesRegex(ValueError, "REMOTE_NAMES_FORBIDDEN"):
                mod.parse_report(local, remote=True)


if __name__ == "__main__":
    unittest.main()
