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

    def test_oxidising_acids_have_distinct_copper_oxide_products(self):
        payload=self.data['reaction_payload']()
        for acid,gas,heat in [('h2so4_conc','SO₂',True),('hno3_conc','NO₂',False),('hno3','NO',False),('h2so4','',False)]:
            rows=[r for r in payload if {r['a'],r['b']}=={'cu2o',acid}]
            self.assertEqual(len(rows),1)
            r=rows[0];self.assertEqual(r['gas'],gas);self.assertEqual(r['heat'],heat)
            self.assertEqual(r['sol'],'#42baf5');self.assertEqual(bool(r['ppt']),acid=='h2so4')
            if gas:self.assertTrue(r['condition']);self.assertIn('Cu(+1)',r['reducer'])
            else:self.assertIn('Cu↓',r['eq'])

    def test_mixed_iron_oxide_and_dilute_nitric_metals_are_available(self):
        payload=self.data['reaction_payload']()
        for a,acids in [('fe3o4',['hno3','hno3_conc','h2so4_conc']),('fe',['hno3']),('al',['hno3']),('cr',['hno3'])]:
            for acid in acids:
                rows=[r for r in payload if {r['a'],r['b']}=={a,acid}]
                self.assertEqual(len(rows),1);r=rows[0]
                self.assertEqual(r['gas'],{'hno3':'NO','hno3_conc':'NO₂','h2so4_conc':'SO₂'}[acid])
                self.assertFalse(r['ppt']);self.assertNotIn('H₂↑',r['eq'])
