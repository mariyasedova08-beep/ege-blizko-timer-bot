import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "seal_decomposition_routing_copy", ROOT / "deploy/seal_decomposition_routing_copy.py")
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)
spec = importlib.util.spec_from_file_location(
    "routing_transport", ROOT / "deploy/capture_decomposition_routing_copy.py")
transport = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"seal_decomposition_routing_copy": copy}):
    spec.loader.exec_module(transport)


class RoutingTransportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "copy.cms"
        self.exporter = (ROOT / "deploy/seal_decomposition_routing_copy.py").read_bytes()
        self.cert = b"SYNTHETIC_TEST_CERTIFICATE"
        self.cert_patch = patch.object(copy, "RECIPIENT_CERT_SHA256", copy.digest(self.cert))
        self.cert_patch.start()
        self.addCleanup(self.cert_patch.stop)

    def capture(self, **overrides):
        fields = dict(key="/tmp/synthetic-key", known_hosts="/tmp/synthetic-hosts",
                      host=transport.APPROVED_HOST, user=transport.APPROVED_USER,
                      output=self.out)
        fields.update(overrides)
        return transport.capture(self.cert, self.exporter, **fields)

    def test_exporter_pin_matches_actual_script_and_payload_is_fixed_read_only(self):
        self.assertEqual(copy.digest(self.exporter), transport.EXPORTER_SHA256)
        with patch.object(transport.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            payload = transport.remote_payload(self.cert, self.exporter)
        compile(payload, "<remote-payload>", "exec")
        self.assertTrue(payload.startswith(b"__name__ = 'routing_copy_remote_helper'"))
        self.assertIn(b"collect(Path('/opt/bots/ege-blizko'))", payload)
        self.assertIn(b"sys.stdout.buffer.write(ciphertext)", payload)

    def test_wrong_identity_certificate_exporter_and_expiry_stop_before_ssh(self):
        with patch.object(transport.subprocess, "run") as run:
            for fields in ({"host": "other.example"}, {"user": "root"}):
                with self.assertRaises(ValueError):
                    self.capture(**fields)
            with self.assertRaises(ValueError):
                transport.remote_payload(b"WRONG_CERT", self.exporter)
            with self.assertRaises(ValueError):
                transport.remote_payload(self.cert, self.exporter + b"# drift")
            run.assert_not_called()
        with patch.object(transport.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 1, b"", b"PRIVATE_DIAGNOSTIC")) as run:
            with self.assertRaises(ValueError):
                self.capture()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0:2], ["openssl", "x509"])
        self.assertFalse(self.out.exists())

    def test_transport_uses_pinned_hostkey_no_shell_and_writes_ciphertext_only(self):
        replies = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"\x30SYNTHETIC_CMS", b""),
            subprocess.CompletedProcess([], 0, b"", b""),
        ]
        with patch.object(transport.subprocess, "run", side_effect=replies) as run:
            self.capture()
        ssh_call = run.call_args_list[1]
        command = ssh_call.args[0]
        self.assertEqual(command[-2:], ["ege-deploy@77.233.212.200", "python3 - --mode remote"])
        self.assertIn("StrictHostKeyChecking=yes", command)
        self.assertIn("PasswordAuthentication=no", command)
        self.assertIn("UserKnownHostsFile=/tmp/synthetic-hosts", command)
        self.assertNotIn("shell", ssh_call.kwargs)
        self.assertEqual(self.out.read_bytes(), b"\x30SYNTHETIC_CMS")
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)

    def test_failed_ssh_timeout_plaintext_and_invalid_cms_leave_no_output(self):
        success = subprocess.CompletedProcess([], 0, b"", b"")
        for ssh_reply in (
            subprocess.CompletedProcess([], 1, b"PRIVATE_SOURCE", b"PRIVATE_ERROR"),
            subprocess.CompletedProcess([], 0, b"PRIVATE_SOURCE", b""),
            subprocess.CompletedProcess([], 0, b"\x30" * (transport.MAX_CIPHERTEXT + 1), b""),
        ):
            with self.subTest(reply_size=len(ssh_reply.stdout)):
                with patch.object(transport.subprocess, "run", side_effect=[success, ssh_reply]):
                    with self.assertRaises(ValueError):
                        self.capture()
                self.assertFalse(self.out.exists())
        with patch.object(transport.subprocess, "run", side_effect=[
            success, subprocess.TimeoutExpired(["ssh"], 90),
        ]):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.capture()
        with patch.object(transport.subprocess, "run", side_effect=[
            success, subprocess.CompletedProcess([], 0, b"\x30INVALID", b""),
            subprocess.CompletedProcess([], 1, b"", b"INVALID_CMS"),
        ]):
            with self.assertRaises(ValueError):
                self.capture()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
