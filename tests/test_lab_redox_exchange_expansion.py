"""Validate the priority Mn(VII)/Cr(VI) and exchange/replacement chemistry."""
from collections import Counter
from pathlib import Path
import re
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHEM = runpy.run_path(str(ROOT / "ege_lab_inorganic_reactions.py"))
REAGENTS = runpy.run_path(str(ROOT / "ege_lab_substances.py"))["REAGENTS"]
SUBS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def atoms(formula):
    formula = re.sub(r"\((?:конц\.|нед\.|изб\.)\)", "", formula).translate(SUBS).replace("↓", "").replace("↑", "").strip()
    if not formula:
        raise ValueError("empty formula")
    if "·" in formula:
        total = Counter()
        for component in formula.split("·"):
            total.update(atoms(component))
        return total
    stack = [Counter()]
    i = 0
    while i < len(formula):
        ch = formula[i]
        if ch in "([":
            stack.append(Counter())
            i += 1
        elif ch in ")]":
            if len(stack) <= 1:
                raise ValueError(f"bad bracket {formula}")
            i += 1
            m = re.match(r"\d+", formula[i:])
            n = int(m.group()) if m else 1
            i += len(m.group()) if m else 0
            group = stack.pop()
            stack[-1].update({key: val*n for key, val in group.items()})
        elif ch.isupper() and ch.isascii():
            j = i + 1
            if j < len(formula) and formula[j].islower():
                j += 1
            symbol = formula[i:j]
            m = re.match(r"\d+", formula[j:])
            n = int(m.group()) if m else 1
            stack[-1][symbol] += n
            i = j + (len(m.group()) if m else 0)
        else:
            raise ValueError(f"unknown formula character {ch} in {formula}")
    if len(stack) != 1:
        raise ValueError(f"unclosed formula {formula}")
    return stack[0]


def side_atoms(side):
    total = Counter()
    for fragment in side.split(" + "):
        m = re.fullmatch(r"\s*(\d+)?\s*([A-Za-z₀-₉()\[\]↓↑·]+)\s*", fragment)
        if not m:
            raise ValueError(f"bad species: {fragment}")
        n = int(m[1]) if m[1] else 1
        total.update({atom: count*n for atom, count in atoms(m[2]).items()})
    return total


def check_balanced(equation):
    equation = re.sub(r"\((?:конц|нед|изб)\.\)", "", equation)
    lhs, rhs = equation.replace(" —t°→ ", " → ").split(" → ")
    a, b = side_atoms(lhs), side_atoms(rhs)
    if a != b:
        raise AssertionError(f"Not balanced: {equation}\nleft: {a}\nright: {b}")


