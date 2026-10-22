"""Offline acceptance against an explicitly supplied, private VPS source copy.

No copying, SSH or decryption. Private files stay outside the repository.
Uses the existing PTB memory transport and synthetic SQLite; socket/DNS blocked.
Does not load the complete production host or run_bot_live7.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PINNED = {
    "run_bot_live7.py": "d61df65fd87e52a5ae852a28b5edbc1a026af4cbb5998ae3a542f793070415da",
    "public_channel_trainers.py": "be7b8d058da8cfd90ed57f9dae1f9e7769b448763ef56a8a18bdbebeab8c9a53",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-source-root", required=True)
    args = parser.parse_args()
    private_root = Path(args.private_source_root)
    for name, sha in PINNED.items():
        path = private_root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise SystemExit("PRIVATE_SNAPSHOT_MISMATCH")
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "private_catalog_protocol", ROOT / "tests/test_decomposition_telegram.py")
    tests = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tests)
    previous_load = tests.load_source

    def load_actual_public(name, host):
        if name != "public_channel_trainers":
            return previous_load(name, host)
        spec = importlib.util.spec_from_file_location(
            "private_catalog_module", private_root / "public_channel_trainers.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"run_bot_live90": host}):
            spec.loader.exec_module(module)
        return module

    tests.load_source = load_actual_public

    class PrivateCatalogAcceptance(tests.TelegramProtocolTest):
        async def test_actual_catalog_stats_and_assignment_visibility_are_separate(self):
            await self.app.shutdown()
            await self.create_app(public=True)
            await self.command(uid=202)
            await self.click(self.button_data("10 случайных", uid=202), uid=202)
            for index in range(10):
                await self.click(self.answer_data(uid=202), uid=202)
                if index < 9:
                    await self.click(self.button_data("Дальше", uid=202), uid=202)
            self.assertIn("1 трен. · 100%", self.public._user_stats_text(202))
            self.assertIn("Всего тренировок: <b>0</b>", self.public._user_stats_text(101))
            # VPS active means assigned; public_active controls public visibility.
            with sqlite3.connect(self.db) as conn:
                conn.execute("UPDATE weekly_trainer_catalog SET active=0 WHERE code='decomposition'")
            self.assertTrue(any(row[0] == "decomposition" for row in self.public._catalog_rows()))
            self.assertFalse(self.public._catalog_rows(assigned_only=True))
            self.assertIsNotNone(self.public._catalog_item("decomposition"))
            self.assertIn("Всего тренировок: <b>0</b>", self.public._user_stats_text(202))
            await self.command(uid=202)
            self.assertIn("Реакции разложения", self.api.last_message(202)["text"])
            self.public._set_public_active("decomposition", False)
            await self.command(uid=202)
            self.assertIn("временно скрыт", self.api.last_message(202)["text"])
            await self.command(uid=101)
            self.assertIn("Реакции разложения", self.api.last_message(101)["text"])

    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PrivateCatalogAcceptance))
    finally:
        tests.load_source = previous_load
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
