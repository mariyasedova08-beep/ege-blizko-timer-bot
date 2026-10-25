"""Regression tests for two-stage Al/Zn hydroxide chemistry in both lab views."""
import ast
import pathlib
import unittest

from test_lab_exchange_matrix import side_atoms


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "ege_lab_webapp.py").read_text(encoding="utf-8")


def literal_assignment(name):
    tree = ast.parse(SOURCE)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing {name}")


def balanced(equation):
    left, right = equation.replace("[", "(").replace("]", ")").split(" → ")
    return side_atoms(left) == side_atoms(right)


class AmphotericStages(unittest.TestCase):
    def test_all_reviewed_al_and_zn_salts_have_balanced_steps(self):
        stages = literal_assignment("AMPHOTERIC_STAGES")
        self.assertEqual(set(stages), {
            "alcl3", "alno3", "al2so43", "znso4", "zncl2", "znno3"
        })
        for salt, (first, second) in stages.items():
            for equation in (first, second):
                with self.subTest(salt=salt, equation=equation):
                    self.assertTrue(balanced(equation), equation)
                    self.assertIn("OH)₃" if salt.startswith("al") else "OH)₂", equation)

    def test_lesson_and_main_lab_share_excess_variants(self):
        self.assertIn('id="lessonExcess"', SOURCE)
        self.assertIn('findReaction(a,b,heated,lessonExcess)', SOURCE)
        self.assertIn('reactionVariants(a,b).find(x=>x.excess===alkali)', SOURCE)
        self.assertIn('lessonDissolving', SOURCE)
        self.assertIn('overrideReaction=undefined', SOURCE)
        self.assertIn('lessonDissolving?findReaction(a,b,lessonHeated):visualReaction', SOURCE)
        self.assertIn('state.excess,result', SOURCE)
        self.assertIn('state.dissolving?findReaction(pair.a,pair.b,state.heated)', SOURCE)
        self.assertIn('id="excess"', SOURCE)

    def test_pdf_highlighter_preserves_transparency(self):
        self.assertIn('id="lessonToolMarker"', SOURCE)
        self.assertIn('id="lessonColorPresets"', SOURCE)
        self.assertIn('lessonTool==="marker"?.32:1', SOURCE)
        self.assertIn('ctx.globalAlpha=Math.max(.1', SOURCE)
        self.assertIn('Number(stroke.opacity??1)', SOURCE)

    def test_both_alkalis_are_exposed_and_visual_stage_is_shared(self):
        self.assertIn('for variant in REACTION_VARIANTS:', SOURCE)
        self.assertIn('first_na.replace("Na", "K")', SOURCE)
        self.assertIn('"excess":"koh"', SOURCE)
        self.assertIn('row["stages"]', SOURCE)
        self.assertIn('tubeDissolving[index]', SOURCE)
        self.assertIn('x.stages.second', SOURCE)
        self.assertIn('x.stages.first', SOURCE)
        self.assertIn('x.stages.total', SOURCE.replace("x.eq", "x.stages.total"))


if __name__ == "__main__":
    unittest.main()