class PriorityChemistry(unittest.TestCase):
    def test_curated_count_and_identifiers(self):
        medium = CHEM["MEDIUM_REACTIONS"]
        self.assertEqual(len(medium), 91)
        for row in medium:
            self.assertIn(row["a"], REAGENTS)
            self.assertIn(row["b"], REAGENTS)
            self.assertIn(row["medium"], {"acid", "neutral", "alkaline", "weak_alkaline"})
            self.assertTrue(row["condition"])
            self.assertTrue(row["sign"])
        CHEM["validate_reactions"](set(REAGENTS))

    def test_all_oxidizer_equations_balance(self):
        for entry in CHEM["MEDIUM_REACTIONS"]:
            with self.subTest(pair=(entry["a"], entry["b"], entry["medium"])):
                check_balanced(entry["eq"])

    def test_new_exchange_replacement_equations_balance(self):
        extra = CHEM["EXTRA_REACTIONS"]
        expected_pairs = {
            frozenset(("k2cro4", "pbno3")),
            frozenset(("k2cro4", "agno3")),
            frozenset(("mg", "znso4")),
            frozenset(("fe", "pbno3")),
            frozenset(("zn", "pbno3")),
            frozenset(("fecl2", "na2s")),
            frozenset(("alcl3", "na2co3")),
            frozenset(("agno3", "k2co3")),
            frozenset(("mg", "pbno3")),
            frozenset(("crcl3", "naoh")),
            frozenset(("crcl3", "koh")),
            frozenset(("crcl3", "nh3")),
            frozenset(("crcl3", "na2co3")),
            frozenset(("crno3_3", "naoh")),
            frozenset(("cr2so43", "naoh")),
            frozenset(("croh3", "hno3")),
            frozenset(("croh3", "h2so4")),
            frozenset(("croh3", "koh")),
            frozenset(("cr2o3", "h2so4")),
            frozenset(("fecl2", "na2co3")),
            frozenset(("feso4", "na2co3")),
            frozenset(("cl2", "nabr")),
        }
        added = [row for row in extra if frozenset(row[:2]) in expected_pairs]
        self.assertEqual(len(added), len(expected_pairs))
        for row in added:
            with self.subTest(reaction=row[2]):
                check_balanced(row[2])

    def test_documented_absent_reactions_are_not_missing_data(self):
        extra = CHEM["EXTRA_REACTIONS"]
        for a, b in [
            ("fe", "mgso4"), ("cu", "pbno3"),
            ("br2", "kcl"), ("i2", "kbr"),
        ]:
            with self.subTest(pair=(a, b)):
                matching = [x for x in extra if frozenset(x[:2]) == frozenset((a, b))]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0][3], "z")

    def test_chromium_three_alkaline_oxidation_requires_heat(self):
        matching = [m for m in CHEM["MEDIUM_REACTIONS"] if
                    m["a"] in {"croh3", "crcl3"} and m["b"] == "h2o2"]
        self.assertEqual(len(matching), 2)
        for row in matching:
            self.assertEqual(row["medium"], "alkaline")
            self.assertTrue(row["heat"])
            self.assertIn("Na₂CrO₄", row["eq"])
            self.assertEqual(row["sol"], "#f5d532")

    def test_two_uploaded_pdf_files_have_complete_audit(self):
        pdf = runpy.run_path(str(ROOT / "ege_lab_mn_cr_pdf_import.py"))
        audit = pdf["SOURCE_AUDIT"]
        sources = pdf["SOURCE_RECORDS"]
        self.assertEqual(audit["source_total"], 87)
        self.assertEqual(len(sources), 87)
        self.assertEqual(sum(audit["by_status"].values()), 87)
        self.assertEqual(audit["by_status"]["imported"], 68)
        self.assertEqual(audit["by_status"]["already_in_lab"], 16)
        self.assertEqual(audit["by_status"]["duplicate_in_pdf"], 1)
        self.assertEqual(audit["by_status"]["needs_chemical_review"], 2)
        self.assertEqual(len(pdf["PDF_MEDIUM_REACTIONS"]), 65)
        self.assertEqual(len(pdf["PDF_EXTRA_REACTIONS"]), 3)
        for source in sources:
            with self.subTest(id=source["source_id"]):
                self.assertIn(source["page"], range(1, 9))
                self.assertIn(source["status"], {"imported", "already_in_lab",
                                              "duplicate_in_pdf", "needs_chemical_review"})
                self.assertIn("→", source["eq"])
                check_balanced(source["eq"])

    def test_pdf_imported_ordinary_reactions_balance(self):
        pdf = runpy.run_path(str(ROOT / "ege_lab_mn_cr_pdf_import.py"))
        for a,b,eq,*_ in pdf["PDF_EXTRA_REACTIONS"]:
            with self.subTest(pair=(a,b)):
                self.assertIn(a, REAGENTS)
                self.assertIn(b, REAGENTS)
                check_balanced(eq)

    def test_source_records_reconcile_with_lab_registry(self):
        pdf = runpy.run_path(str(ROOT / "ege_lab_mn_cr_pdf_import.py"))
        imported = [x for x in pdf["SOURCE_RECORDS"] if x["status"] == "imported"]
        keys_medium = {(frozenset((x["a"],x["b"])),x["medium"]) for x in CHEM["MEDIUM_REACTIONS"]}
        keys_ordinary = {frozenset((x[0],x[1])) for x in CHEM["EXTRA_REACTIONS"]}
        for row in imported:
            with self.subTest(id=row["source_id"]):
                if row["medium"] == "ordinary":
                    self.assertIn(frozenset((row["a"],row["b"])),keys_ordinary)
                else:
                    self.assertIn((frozenset((row["a"],row["b"])),row["medium"]),keys_medium)
        for item in pdf["SOURCE_RECORDS"]:
            if item["status"] == "needs_chemical_review":
                self.assertNotIn(item["source_id"],{x.get("source_id") for x in pdf["PDF_MEDIUM_REACTIONS"]})

    def test_dichromate_and_chromate_remain_separate(self):
        medium = CHEM["MEDIUM_REACTIONS"]
        self.assertTrue(any(x["a"] == "k2cr2o7" for x in medium))
        self.assertTrue(any(x["a"] == "k2cro4" for x in medium))
        self.assertEqual(
            [x["medium"] for x in medium if x["a"] == "kmno4" and x["b"] == "h2o2"],
            ["acid", "neutral", "alkaline"],
        )


if __name__ == "__main__":
    unittest.main()
