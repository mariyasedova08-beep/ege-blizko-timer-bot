"""Chemistry regressions for the November classroom feedback, without the bot."""
import unittest
from lab_isolated_data import load_candidate


class ClassroomFeedback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_candidate()

    def test_manganate_sulfite_has_distinct_acid_and_mno2_products(self):
        for a,b in [('k2mno4','k2so3'),('na2mno4','na2so3')]:
            rows = [r for r in self.data['MEDIUM_REACTIONS'] if r['a']==a and r['b']==b]
            self.assertEqual({r['medium'] for r in rows},{'acid','neutral','alkaline','weak_alkaline'})
            for r in rows:
                self.assertIn('Зелёная', r['sign'])
                self.assertNotIn('фиолет', r['sign'].lower())
                self.assertFalse(r['heat'])
                self.assertFalse(r['gas'])
                if r['medium']=='acid':
                    self.assertIn('MnSO₄',r['eq']); self.assertFalse(r['ppt'])
                else:
                    self.assertIn('MnO₂↓',r['eq']); self.assertTrue(r['ppt'])

    def test_permanganate_hcl_direct_reaction_without_extra_acid(self):
        rows = [r for r in self.data['reaction_payload']() if {r['a'],r['b']}=={'kmno4','hcl'}]
        self.assertEqual(len(rows),1)
        r=rows[0]
        self.assertIn('16HCl',r['eq']);self.assertIn('5Cl₂',r['eq'])
        self.assertEqual(r['gas'],'Cl₂');self.assertFalse(r['heat'])
