"""Exchange matrix invariants: do not show invented precipitation or violate atoms."""
import re
import unittest

from ege_lab_substances import REAGENTS
from ege_lab_exchange_matrix import (
    AQUEOUS_SALTS, CATIONS, ANIONS, INSOLUBLE, _balance_exchange,
    _formula, generate_exchange_reactions,
)

SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉","0123456789")

def atom_counter(formula):
    s=formula.translate(SUB).replace("↓","").replace("↑","")
    pos=0
    def parse():
        nonlocal pos
        atoms={}
        while pos<len(s):
            if s[pos]==")":
                break
            if s[pos]=="(":
                pos+=1
                group=parse()
                assert pos<len(s) and s[pos]==")",formula
                pos+=1
            else:
                token=re.match(r"[A-Z][a-z]?",s[pos:])
                assert token,(formula,s[pos:])
                group={token.group():1}
                pos+=len(token.group())
            count=re.match(r"\d+",s[pos:])
            n=int(count.group()) if count else 1
            if count:pos+=len(count.group())
            for el,val in group.items():atoms[el]=atoms.get(el,0)+val*n
        return atoms
    atoms=parse()
    assert pos==len(s),(formula,pos)
    return atoms

def side_atoms(side):
    d={}
    for term in side.split(" + "):
        term=term.strip()
        m=re.fullmatch(r"(\d+)?(.+)",term)
        assert m,term
        coefficient=int(m.group(1) or 1)
        for element,count in atom_counter(m.group(2)).items():
            d[element]=d.get(element,0)+count*coefficient
    return d

class ExchangeMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reactions=generate_exchange_reactions(REAGENTS)
        cls.by_pair={frozenset((x["a"],x["b"])):x for x in cls.reactions}

    def get_pair(self,a,b):
        key=frozenset((a,b))
        self.assertIn(key,self.by_pair,a+"+"+b)
        return self.by_pair[key]

    def test_sources_exist_and_are_really_aqueous(self):
        for c,salts in AQUEOUS_SALTS.items():
            self.assertIn(c,CATIONS)
            for anion,rid in salts.items():
                self.assertIn(anion,ANIONS)
                self.assertIn(rid,REAGENTS)
                self.assertEqual(REAGENTS[rid][3],"р-р",rid)

    def test_all_generated_equations_are_atom_balanced(self):
        self.assertGreater(len(self.reactions),150)
        print("EXCHANGE_MATRIX_COVERAGE:",len(self.reactions),"verified generated outcomes")
        self.assertEqual(len(self.by_pair),len(self.reactions))
        for row in self.reactions:
            with self.subTest(pair=(row["a"],row["b"])):
                self.assertIn("→",row["eq"])
                left,right=row["eq"].split(" → ")
                if row["t"]!="z":
                    self.assertEqual(side_atoms(left),side_atoms(right),row["eq"])
                else:
                    self.assertEqual(right,"реакция не идёт")
                self.assertIn(row["t"],("p","g","n","x","z","c"))
                self.assertIn(row["a"],REAGENTS)
                self.assertIn(row["b"],REAGENTS)
                self.assertEqual(row["heat"],False)
                self.assertTrue(row["sign"])

    def test_precipitate_colours_and_exchange_drivers(self):
        samples={
            ("bacl2","na2so4"):"BaSO₄↓",
            ("agno3","nacl"):"AgCl↓",
            ("bacl2","h2so4"):"BaSO₄↓",
            ("agno3","hcl"):"AgCl↓",
            ("pbno3","hi"):"PbI₂↓",
            ("agno3","ki"):"AgI↓",
            ("pbno3","ki"):"PbI₂↓",
            ("cacl2","na2co3"):"CaCO₃↓",
            ("agno3","k2cro4"):"Ag₂CrO₄↓",
            ("fecl2","naoh"):"Fe(OH)₂↓",
            ("fecl3","naoh"):"Fe(OH)₃↓",
            ("cuso4","naoh"):"Cu(OH)₂↓",
            ("crcl3","koh"):"Cr(OH)₃↓",
            ("alcl3","naoh"):"Al(OH)₃↓",
            ("agno3","naoh"):"Ag₂O↓",
            ("na2so4","baoh2"):"BaSO₄↓",
        }
        for (a,b),product in samples.items():
            with self.subTest(pair=a+"+"+b):
                row=self.get_pair(a,b)
                self.assertIn(product,row["eq"])
                self.assertEqual(row["t"],"p")
                self.assertTrue(row["ppt"])

    def test_acid_base_and_acid_salt_gases(self):
        self.assertIn("H₂O",self.get_pair("hcl","naoh")["eq"])
        for solid, acid, target_product in [
            ("cuo","hcl","CuCl₂"),
            ("fe2o3","h2so4","Fe₂(SO₄)₃"),
            ("al2o3","hcl","AlCl₃"),
            ("croh3","hcl","CrCl₃"),
            ("aloh3","hcl","AlCl₃"),
            ("feoh3","h2so4","Fe₂(SO₄)₃"),
        ]:
            with self.subTest(pair=(solid,acid)):
                self.assertIn(target_product,self.get_pair(solid,acid)["eq"])
        self.assertIn("CaCl₂",self.get_pair("hcl","caoh2")["eq"])
        self.assertIn("CO₂↑",self.get_pair("na2co3","hcl")["eq"])
        self.assertIn("SO₂↑",self.get_pair("na2so3","hcl")["eq"])
        self.assertIn("H₂S↑",self.get_pair("na2s","hcl")["eq"])
        self.assertIn("NH₃↑",self.get_pair("nh4cl","naoh")["eq"])
        self.assertIn("CO₂↑",self.get_pair("nahco3","hcl")["eq"])
        self.assertIn("SO₂↑",self.get_pair("nahso3","hcl")["eq"])
        self.assertIn("H₂S↑",self.get_pair("khs","hcl")["eq"])
        self.assertIn("H₂SiO₃↓",self.get_pair("na2sio3","hcl")["eq"])
        self.assertIn("AgCl↓",self.get_pair("agno3","hcl")["eq"])
        self.assertIn("BaSO₄↓",self.get_pair("bacl2","h2so4")["eq"])
        self.assertIn("PbCl₂↓",self.get_pair("pbno3","hcl")["eq"])

    def test_do_not_forge_chemically_false_pairs(self):
        for a,b in (
            ("fecl3","ki"),     # Fe(III) reduction + I₂, NOT ion exchange
            ("cuso4","ki"),     # Cu(I) precip + I₂, NOT ion exchange
            ("fecl3","k2s"),    # Fe(III) reduction + sulfur, NOT hydrolysis
            ("fecl3","k2so3"),  # Fe(III) reduction + sulfate, NOT hydrolysis
            ("fecl3","na2s"),   # Fe(III) reduction + sulfur
            ("fe2o3","hi"),    # HI iodide is an actual reductant here
            ("cuo","hi"),      # HI with Cu(II) yields CuI and iodine
        ):
            with self.subTest(pair=a+"+"+b):
                self.assertNotIn(frozenset((a,b)),self.by_pair)

    def test_hydrolysis_and_copper_basic_salt_exceptions(self):
        for pair,part in {
            ("alcl3","na2co3"):"Al(OH)₃↓",
            ("fecl3","k2co3"):"Fe(OH)₃↓",
            ("crcl3","na2so3"):"Cr(OH)₃↓",
            ("alno3","na2so3"):"Al(OH)₃↓",
            ("cr2so43","na2s"):"Cr(OH)₃↓",
            ("fecl3","khco3"):"Fe(OH)₃↓",
            ("cuso4","k2co3"):"Cu₂(OH)₂CO₃↓",
            ("cucl2","na2co3"):"Cu₂(OH)₂CO₃↓",
        }.items():
            with self.subTest(pair=pair):
                r=self.get_pair(*pair)
                self.assertEqual(r["t"],"x")
                self.assertIn(part,r["eq"])
                self.assertIn("↑",r["eq"])
                self.assertIn("↓",r["eq"])

    def test_inert_ions_are_explicitly_no_reaction(self):
        for a,b in (("nacl","kno3"),("kcl","nano3"),("nabr","kno3")):
            with self.subTest(pair=a+"+"+b):
                reaction=self.get_pair(a,b)
                self.assertEqual(reaction["t"],"z")
                self.assertIn("реакция не идёт",reaction["eq"])

    def test_reviewed_reaction_has_priority(self):
        saved={("agno3","nacl"),("cuso4","naoh")}
        rows=generate_exchange_reactions(REAGENTS,saved)
        pairs={frozenset((x["a"],x["b"])) for x in rows}
        for x in saved:self.assertNotIn(frozenset(x),pairs)

    def test_no_chemically_invalid_hydroxide_species(self):
        for item in self.reactions:
            self.assertNotIn("AgOH",item["eq"])
            self.assertNotIn("CuCO₃↓",item["eq"])

if __name__=="__main__":
    unittest.main()
