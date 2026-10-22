"""Offline checks for Telegram chemistry decomposition trainer bank."""
import ast
import re
from collections import Counter
import unittest
from pathlib import Path

from decomposition_trainer_bank import (
    DECOMPOSITION_BANK,
    DECOMPOSITION_GROUPS,
    DECOMPOSITION_EXPLANATIONS,
)


class DecompositionBankTest(unittest.TestCase):
    def test_exactly_fifty_unique_questions(self):
        self.assertEqual(len(DECOMPOSITION_BANK), 50)
        self.assertEqual(len({q[0] for q in DECOMPOSITION_BANK}), 50)

    def test_both_modes_have_25(self):
        groups = list(DECOMPOSITION_GROUPS.values())
        self.assertEqual(groups.count("ovr"), 25)
        self.assertEqual(groups.count("non_ovr"), 25)

    def test_four_distinct_choices_and_complete_equations(self):
        for qid, prompt, correct, wrong in DECOMPOSITION_BANK:
            with self.subTest(qid=qid):
                self.assertTrue(prompt)
                self.assertEqual(len(wrong), 3)
                self.assertEqual(len({correct, *wrong}), 4)
                self.assertIn("→", DECOMPOSITION_EXPLANATIONS[qid])
                self.assertIn("ОВР", DECOMPOSITION_EXPLANATIONS[qid])

    def test_chemical_edge_cases(self):
        self.assertIn("2CuO", DECOMPOSITION_EXPLANATIONS["decomp016"])  # malachite
        self.assertIn("MnO₂ + 2NO₂", DECOMPOSITION_EXPLANATIONS["decomp038"])
        self.assertNotIn("MnO₂ + 2NO₂ + O₂", DECOMPOSITION_EXPLANATIONS["decomp038"])
        self.assertIn("K₂MnO₄ + MnO₂ + O₂", DECOMPOSITION_EXPLANATIONS["decomp047"])
        self.assertIn("2KCl + 3O₂", DECOMPOSITION_EXPLANATIONS["decomp048"])
        self.assertIn("KCl + 3KClO₄", DECOMPOSITION_EXPLANATIONS["decomp049"])


    def test_all_equations_balance_and_match_the_correct_products(self):
        digits = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

        def atoms(formula):
            tokens = re.findall(r"[A-Z][a-z]?|[0-9]+|[()]", formula)
            self.assertEqual("".join(tokens), formula)
            stack = [Counter()]
            i = 0
            while i < len(tokens):
                token = tokens[i]
                i += 1
                if token == "(":
                    stack.append(Counter())
                    continue
                if token == ")":
                    item = stack.pop()
                else:
                    self.assertRegex(token, r"^[A-Z][a-z]?$")
                    item = Counter({token: 1})
                factor = 1
                if i < len(tokens) and tokens[i].isdigit():
                    factor = int(tokens[i])
                    i += 1
                stack[-1].update({atom: count * factor for atom, count in item.items()})
            self.assertEqual(len(stack), 1)
            return stack[0]

        def side(text):
            total, products = Counter(), set()
            for term in text.translate(digits).split(" + "):
                match = re.fullmatch(r"(\d*)(.+)", term.strip())
                factor, formula = match.groups()
                products.add(formula)
                total.update({atom: count * int(factor or 1) for atom, count in atoms(formula).items()})
            return total, products

        for qid, _prompt, correct, _wrong in DECOMPOSITION_BANK:
            with self.subTest(qid=qid):
                equation = DECOMPOSITION_EXPLANATIONS[qid].splitlines()[0]
                left, right = equation.split(" → ")
                self.assertEqual(side(left)[0], side(right)[0])
                self.assertEqual(side(right)[1], side(correct)[1])

    def test_multistage_questions_state_the_requested_endpoint(self):
        prompts = {qid: prompt for qid, prompt, _correct, _wrong in DECOMPOSITION_BANK}
        self.assertIn("кипячении раствора", prompts["decomp015"])
        self.assertIn("полном разложении", prompts["decomp022"])
        self.assertIn("до образования Na₂SO₃", prompts["decomp025"])
        self.assertIn("до оксида свинца(II)", prompts["decomp044"])
        self.assertIn("до оксида хрома(III)", prompts["decomp045"])

    def test_handler_has_no_webapp_and_compiles(self):
        source = Path(__file__).resolve().parents[1].joinpath("decomposition_trainer.py")
        text = source.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertNotIn("WebAppInfo", text)
        self.assertNotIn("send_document", text)


if __name__ == "__main__":
    unittest.main()
