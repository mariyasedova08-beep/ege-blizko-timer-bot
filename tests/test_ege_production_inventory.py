"""Local-only tests for the allowlisted production inventory."""
import importlib.util
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "ege-blizko-production-inventory.py"
spec = importlib.util.spec_from_file_location("ege_production_inventory", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProductionInventoryTests(unittest.TestCase):
    def test_allowlist_is_not_sensitive(self):
        self.assertTrue(module.FILES)
        self.assertEqual(len(module.FILES), len(set(module.FILES)))
        for name in module.FILES:
            self.assertEqual(pathlib.PurePath(name).name, name)
            self.assertTrue(name.endswith(".py"))
            self.assertNotIn("secret", name.lower())
            self.assertNotIn("env", name.lower())

    def test_sha256_and_absent_file(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            self.assertEqual(module.file_digest(directory, "run_bot_live7.py"), "MISSING")
            (directory / "run_bot_live7.py").write_bytes(b"small test sample")
            self.assertEqual(
                module.file_digest(directory, "run_bot_live7.py"),
                "fbdd34054093a87cb14d12ecdcc33de040da487ae4e60f5c397c588b97edae84",
            )

    def test_refuses_symlinked_source(self):
        with tempfile.TemporaryDirectory() as root:
            directory = pathlib.Path(root)
            (directory / "outside.py").write_text("SECRET = 'not read'")
            (directory / "run_bot_live7.py").symlink_to(directory / "outside.py")
            with self.assertRaisesRegex(ValueError, "SYMLINK_FILE_FORBIDDEN"):
                module.file_digest(directory, "run_bot_live7.py")

    def test_compare_does_not_merge_drift(self):
        same = "a" * 64
        altered = "b" * 64
        local = {name: same for name in module.FILES}
        server = dict(local)
        local["oge9_trainer_notifications.py"] = module.MISSING
        server["run_bot_live7.py"] = altered
        server["oge9_trainer_notifications.py"] = same
        server["ege11_lesson_transfer.py"] = module.MISSING
        result = module.compare(local, server)
        self.assertIn("run_bot_live7.py", result["different"])
        self.assertIn("oge9_trainer_notifications.py", result["only_server"])
        self.assertIn("ege11_lesson_transfer.py", result["only_github"])

    def test_parser_rejects_incomplete_and_extra_output(self):
        with self.assertRaises(ValueError):
            module.read_inventory("FILE\tunexpected_secret\tdeadbeef")
        rows = "\n".join(module.lines_for_inventory({name: module.MISSING for name in module.FILES}))
        data, state = module.read_inventory(rows + "\nSERVICE\tactive\n")
        self.assertEqual(len(data), len(module.FILES))
        self.assertEqual(state, "active")
        with self.assertRaises(ValueError):
            module.read_inventory(rows + "\nFILE\trun_bot_live7.py\tMISSING\n")
        with self.assertRaises(ValueError):
            module.read_inventory(rows + "\nFILE\trun_bot_live7.py\tbogus\n")


if __name__ == "__main__":
    unittest.main()
