"""Local checks only; no VPS access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "deploy/ege-sealed-source-diff.py"
spec = importlib.util.spec_from_file_location("sealed_diff", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SealedDiffTests(unittest.TestCase):
    def test_allowlist_and_no_paths_outside_working_dir(self):
        self.assertEqual(len(module.FILES), 7)
        self.assertEqual(len(set(module.FILES)), len(module.FILES))
        for name in module.FILES:
            self.assertEqual(Path(name).name, name)
            self.assertTrue(name.endswith(".py"))

    def test_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / "data.py").write_text("a = 1")
            (directory / module.FILES[0]).symlink_to(directory / "data.py")
            with self.assertRaisesRegex(ValueError, "SYMLINK_DENIED"):
                module.read_limited(directory, module.FILES[0])

    def test_public_certificate_is_exact_expected_recipient(self):
        import hashlib
        import subprocess
        certificate = REPO / "deploy/sealed-audit-public-cert.crt"
        self.assertEqual(
            hashlib.sha256(certificate.read_bytes()).hexdigest(),
            "fe1f46e8f15ae494bef7280ab5491bf3a243a9e5c7c124bbc294bdf462754d6b",
        )
        self.assertEqual(
            subprocess.run(
                ["openssl", "x509", "-in", str(certificate), "-noout", "-checkend", "0"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            ).returncode, 0,
        )

    def test_encrypted_cms_is_not_plaintext(self):
        certificate = (REPO / "deploy/sealed-audit-public-cert.crt").read_bytes()
        clear = b"not-for-github-logs SECRET_CANARY_VALUE"
        ciphertext = module.encrypt_in_memory(clear, certificate)
        self.assertTrue(ciphertext.startswith(b"\x30"))
        self.assertNotIn(clear, ciphertext)
        self.assertGreater(len(ciphertext), len(clear))

    def test_absent_source_is_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(module.read_limited(Path(root), module.FILES[0]))


if __name__ == "__main__":
    unittest.main()
