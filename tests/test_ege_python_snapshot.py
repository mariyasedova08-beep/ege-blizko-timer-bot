import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

snapshot = load("seal_ege_python_snapshot")
encrypted = load("seal_decomposition_routing_copy")
with patch.dict(sys.modules, {"seal_decomposition_routing_copy": encrypted}):
    transport = load("capture_ege_python_snapshot")


class PythonSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = b"raise RuntimeError('MUST_NOT_EXECUTE')\n"
        (self.root / "fixture.py").write_bytes(self.raw)
        (self.root / ".env").write_text("DO_NOT_COPY")
        (self.root / "students.sqlite").write_text("DO_NOT_COPY")
        (self.root / "bank.json").write_text("DO_NOT_COPY")
        self.report = {"modules": {"fixture": {
            "status": "present", "sha256": encrypted.digest(self.raw), "bytes": len(self.raw)}}}
        self.pin = encrypted.digest(json.dumps(
            snapshot.manifest(self.report), sort_keys=True, separators=(",", ":")).encode())

    def collect(self, report=None):
        return snapshot.collect(self.report if report is None else report, self.root,
                                encrypted.open_directory, expected_digest=self.pin, expected_count=1)

    def test_only_exact_python_bytes_and_no_execution_or_assets(self):
        result = json.loads(self.collect())
        self.assertEqual(set(result["modules"]), {"fixture.py"})
        self.assertEqual(base64.b64decode(result["modules"]["fixture.py"]["content_b64"]), self.raw)
        self.assertFalse(result["complete_runnable_snapshot"])
        self.assertFalse(result["assets_included"])
        self.assertFalse(result["databases_included"])
        self.assertNotIn(b"DO_NOT_COPY", self.collect())

    def test_manifest_drift_and_unapproved_names_stop_before_source_read(self):
        report = json.loads(json.dumps(self.report))
        report["modules"]["fixture"]["sha256"] = "0" * 64
        with patch.object(snapshot.os, "open") as op:
            with self.assertRaises(ValueError):
                self.collect(report)
            op.assert_not_called()
        for name in ("../secret", ".env", "folder/file"):
            with self.assertRaises(ValueError):
                snapshot.manifest({"modules": {name: self.report["modules"]["fixture"]}})
        self.report["modules"]["fixture"]["status"] = "missing"
        with self.assertRaises(ValueError):
            self.collect()

    def test_source_drift_symlink_and_fifo_rejected(self):
        file = self.root / "fixture.py"
        file.write_bytes(self.raw.replace(b"raise", b"print"))
        with self.assertRaises(ValueError):
            self.collect()
        file.unlink()
        file.symlink_to(self.root / ".env")
        with self.assertRaises(OSError):
            self.collect()
        file.unlink()
        os.mkfifo(file)
        with self.assertRaises(ValueError):
            self.collect()

    def test_source_changes_during_read_rejected(self):
        original = os.read
        changed = False
        def race(fd, size):
            nonlocal changed
            result = original(fd, size)
            if not changed:
                changed = True
                with (self.root / "fixture.py").open("ab") as stream:
                    stream.write(b"#changed")
            return result
        with patch.object(snapshot.os, "read", side_effect=race):
            with self.assertRaises(ValueError):
                self.collect()

    def test_size_and_count_limits(self):
        with patch.object(snapshot, "MAX_SOURCE_BYTES", 1):
            with self.assertRaises(ValueError):
                self.collect()
        with self.assertRaises(ValueError):
            snapshot.collect(self.report,self.root,encrypted.open_directory,
                             expected_digest=self.pin,expected_count=2)

    def test_transport_pins_and_compilable_remote_payload(self):
        sources = {name:(ROOT / "deploy" / name).read_bytes() for name in transport.SOURCE_PINS}
        cert=b"PUBLIC_TEST_CERT"
        with patch.object(encrypted,"RECIPIENT_CERT_SHA256",encrypted.digest(cert)):
            with patch.object(transport.subprocess,"run",
                              return_value=subprocess.CompletedProcess([],0,b"",b"")):
                compile(transport.remote_payload(cert,sources),"<remote>","exec")
                sources["seal_ege_python_snapshot.py"] += b"#changed"
                with self.assertRaises(ValueError):
                    transport.remote_payload(cert,sources)
        with self.assertRaises(ValueError):
            transport.remote_payload(b"WRONG_CERT",sources)

    def test_transport_failure_and_wrong_target_do_not_write_output(self):
        out=self.root / "result.cms"
        args=dict(key="synthetic",known_hosts="synthetic",host="other",user="root",output=out)
        with patch.object(transport.subprocess,"run") as run:
            with self.assertRaises(ValueError):
                transport.capture(b"",{},**args)
            run.assert_not_called()
        args.update(host="77.233.212.200",user="ege-deploy")
        with patch.object(transport,"remote_payload",return_value=b"TRUSTED_SYNTHETIC_PAYLOAD"):
            with patch.object(transport.subprocess,"run",
                              return_value=subprocess.CompletedProcess([],1,b"PRIVATE_SOURCE",b"PRIVATE_ERROR")):
                with self.assertRaises(ValueError):
                    transport.capture(b"",{},**args)
        self.assertFalse(out.exists())

    def test_transport_fixed_command_and_exclusive_ciphertext(self):
        out=self.root / "result.cms"
        with patch.object(transport,"remote_payload",return_value=b"TRUSTED_SYNTHETIC_PAYLOAD"):
            with patch.object(transport.subprocess,"run",side_effect=[
                subprocess.CompletedProcess([],0,b"\x30CMS",b""),
                subprocess.CompletedProcess([],0,b"",b""),
            ]) as run:
                transport.capture(b"",{},key="synthetic",known_hosts="pinned",
                                  host="77.233.212.200",user="ege-deploy",output=out)
                cmd=run.call_args_list[0].args[0]
                self.assertEqual(cmd[-1],"python3 - --mode remote")
                self.assertIn("StrictHostKeyChecking=yes",cmd)
        self.assertEqual(out.read_bytes(),b"\x30CMS")
        self.assertEqual(out.stat().st_mode & 0o777,0o600)


if __name__ == "__main__":
    unittest.main()
