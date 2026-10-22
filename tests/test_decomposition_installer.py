import importlib.util
from pathlib import Path
import os
import io
from contextlib import ExitStack, contextmanager
import sys
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "deploy/install_decomposition_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_atomic_write_retains_owner_mode_and_exact_bytes(self):
        target = self.root / "source.py"
        target.write_bytes(b"before")
        target.chmod(0o640)
        metadata = target.stat()
        release.atomic_write(target, b"after", metadata)
        self.assertEqual(target.read_bytes(), b"after")
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual((target.stat().st_uid, target.stat().st_gid),
                         (metadata.st_uid, metadata.st_gid))
        self.assertFalse(list(self.root.glob(".decomposition-release-*")))

    def test_interrupted_atomic_replace_keeps_original_and_removes_temp(self):
        target = self.root / "source.py"
        target.write_bytes(b"before")
        with patch.object(release.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                release.atomic_write(target, b"after", target.stat())
        self.assertEqual(target.read_bytes(), b"before")
        self.assertFalse(list(self.root.glob(".decomposition-release-*")))

    def test_drift_symlink_and_new_package_mismatch_are_rejected(self):
        source = self.root / "source.py"
        source.write_bytes(b"unreviewed")
        with self.assertRaises(ValueError):
            release.read_pinned(source, "0" * 64)
        alias = self.root / "alias.py"
        alias.symlink_to(source)
        with self.assertRaises(ValueError):
            release.read_pinned(alias, release.digest(source.read_bytes()))
        with self.assertRaises(ValueError):
            release.validate_new({"extra.py": b"unexpected"})
        with self.assertRaises(ValueError):
            release.patch_sources({name:b"unreviewed" for name in release.OLD})

    def test_online_backup_contains_committed_wal_and_does_not_replace_live_db(self):
        db, backup = self.root / "live.db", self.root / "backup.db"
        conn = sqlite3.connect(db)
        self.addCleanup(conn.close)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE payments(id INTEGER PRIMARY KEY,amount INTEGER)")
        conn.execute("INSERT INTO payments VALUES(1,13200)")
        conn.commit()
        release.database_backup(db, backup)
        conn.execute("INSERT INTO payments VALUES(2,15000)")
        conn.commit()
        with sqlite3.connect(backup) as saved:
            self.assertEqual(saved.execute("SELECT * FROM payments").fetchall(),[(1,13200)])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM payments").fetchone(),(2,))
        self.assertEqual(backup.stat().st_mode & 0o777,0o600)

    def test_rollback_hides_both_catalog_flags_preserving_payments_and_answers(self):
        db=self.root/"live.db"
        with sqlite3.connect(db) as conn:
            conn.executescript("""
              CREATE TABLE weekly_trainer_catalog(code TEXT PRIMARY KEY,active INTEGER);
              INSERT INTO weekly_trainer_catalog VALUES('trivial',1),('decomposition',1);
              CREATE TABLE channel_trainer_catalog_settings(code TEXT PRIMARY KEY,public_active INTEGER,updated_at TEXT);
              INSERT INTO channel_trainer_catalog_settings VALUES('trivial',1,'unchanged');
              CREATE TABLE payments(amount INTEGER);
              INSERT INTO payments VALUES(13200);
              CREATE TABLE decomposition_attempts(correct INTEGER);
              INSERT INTO decomposition_attempts VALUES(1);
            """)
        release.hide_rollback_catalog(db)
        release.hide_rollback_catalog(db)
        with sqlite3.connect(db) as conn:
            self.assertEqual(conn.execute("SELECT * FROM weekly_trainer_catalog ORDER BY code").fetchall(),
                             [('decomposition',0),('trivial',1)])
            self.assertEqual(conn.execute("SELECT code,public_active FROM channel_trainer_catalog_settings ORDER BY code").fetchall(),
                             [('decomposition',0),('trivial',1)])
            self.assertEqual(conn.execute("SELECT amount FROM payments").fetchall(),[(13200,)])
            self.assertEqual(conn.execute("SELECT correct FROM decomposition_attempts").fetchall(),[(1,)])

    def test_backup_and_health_configuration_must_be_explicit(self):
        with patch.object(release,"APP",self.root), patch.object(release,"DB",self.root/"data/live.db"):
            with patch.object(release,"run",return_value=""):
                with self.assertRaises(ValueError):
                    release.verify_database_configuration()
            (self.root/"runtime-vars.json").write_text('{"COREAPP_DB_PATH":"/wrong/database.db"}')
            with patch.object(release,"run",return_value=""):
                with self.assertRaises(ValueError):
                    release.verify_database_configuration()

    @contextmanager
    def fixture_installation(self, health=True):
        app=self.root/"app";app.mkdir()
        db=app/"live.db"
        originals={name:b"before = 1\n" for name in release.OLD}
        modified={name:b"after = 2\n" for name in release.PATCHED}
        router_data={name:b"router = 1\n" for name in release.ROUTERS}
        rows="".join(f"question{i}\tcorrect\ta\tb\tc\tequation\tnote\n" for i in range(50))
        payload={name:(rows.encode() if name.endswith(".tsv") else b"value = 1\n") for name in release.NEW}
        for name,raw in {**originals,**router_data}.items():
            (app/name).write_bytes(raw);(app/name).chmod(0o640)
        with sqlite3.connect(db) as conn:
            conn.executescript("""
              CREATE TABLE payments(amount INTEGER);
              INSERT INTO payments VALUES(13200);
              CREATE TABLE weekly_trainer_catalog(code TEXT PRIMARY KEY,start_param TEXT,active INTEGER);
              INSERT INTO weekly_trainer_catalog VALUES('trivial','trivial',1),('decomposition','decomposition',1);
              CREATE TABLE channel_trainer_catalog_settings(code TEXT PRIMARY KEY,public_active INTEGER,updated_at TEXT);
              INSERT INTO channel_trainer_catalog_settings VALUES('trivial',1,'unchanged');
            """)
        class Response(io.BytesIO):
            status=200
        def fetch(url,**_kwargs):
            return Response(b"OK" if url.endswith("/health") else payload[url.rsplit("/",1)[1]])
        before_umask=os.umask(0o077)
        with ExitStack() as stack:
            for name,value in dict(APP=app,DB=db,STATE=self.root/"backups",LOCK=self.root/"lock",
                OLD={n:release.digest(b) for n,b in originals.items()},
                PATCHED={n:release.digest(b) for n,b in modified.items()},
                ROUTERS={n:release.digest(b) for n,b in router_data.items()},
                NEW={n:release.digest(b) for n,b in payload.items()}).items():
                stack.enter_context(patch.object(release,name,value))
            stack.enter_context(patch.object(release.os,"geteuid",return_value=0))
            stack.enter_context(patch.object(sys,"argv",["installer",release.RELEASE_ID]))
            stack.enter_context(patch.object(release,"run",side_effect=lambda cmd,**kw:
                "ege-bot" if "User" in cmd else "active"))
            stack.enter_context(patch.object(release,"verify_database_configuration"))
            stack.enter_context(patch.object(release,"patch_sources",return_value=modified))
            stack.enter_context(patch.object(release,"healthy",return_value=health))
            stack.enter_context(patch.object(release.urllib.request,"urlopen",side_effect=fetch))
            stack.enter_context(patch.object(release.time,"sleep"))
            try:
                yield app,db,originals,payload,modified
            finally:
                os.umask(before_umask)

    def test_success_and_manual_rollback_preserve_later_payments(self):
        with self.fixture_installation() as (app,db,originals,payload,modified):
            release.install()
            for name,raw in {**payload,**modified}.items():
                self.assertEqual((app/name).read_bytes(),raw)
            for name in originals:
                self.assertEqual((app/name).stat().st_mode & 0o777,0o640)
            with sqlite3.connect(db) as conn:
                conn.execute("INSERT INTO payments VALUES(15000)")
            with patch.object(sys,"argv",["installer",release.RELEASE_ID+"-ROLLBACK"]):
                release.rollback_last()
            for name,raw in originals.items():
                self.assertEqual((app/name).read_bytes(),raw)
            self.assertTrue(all(not (app/name).exists() for name in payload))
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT amount FROM payments").fetchall(),[(13200,),(15000,)])
                self.assertEqual(conn.execute("SELECT public_active FROM channel_trainer_catalog_settings WHERE code='decomposition'").fetchone(),(0,))

    def test_failed_health_restores_original_code_and_keeps_database(self):
        with self.fixture_installation(health=False) as (app,db,originals,payload,_modified):
            with self.assertRaises(ValueError):
                release.install()
            for name,raw in originals.items():
                self.assertEqual((app/name).read_bytes(),raw)
            self.assertTrue(all(not (app/name).exists() for name in payload))
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT amount FROM payments").fetchall(),[(13200,)])

    def test_failure_after_first_atomic_write_is_rolled_back(self):
        with self.fixture_installation() as (app,_db,originals,payload,_modified):
            original_write=release.atomic_write
            first=True
            def fail_after_write(*args):
                nonlocal first
                original_write(*args)
                if first:
                    first=False
                    raise OSError("synthetic fsync failure after rename")
            with patch.object(release,"atomic_write",side_effect=fail_after_write):
                with self.assertRaises(OSError):
                    release.install()
            for name,raw in originals.items():
                self.assertEqual((app/name).read_bytes(),raw)
            self.assertTrue(all(not (app/name).exists() for name in payload))


if __name__=="__main__":
    unittest.main()
