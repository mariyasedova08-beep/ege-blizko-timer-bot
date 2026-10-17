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
        self.assertEqual(len(d["anions"]), 25)
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
        self.assertEqual(cells["OH"]["Fe2"], "H")  # Fe(OH)₂ insoluble
        self.assertEqual(cells["OH"]["Fe3"], "H")  # Fe(OH)₃ insoluble
        self.assertEqual(cells["S"]["Hg"], "H")  # HgS insoluble
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
        self.assertEqual(self.data["precipitates"]["Fe2|OH"][0], "серо-зелёный")
        self.assertEqual(self.data["precipitates"]["Fe3|OH"][0], "бурый")


    def test_hydrolysis_and_redox_as_in_teacher_table(self):
        d = self.data
        h = d["hydrolysis"]
        self.assertEqual(len(h), 18)
        for c in ("Al", "Cr3"):
            for a in ("CO3", "HCO3", "S", "HS", "SO3", "HSO3"):
                row = h[c + "|" + a]
                self.assertEqual(row["display"], "↑ Н ↓")
                self.assertEqual(row["kind"], "hydrolysis")
                self.assertTrue(row["ppt"])
                self.assertTrue(row["gas"])
                self.assertIn("↓", row["equation"])
                self.assertIn("↑", row["equation"])
        for a in ("CO3", "HCO3"):
            self.assertEqual(h["Fe3|" + a]["display"], "↑ Н ↓")
        for a in ("S", "HS", "SO3", "HSO3"):
            self.assertEqual(h["Fe3|" + a]["display"], "ОВР")
            self.assertEqual(h["Fe3|" + a]["kind"], "redox")
            self.assertIn("2Fe³⁺", h["Fe3|" + a]["equation"])
            self.assertEqual(h["Fe3|" + a]["gas"], None)
        self.assertEqual(d["cells"]["HSO3"]["NH4"], "?")
        self.assertIn("↑ Н ↓", self.html)
        self.assertIn('id="gasBubbles"', self.html)
        for c in ("Rb", "Cs", "Be", "Cr2"):
            self.assertFalse(next(x for x in d["cations"] if x["id"] == c)["reference"])

    def test_read_only_public_route(self):
        self.assertNotIn("/lab-app/api", self.html)
        self.assertNotIn("initData", self.html)
        self.assertIn('href="/lab-app"', self.html)
        self.assertIn('data-pair', self.html)


if __name__ == "__main__":
    unittest.main()
