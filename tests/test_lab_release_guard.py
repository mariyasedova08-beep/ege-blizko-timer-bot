"""Read-only regression checks for the EGE BLIZKO laboratory release.

This suite never imports the bot or touches SQLite/Telegram/server state.
"""
import ast
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "ege_lab_webapp.py"


def literal_assignment(file_name, variable):
    tree = ast.parse((ROOT / file_name).read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == variable for t in node.targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except (TypeError, ValueError):
            continue
    raise AssertionError(f"{variable} literal missing in {file_name}")


class LaboratoryReleaseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab_source = LAB.read_text(encoding="utf-8")
        cls.reagents = literal_assignment("ege_lab_substances.py", "REAGENTS")
        cls.reactions = (
            literal_assignment("ege_lab_webapp.py", "REACTIONS")
            + literal_assignment("ege_lab_inorganic_reactions.py", "EXTRA_REACTIONS")
            + literal_assignment("ege_task6_reactions.py", "TASK6_REACTIONS")
        )
        cls.variants = (
            literal_assignment("ege_lab_inorganic_reactions.py", "REACTION_VARIANTS")
            + literal_assignment("ege_task6_reactions.py", "TASK6_VARIANTS")
        )
        cls.html = literal_assignment("ege_lab_webapp.py", "HTML")

    def test_catalogue_coverage_not_reduced(self):
        self.assertEqual(len(self.reagents), 195)
        self.assertEqual(len(self.reactions) + len(self.variants), 435)

    def test_reaction_references_and_shapes(self):
        known = set(self.reagents)
        for rx in self.reactions:
            self.assertEqual(len(rx), 9, rx)
            self.assertIn(rx[0], known)
            self.assertIn(rx[1], known)
        for rx in self.variants:
            self.assertIn(rx["a"], known)
            self.assertIn(rx["b"], known)
            if rx.get("excess"):
                self.assertIn(rx["excess"], known)

    def test_gel_visualization_and_colour_source(self):
        # Both Cu(OH)2 and Fe(OH)2 should use soft clouds, not round bubbles.
        self.assertIn('"Cu(OH)₂":"gel"', self.html)
        self.assertIn('"Fe(OH)₂":"gel"', self.html)
        self.assertIn('"Fe(OH)₃":"gel"', self.html)
        self.assertIn('class="gel-bed"', self.html)
        self.assertIn('class="gel-cloud"', self.html)
        self.assertIn("@keyframes gelCloudSettle", self.html)
        self.assertIn("--pc:'+x.ppt", self.html)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for live visual rules")
    def test_eight_reference_experiments_use_correct_visuals(self):
        """Evaluate actual production JavaScript against 8 reference chemical pairs."""
        expected = {
            ("cuso4", "naoh"): ("gel", ""),
            ("feso4", "naoh"): ("gel", ""),
            ("fecl3", "naoh"): ("gel", ""),
            ("alcl3", "naoh"): ("gel", ""),
            ("bacl2", "h2so4"): ("fine", ""),
            ("pbno3", "ki"): ("crystal", ""),
            ("cuo", "hcl"): ("", "dissolving_solid"),
            ("caco3", "hcl"): ("", "dissolving_solid"),
        }
        by_pair = {frozenset((rx[0], rx[1])): rx for rx in self.reactions}
        cases = []
        for pair, (texture, solid) in expected.items():
            rx = by_pair[frozenset(pair)]
            cases.append({
                "pair": list(pair), "texture": texture, "solid": solid,
                "rx": {
                    "eq": rx[2], "t": rx[3], "sign": rx[4], "sol": rx[5],
                    "ppt": rx[6], "gas": rx[7], "heat": bool(rx[8]),
                },
            })
        scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", self.html)
        self.assertTrue(scripts)
        js = next(part for part in scripts if "const PRECIPITATE_STYLES=" in part)
        precipitate_rules = js[
            js.index("const PRECIPITATE_STYLES="):js.index("function bubblesHTML(x){")
        ]
        solid_rules = js[
            js.index("function solidReactionMode("):js.index("function metalDepositHTML(")
        ]
        snippet = "\n".join((
            "const cases=" + json.dumps(cases, ensure_ascii=False) + ";",
            "const reagents=" + json.dumps(self.reagents, ensure_ascii=False) + ";",
            "function reagent(id){return reagents[id];}",
            precipitate_rules,
            solid_rules,
            """const results=cases.map(c=>{
              const visual=precipitateHTML(c.rx);
              const solidVisual=solidReagentHTML(c.pair,c.rx);
              return {
                texture:pptTexture(c.rx), solid:solidReactionMode(c.pair,c.rx),
                output:visual, solidOutput:solidVisual
              };
            });""",
            "process.stdout.write(JSON.stringify(results));",
        ))
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "reference_visuals.js"
            target.write_text(snippet, encoding="utf-8")
            process = subprocess.run(
                ["node", str(target)], capture_output=True, text=True, check=False,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        actual = json.loads(process.stdout)
        self.assertEqual(len(actual), 8)
        for item, state in zip(cases, actual):
            label = " + ".join(item["pair"])
            self.assertEqual(state["texture"], item["texture"], label)
            self.assertEqual(state["solid"], item["solid"], label)
            if item["texture"] == "gel":
                self.assertIn("gel-sediment", state["output"], label)
            if item["texture"] == "fine":
                self.assertIn("particle fine", state["output"], label)
            if item["texture"] == "crystal":
                self.assertIn("particle crystal", state["output"], label)
            if item["solid"]:
                self.assertIn("dissolving-solid", state["solidOutput"], label)
            if item["rx"]["ppt"]:
                self.assertIn(item["rx"]["ppt"], state["output"], label)
        self.assertEqual(cases[-1]["rx"]["gas"], "CO₂")
        self.assertIn("растворяется", cases[-1]["rx"]["sign"].lower())
        self.assertIn("CuCl₂", cases[-2]["rx"]["eq"])

    @unittest.skipUnless(shutil.which("node"), "Node.js required for live visual rules")
    def test_solid_consumption_requires_a_real_reaction(self):
        js = next(part for part in re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", self.html)
                  if "function solidReactionMode(" in part)
        rules = js[js.index("function solidReactionMode("):js.index("function metalDepositHTML(")]
        source = "\n".join((
            "const reagents=" + json.dumps(self.reagents, ensure_ascii=False) + ";",
            "function reagent(id){return reagents[id];}",
            rules,
            """const solid=['cuo','hcl'], metal=['zn','hcl'], noReaction=['cu','hcl'];
            const reactive={t:'c',sign:'чёрный CuO растворяется'};
            const activeMetal={t:'g',sign:'цинк растворяется'};
            const passive={t:'z',sign:'реакция не идёт'};
            const output={
                solid:solidReactionMode(solid,reactive),
                metal:solidReactionMode(metal,activeMetal),
                missing:solidReactionMode(solid,null),
                passive:solidReactionMode(noReaction,passive),
                kept:solidReagentHTML(solid,null),
                consumed:solidReagentHTML(solid,reactive)
            };
            process.stdout.write(JSON.stringify(output));""",
        ))
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "solid_rules.js"
            target.write_text(source, encoding="utf-8")
            result = subprocess.run(
                ["node", str(target)], capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["solid"], "dissolving_solid")
        self.assertEqual(data["metal"], "reactive_metal")
        self.assertEqual(data["missing"], "")
        self.assertEqual(data["passive"], "")
        self.assertNotIn("dissolving-solid", data["kept"])
        self.assertIn("dissolving-solid", data["consumed"])

    def test_gas_reference_covers_all_emitted_gases(self):
        """Every gas produced by the 435 reactions must have explicit facts."""
        gas_section = self.html.split("const GAS_REFERENCE=Object.freeze({", 1)[1].split("});", 1)[0]
        gases = {rx[7] for rx in self.reactions if rx[7]}
        gases.update(item["gas"] for item in self.variants if item.get("gas"))
        self.assertTrue(gases, "No laboratory gas reactions were detected")
        for gas in gases:
            self.assertIn('"' + gas + '":', gas_section, gas)
        self.assertIn("function gasObservationHTML(x)", self.html)
        self.assertIn("+gasObservationHTML(x)+", self.html)
        self.assertIn("Не вдыхайте выделяющиеся газы", self.html)
        self.assertIn("const gasColor=gasInfo?gasInfo.plume", self.html)
        self.assertIn('"NO₂":{color:"бурый"', gas_section)
        for gas in ("SO₂", "H₂S", "NH₃"):
            self.assertIn('"' + gas + '":{color:"бесцветный"', gas_section)

    def test_existing_modes_and_gas_effects_remain(self):
        for marker in (
            "function bubblesHTML(x)",
            "function renderTubes()",
            "function setupMobileTubePicker()",
            '"task6":TASK6_BANK',
            '"oge12":_oge12_bank_payload()',
            '"oge23":_oge23_bank_payload()',
            "function reactionResultHTML(",
        ):
            self.assertIn(marker, self.lab_source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JS syntax checks")
    def test_embedded_javascript_syntax(self):
        scripts = re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>", self.html)
        self.assertTrue(any(part.strip() for part in scripts))
        with tempfile.TemporaryDirectory() as tempdir:
            for index, script in enumerate(scripts):
                if not script.strip():
                    continue
                target = Path(tempdir) / f"lab_inline_{index}.js"
                target.write_text(script, encoding="utf-8")
                process = subprocess.run(
                    ["node", "--check", str(target)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
