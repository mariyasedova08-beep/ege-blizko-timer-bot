"""Offline file-set and rollback rehearsal; never connect to a server."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_decomposition", ROOT / "deploy/prepare_decomposition_release.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ReleasePreparationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.baseline = self.root / "candidate", self.root / "old"
        self.source.mkdir()
        self.baseline.mkdir()
        for name in prepare.RUNTIME_FILES:
            (self.source / name).write_text("# reviewed new " + name + "\n")
        for name in prepare.BASELINE_FILES:
            (self.baseline / name).write_text("# reviewed old " + name + "\n")
        self.output = self.root / "bundle"
        self.manifest = self.root / "fixture_manifest.json"
        self.specification = {
            "runtime_sha256": {p: digest((self.source / p).read_bytes()) for p in prepare.RUNTIME_FILES},
            "baseline_sha256": {p: digest((self.baseline / p).read_bytes()) for p in prepare.BASELINE_FILES},
            "baseline_source": "SYNTHETIC_FIXTURE_ONLY",
        }
        self.manifest.write_text(json.dumps(self.specification))

    def build(self, **kwargs):
        return prepare.build(kwargs.get("source", self.source), self.baseline,
                             kwargs.get("output", self.output), self.manifest)

    def test_only_reviewed_code_is_copied_never_secrets_or_databases(self):
        for root in [self.source, self.baseline]:
            for name in [".env", "students.sqlite", "private.key", "unrelated.py"]:
                (root / name).write_text("DO_NOT_COPY_SYNTHETIC_SENTINEL")
        result = self.build()
        files = {str(p.relative_to(self.output)) for p in self.output.rglob("*") if p.is_file()}
        expected = {"preflight.json"}
        expected.update("runtime/" + p for p in prepare.RUNTIME_FILES)
        expected.update("baseline/" + p for p in prepare.BASELINE_FILES)
        self.assertEqual(files, expected)
        for p in self.output.rglob("*"):
            if p.is_file():
                self.assertNotIn("DO_NOT_COPY_SYNTHETIC_SENTINEL", p.read_text())
        self.assertFalse(result["server_compatibility_verified"])
        self.assertFalse(result["production_backup_created"])
        self.assertFalse(result["production_modified"])

    def test_baseline_drift_is_rejected_before_any_output(self):
        (self.baseline / "run_bot_production.py").write_text("# server has local changes\n")
        with self.assertRaisesRegex(ValueError, "CHECKSUM"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_candidate_tampering_is_rejected_before_any_output(self):
        (self.source / "decomposition_trainer_questions.tsv").write_text("unexpected bank")
        with self.assertRaisesRegex(ValueError, "CHECKSUM"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_existing_output_and_unrelated_contents_are_preserved(self):
        self.output.mkdir()
        marker = self.output / "keep"
        marker.write_text("unchanged")
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_NOT_EXIST"):
            self.build()
        self.assertEqual(marker.read_text(), "unchanged")

    def test_linked_code_is_refused(self):
        target = self.source / "decomposition_trainer.py"
        target.rename(self.root / "elsewhere.py")
        target.symlink_to(self.root / "elsewhere.py")
        with self.assertRaisesRegex(ValueError, "LINKED"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_new_file_collision_in_baseline_is_refused(self):
        (self.baseline / "decomposition_trainer.py").write_text("do not overwrite this")
        with self.assertRaisesRegex(ValueError, "NEW_FILE_ALREADY_EXISTS"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_nested_output_and_symlink_parent_are_refused(self):
        with self.assertRaisesRegex(ValueError, "OUTPUT_MUST_BE_SEPARATE"):
            self.build(output=self.source / "bundle")
        linked = self.root / "linked"
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "PLAIN_DIRECTORY"):
            self.build(output=linked / "bundle")
        self.assertFalse((self.source / "bundle").exists())

    def test_allowlist_cannot_expand_to_other_files(self):
        self.specification["runtime_sha256"][".env"] = "0" * 64
        self.manifest.write_text(json.dumps(self.specification))
        with self.assertRaisesRegex(ValueError, "ALLOWLIST_MISMATCH"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_fixture_file_rollback_preserves_database_and_new_answers(self):
        self.build()
        rehearsal = self.root / "rehearsal"
        shutil.copytree(self.baseline, rehearsal)
        db = rehearsal / "synthetic.sqlite"
        with sqlite3.connect(db) as conn:
            conn.executescript("""
                CREATE TABLE payments(id INTEGER PRIMARY KEY, amount INTEGER);
                INSERT INTO payments VALUES(1,13200);
                CREATE TABLE weekly_trainer_catalog(code TEXT PRIMARY KEY,active INTEGER);
                INSERT INTO weekly_trainer_catalog VALUES('trivial',1);
            """)
        # Rehearse file replacement in this disposable directory only.
        for p in (self.output / "runtime").iterdir():
            shutil.copyfile(p, rehearsal / p.name)
        with sqlite3.connect(db) as conn:
            conn.executescript("""
                CREATE TABLE decomposition_attempts(id INTEGER PRIMARY KEY,correct INTEGER);
                INSERT INTO decomposition_attempts VALUES(1,1);
                INSERT INTO weekly_trainer_catalog VALUES('decomposition',1);
            """)
        # Rehearse documented code rollback, retaining data written meanwhile.
        for p in (self.output / "baseline").iterdir():
            shutil.copyfile(p, rehearsal / p.name)
        for name in prepare.RUNTIME_FILES - prepare.BASELINE_FILES:
            (rehearsal / name).unlink()
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE weekly_trainer_catalog SET active=0 WHERE code='decomposition'")
            self.assertEqual(conn.execute("SELECT amount FROM payments").fetchall(), [(13200,)])
            self.assertEqual(conn.execute("SELECT correct FROM decomposition_attempts").fetchall(), [(1,)])
            self.assertEqual(conn.execute("SELECT code,active FROM weekly_trainer_catalog ORDER BY code").fetchall(),
                             [("decomposition", 0), ("trivial", 1)])
        for name in prepare.BASELINE_FILES:
            self.assertEqual((rehearsal / name).read_bytes(), (self.baseline / name).read_bytes())

    def test_checked_in_manifest_pins_the_current_runtime_files(self):
        reviewed = json.loads(prepare.MANIFEST_PATH.read_text())
        self.assertEqual(set(reviewed["runtime_sha256"]), prepare.RUNTIME_FILES)
        self.assertEqual(set(reviewed["baseline_sha256"]), prepare.BASELINE_FILES)
        for name, expected in reviewed["runtime_sha256"].items():
            self.assertEqual(digest((ROOT / name).read_bytes()), expected, name)


if __name__ == "__main__":
    unittest.main()
