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

    def test_encrypted_cms_is_not_plaintext(self):
        certificate = (REPO / "deploy/sealed-audit-public-cert.pem").read_bytes()
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
