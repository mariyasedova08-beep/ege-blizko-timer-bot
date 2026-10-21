"""Offline checks for Telegram chemistry decomposition trainer bank."""
import ast
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

    def test_handler_has_no_webapp_and_compiles(self):
        source = Path(__file__).resolve().parents[1].joinpath("decomposition_trainer.py")
        text = source.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertNotIn("WebAppInfo", text)
        self.assertNotIn("send_document", text)


if __name__ == "__main__":
    unittest.main()
