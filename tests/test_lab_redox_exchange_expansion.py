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
    formula = formula.translate(SUBS).replace("↓", "").replace("↑", "").strip()
    if not formula:
        raise ValueError("empty formula")
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
        m = re.fullmatch(r"\s*(\d+)?\s*([A-Za-z₀-₉()\[\]↓↑]+)\s*", fragment)
        if not m:
            raise ValueError(f"bad species: {fragment}")
        n = int(m[1]) if m[1] else 1
        total.update({atom: count*n for atom, count in atoms(m[2]).items()})
    return total


def check_balanced(equation):
    lhs, rhs = equation.split(" → ")
    a, b = side_atoms(lhs), side_atoms(rhs)
    if a != b:
        raise AssertionError(f"Not balanced: {equation}\nleft: {a}\nright: {b}")


class PriorityChemistry(unittest.TestCase):
    def test_curated_count_and_identifiers(self):
        medium = CHEM["MEDIUM_REACTIONS"]
        self.assertEqual(len(medium), 24)
        for row in medium:
            self.assertIn(row["a"], REAGENTS)
            self.assertIn(row["b"], REAGENTS)
            self.assertIn(row["medium"], {"acid", "neutral", "alkaline"})
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
        }
        added = [row for row in extra if frozenset(row[:2]) in expected_pairs]
        self.assertEqual(len(added), len(expected_pairs))
        for row in added:
            with self.subTest(reaction=row[2]):
                check_balanced(row[2])

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
