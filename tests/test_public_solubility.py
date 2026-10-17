"""Contract tests for the public read-only solubility table."""
import json
import re
import unittest
from pathlib import Path

PUBLIC_HTML = Path(__file__).resolve().parents[1] / "ege_lab_solubility_public.html"


class PublicSolubilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PUBLIC_HTML.read_text(encoding="utf-8")
        match = re.search(r"const D=(\{.*?\});\s*const subs=", cls.html, re.S)
        assert match, "Reference data missing"
        cls.data = json.loads(match.group(1))

    def test_full_matrix_and_reference_count(self):
        d = self.data
        self.assertEqual(len(d["cations"]), 24)
        self.assertEqual(len(d["anions"]), 24)
        columns = [c["id"] for c in d["cations"] if c["reference"]]
        self.assertEqual(len(columns), 20)
        self.assertEqual(
            sum(d["cells"][a["id"]][c] == "H" for a in d["anions"] for c in columns),
            98,
        )
        for a in d["anions"]:
            self.assertEqual(len(d["cells"][a["id"]]), 24)

    def test_teacher_chemistry_and_colour_corrections(self):
        cells = self.data["cells"]
        self.assertEqual(cells["OH"]["Ca"], "M")
        self.assertEqual(cells["OH"]["Sr"], "M")
        self.assertEqual(cells["OH"]["Ba"], "P")
        self.assertEqual(cells["NO3"]["NH4"], "P")
        self.assertEqual(cells["NO3"]["Be"], "P")
        self.assertEqual(cells["PO4"]["NH4"], "P")
        self.assertEqual(cells["S"]["Al"], "—")
        self.assertEqual(cells["S"]["Fe3"], "—")
        for c in ["Fe2", "Ag", "Hg", "Pb"]:
            self.assertEqual(cells["S"][c], "H")
        self.assertEqual(self.data["precipitates"]["Ag|Br"][0], "светло-жёлтый")
        self.assertEqual(self.data["precipitates"]["Ag|S"][0], "чёрный")
        self.assertEqual(self.data["precipitates"]["Hg|S"][0], "чёрный")

    def test_read_only_public_route(self):
        self.assertNotIn("/lab-app/api", self.html)
        self.assertNotIn("initData", self.html)
        self.assertIn('href="/lab-app"', self.html)
        self.assertIn('data-pair', self.html)


if __name__ == "__main__":
    unittest.main()
