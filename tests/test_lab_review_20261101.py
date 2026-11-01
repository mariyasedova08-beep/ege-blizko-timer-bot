"""Full payload chemistry checks, without bot imports or database access."""
import re
import unittest
from lab_isolated_data import load_candidate
from test_lab_redox_exchange_expansion import check_balanced

class CandidateReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_candidate()
        cls.payload = cls.data['reaction_payload']()

    def test_every_actual_payload_equation_and_stage_conserves_atoms(self):
        equations = []
        for row in self.payload + self.data['MEDIUM_REACTIONS']:
            if row['t'] == 'z':
                continue
            equations.append(row['eq'])
            equations.extend(row.get('stages', {}).values())
        for equation in equations:
            # Remove condition annotations, keeping chemical parentheses intact.
            clean = re.sub(r'\((?:разб\.|конц\.|конц\., холодн\.|нед\.|изб\.)\)', '', equation)
            clean = clean.replace(' ⇄ ', ' → ')
            with self.subTest(equation=equation):
                check_balanced(clean)
        print('FULL_PAYLOAD_BALANCE_OK', len(equations), 'equations/stages')

    def test_acid_salts_with_other_alkali_use_two_medium_salts(self):
        expected = {
            frozenset(('nahco3','koh')): '2NaHCO₃ + 2KOH → Na₂CO₃ + K₂CO₃ + 2H₂O',
            frozenset(('khso3','naoh')): '2KHSO₃ + 2NaOH → K₂SO₃ + Na₂SO₃ + 2H₂O',
            frozenset(('kh2po4','naoh')): '3KH₂PO₄ + 6NaOH → K₃PO₄ + 2Na₃PO₄ + 6H₂O',
        }
        for pair, equation in expected.items():
            rows = [r for r in self.payload if frozenset((r['a'],r['b'])) == pair]
            self.assertTrue(rows)
            self.assertTrue(all(r['eq'] == equation for r in rows))
        self.assertFalse(any(re.search(r'NaKCO₃|KNaSO₃|KNa₂PO₄',r['eq']) for r in self.payload))

    def test_references_and_medium_are_complete(self):
        for row in self.payload + self.data['MEDIUM_REACTIONS']:
            self.assertIn(row['a'], self.data['REAGENTS'])
            self.assertIn(row['b'], self.data['REAGENTS'])
        print('CANDIDATE_COVERAGE', len(self.data['REAGENTS']), len(self.payload), len(self.data['MEDIUM_REACTIONS']))
