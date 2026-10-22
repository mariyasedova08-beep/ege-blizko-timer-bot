"""Offline tests: synthetic source and disposable encryption keys only."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "routing_copy", ROOT / "deploy/seal_decomposition_routing_copy.py")
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)


class RoutingCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.expected = {}
        for name in copy.PINNED_FILES:
            raw = b"raise RuntimeError('SOURCE_MUST_NEVER_EXECUTE')\n"
            (self.source / name).write_bytes(raw)
            self.expected[name] = copy.digest(raw)
        (self.source / ".env").write_text("DO_NOT_EXPORT")
        (self.source / "students.sqlite").write_text("DO_NOT_EXPORT")

    def test_fixed_allowlist_no_execution_or_unrelated_data(self):
        data = json.loads(copy.collect(self.source, self.expected))
        self.assertFalse(data["complete_bot_snapshot"])
        self.assertEqual(set(data["files"]), set(copy.PINNED_FILES))
        for name, record in data["files"].items():
            self.assertEqual(base64.b64decode(record["content_b64"]),
                             (self.source / name).read_bytes())
        self.assertNotIn(b"DO_NOT_EXPORT", copy.collect(self.source, self.expected))
        with self.assertRaises(ValueError):
            copy.collect(self.source, {"../secret.py": "0" * 64})

    def test_drift_and_missing_file_stop_collection(self):
        name = next(iter(self.expected))
        (self.source / name).write_text("NEW_SERVER_CODE = True\n")
        with self.assertRaises(ValueError):
            copy.collect(self.source, self.expected)
        (self.source / name).unlink()
        with self.assertRaises(FileNotFoundError):
            copy.collect(self.source, self.expected)

    def test_symlink_root_parent_and_source_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            copy.collect(alias, self.expected)
        child = self.source / "nested"
        child.mkdir()
        with self.assertRaises(OSError):
            copy.open_directory(alias / "nested")
        name = next(iter(self.expected))
        (self.source / name).unlink()
        (self.source / name).symlink_to(self.source / next(iter(list(self.expected)[1:])))
        with self.assertRaises(OSError):
            copy.collect(self.source, self.expected)

    def test_oversize_nonregular_and_invalid_python_are_rejected(self):
        name = next(iter(self.expected))
        path = self.source / name
        path.write_bytes(b"x" * (copy.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            copy.collect(self.source, self.expected)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            copy.collect(self.source, self.expected)
        path.unlink()
        path.write_bytes(b"def broken(\n")
        expected = dict(self.expected, **{name: copy.digest(path.read_bytes())})
        with self.assertRaises(SyntaxError):
            copy.collect(self.source, expected)

    def test_change_during_read_is_rejected(self):
        name = next(iter(self.expected))
        real_read = os.read
        changed = False
        def racing_read(fd, size):
            nonlocal changed
            raw = real_read(fd, size)
            if not changed:
                changed = True
                with (self.source / name).open("ab") as stream:
                    stream.write(b"# changed\n")
            return raw
        with patch.object(copy.os, "read", side_effect=racing_read):
            with self.assertRaises(ValueError):
                copy.collect(self.source, self.expected)

    def test_wrong_recipient_and_openssl_failure_never_return_plaintext(self):
        with self.assertRaises(ValueError):
            copy.seal(b"PRIVATE_SOURCE", b"wrong certificate")
        cert = b"synthetic invalid cert"
        with self.assertRaises(ValueError):
            copy.seal(b"PRIVATE_SOURCE", cert, copy.digest(cert))

    def test_real_authenticated_encryption_roundtrip_with_disposable_key(self):
        key, cert = self.root / "key.pem", self.root / "cert.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=Disposable Offline Test",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        payload = copy.collect(self.source, self.expected)
        certificate = cert.read_bytes()
        encrypted = copy.seal(payload, certificate, copy.digest(certificate))
        self.assertNotIn(payload, encrypted)
        recovered = subprocess.run([
            "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
            "-recip", str(cert), "-inkey", str(key),
        ], input=encrypted, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.assertEqual(recovered.stdout, payload)
        damaged = bytearray(encrypted)
        damaged[-1] ^= 1
        result = subprocess.run([
            "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
            "-recip", str(cert), "-inkey", str(key),
        ], input=damaged, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)

    def test_output_exclusive_private_and_no_symlink_parent(self):
        target = self.root / "routing.cms"
        copy.write_ciphertext(target, b"ENCRYPTED_ONLY")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            copy.write_ciphertext(target, b"REPLACEMENT")
        self.assertEqual(target.read_bytes(), b"ENCRYPTED_ONLY")
        alias = self.root / "output-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            copy.write_ciphertext(alias / "new.cms", b"ENCRYPTED_ONLY")
        self.assertFalse((self.root / "new.cms").exists())


if __name__ == "__main__":
    unittest.main()
