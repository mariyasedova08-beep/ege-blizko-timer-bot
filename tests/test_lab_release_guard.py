"""Read-only regression checks for the EGE BLIZKO laboratory release.

This suite never imports the bot or touches SQLite/Telegram/server state.
"""
import ast
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "ege_lab_webapp.py"


def literal_assignment(file_name, variable):
    tree = ast.parse((ROOT / file_name).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except (TypeError, ValueError):
            continue
    raise AssertionError(f"{variable} literal missing in {file_name}")


class LaboratoryReleaseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab_source = LAB.read_text(encoding="utf-8")
        cls.reagents = literal_assignment("ege_lab_substances.py", "REAGENTS")
        cls.reactions = (
            literal_assignment("ege_lab_webapp.py", "REACTIONS")
            + literal_assignment("ege_lab_inorganic_reactions.py", "EXTRA_REACTIONS")
            + literal_assignment("ege_task6_reactions.py", "TASK6_REACTIONS")
        )
        cls.variants = (
            literal_assignment("ege_lab_inorganic_reactions.py", "REACTION_VARIANTS")
            + literal_assignment("ege_task6_reactions.py", "TASK6_VARIANTS")
        )
        cls.html = literal_assignment("ege_lab_webapp.py", "HTML")

    def test_catalogue_coverage_not_reduced(self):
        self.assertEqual(len(self.reagents), 195)
        self.assertEqual(len(self.reactions) + len(self.variants), 435)

    def test_reaction_references_and_shapes(self):
        known = set(self.reagents)
        for rx in self.reactions:
            self.assertEqual(len(rx), 9, rx)
            self.assertIn(rx[0], known)
            self.assertIn(rx[1], known)
        for rx in self.variants:
            self.assertIn(rx["a"], known)
            self.assertIn(rx["b"], known)
            if rx.get("excess"):
                self.assertIn(rx["excess"], known)

    def test_gel_visualization_and_colour_source(self):
        # Both Cu(OH)2 and Fe(OH)2 should use soft clouds, not round bubbles.
        self.assertIn(r"cu\(oh\)[₂2]|fe\(oh\)[₂2]", self.html)
        self.assertIn('class="gel-bed"', self.html)
        self.assertIn('class="gel-cloud"', self.html)
        self.assertIn("@keyframes gelCloudSettle", self.html)
        self.assertIn("--pc:'+x.ppt", self.html)

    def test_existing_modes_and_gas_effects_remain(self):
        for marker in (
            "function bubblesHTML(x)",
            "function renderTubes()",
            "function setupMobileTubePicker()",
            '"task6":TASK6_BANK',
            '"oge12":_oge12_bank_payload()',
            '"oge23":_oge23_bank_payload()',
            "function reactionResultHTML(",
        ):
            self.assertIn(marker, self.lab_source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JS syntax checks")
    def test_embedded_javascript_syntax(self):
        scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", self.html)
        self.assertTrue(any(part.strip() for part in scripts))
        with tempfile.TemporaryDirectory() as tempdir:
            for index, script in enumerate(scripts):
                if not script.strip():
                    continue
                target = Path(tempdir) / f"lab_inline_{index}.js"
                target.write_text(script, encoding="utf-8")
                process = subprocess.run(
                    ["node", "--check", str(target)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
