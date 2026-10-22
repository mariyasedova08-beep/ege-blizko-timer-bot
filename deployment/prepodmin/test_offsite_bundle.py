"""Offline, synthetic-only regression tests for PREPODMIN offsite bundle staging."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SOURCE = Path(__file__).with_name("prepare_offsite_bundle.py")
spec = importlib.util.spec_from_file_location("prepodmin_offsite_bundle", SOURCE)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "teacher_product.sqlite3"
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE teacher_webapp_homework_files "
                         "(stored_name TEXT PRIMARY KEY, size_bytes INTEGER)")
            conn.commit()

    def add_attachment(self, name=None):
        name = name or ("a" * 32 + ".pdf")
        content = b"%PDF-1.4\nSynthetic test only"
        (self.uploads / name).write_bytes(content)
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO teacher_webapp_homework_files VALUES(?, ?)",
                (name, len(content)),
            )
        return name

    def test_bundle_restores_sqlite_and_immutable_attachment(self):
        name = self.add_attachment()
        bundle = self.root / "bundle"
        self.assertEqual(backup.prepare(self.db, self.uploads, bundle)["files"], 1)
        self.assertEqual(backup.verify(bundle), 1)
        with sqlite3.connect(bundle / "teacher_product.sqlite3") as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual((bundle / "homework_uploads" / name).read_bytes(),
                         (self.uploads / name).read_bytes())

    def test_tampering_with_staged_blob_is_caught(self):
        name = self.add_attachment()
        bundle = self.root / "bundle"
        backup.prepare(self.db, self.uploads, bundle)
        (bundle / "homework_uploads" / name).write_bytes(b"corrupted")
        with self.assertRaises(RuntimeError):
            backup.verify(bundle)

    def test_missing_file_prevents_success(self):
        self.add_attachment()
        (self.uploads / ("a" * 32 + ".pdf")).unlink()
        with self.assertRaises(RuntimeError):
            backup.prepare(self.db, self.uploads, self.root / "bundle")

    def test_unknown_filename_rejected(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO teacher_webapp_homework_files VALUES(?, ?)",
                         ("../../other.sqlite3", 1))
        with self.assertRaises(RuntimeError):
            backup.prepare(self.db, self.uploads, self.root / "bundle")

    def test_legacy_database_without_files_table(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE teacher_webapp_homework_files")
        bundle = self.root / "bundle"
        self.assertEqual(backup.prepare(self.db, self.uploads, bundle)["files"], 0)
        self.assertEqual(backup.verify(bundle), 0)

    def test_symlink_in_attachments_rejected(self):
        name = self.add_attachment()
        (self.uploads / name).unlink()
        (self.uploads / name).symlink_to(self.db)
        with self.assertRaises(RuntimeError):
            backup.prepare(self.db, self.uploads, self.root / "bundle")


if __name__ == "__main__":
    unittest.main()
