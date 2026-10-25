"""Read-only regression checks for the EGE BLIZKO laboratory release.

This suite never imports the bot or touches SQLite/Telegram/server state.
"""
import ast
import json
import re
import runpy
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
        # This pure data module appends curated batches via .extend().
        # AST literal inspection alone misses the appended entries.
        data = runpy.run_path(str(ROOT / "ege_lab_inorganic_reactions.py"))
        cls.reactions = (
            literal_assignment("ege_lab_webapp.py", "REACTIONS")
            + data["EXTRA_REACTIONS"]
            + literal_assignment("ege_task6_reactions.py", "TASK6_REACTIONS")
        )
        cls.variants = (
            data["REACTION_VARIANTS"]
            + literal_assignment("ege_task6_reactions.py", "TASK6_VARIANTS")
        )
        cls.html = literal_assignment("ege_lab_webapp.py", "HTML")

    def test_catalogue_coverage_not_reduced(self):
        self.assertGreaterEqual(len(self.reagents), 200)  # Cr(III) catalogue extensions must not disappear
        self.assertGreaterEqual(len(self.reactions) + len(self.variants), 461)  # curated batch 3

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

    def test_all_white_precipitates_use_visible_shared_styling(self):
        self.assertIn('light=/^#(?:fff|ffffff|f8fbff)$/i', self.html)
        self.assertIn('.pptLayer.light-ppt .particle{', self.html)
        self.assertIn('.pptLayer.light-ppt .gel-bed{', self.html)
        self.assertIn('.pptLayer.light-ppt .gel-cloud{', self.html)
        self.assertIn('.tube-slot:has(.pptLayer):before', self.html)
        self.assertIn('.tube-slot:has(.pptLayer):before{content:none}', self.html)
        self.assertNotIn('.tube-slot:has(.pptLayer.bright-ppt):before', self.html)
        self.assertIn('.tube:has(.pptLayer){', self.html)
        self.assertIn('box-shadow:0 1px 2px rgba(68,78,88,.30);animation-name:settleLight', self.html)
        self.assertIn('light&&cls==="fine"?110', self.html)
        self.assertIn('animation-name:gelBedGrowLight', self.html)
        self.assertIn('animation-name:gelCloudSettleLight', self.html)
        self.assertIn('@keyframes gelCloudSettleLight', self.html)
        self.assertIn('opacity:.94', self.html)

    def test_all_precipitate_colours_get_contrasting_backgrounds(self):
        self.assertIn('function pptIsBright(color)', self.html)
        self.assertIn("const bgClass=pptIsBright(x.ppt)?' bright-ppt':''", self.html)
        self.assertIn("+(light?' light-ppt':'')+bgClass", self.html)
        self.assertIn('.pptLayer:not(.light-ppt) .particle.crystal', self.html)
        self.assertIn('.pptLayer:not(.light-ppt) .particle.dense', self.html)

    def test_reagent_chains_preserve_reaction_products(self):
        self.assertIn('let tubeChain=[null,null,null,null]', self.html)
        self.assertIn('function chainProductIds(rx)', self.html)
        self.assertIn('function chainCandidates(i,newId)', self.html)
        self.assertIn('function chainCompleteStep(i,newId,selected)', self.html)
        self.assertIn('const next=chain.available.filter', self.html)
        self.assertIn('tubeChain[selectedTube]=null', self.html)
        self.assertNotIn('if(tubes[selectedTube].length>=2)return;', self.html)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for chain checks")
    def test_chain_reacts_with_products_not_original_inputs(self):
        js = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        chain_code = js[js.index("function key(a,b)"):js.index("// Unified source of gas colours")]
        chain_code = chain_code.replace(
            'document.getElementById("result").textContent=',
            'globalThis.lastChainResult=',
        )
        entries = []
        for rx in self.reactions:
            a, b, eq, kind, sign, sol, ppt, gas, heated = rx
            if {a, b} in ({"cuoh2", "hcl"}, {"cucl2", "naoh"}):
                entries.append({"a": a, "b": b, "eq": eq, "t": kind,
                                "sign": sign, "sol": sol, "ppt": ppt,
                                "gas": gas, "heat": heated})
        script = "\n".join((
            "const reagentMap=new Map(Object.entries(" + json.dumps(self.reagents, ensure_ascii=False) + "));",
            "const reactionMap=new Map();",
            "const tubes=[['cuso4','naoh']];",
            "const tubeChain=[{available:['cuoh2','na2so4'],steps:[{reaction:{eq:'CuSO₄ + 2NaOH → Cu(OH)₂↓ + Na₂SO₄'}}]}];",
            "let renders=0;function renderTubes(){renders++}",
            "function normalizeReagentSearch(s){return String(s).toLowerCase().replace(/[₀₁₂₃₄₅₆₇₈₉]/g,x=>'0123456789'['₀₁₂₃₄₅₆₇₈₉'.indexOf(x)]).replace(/[\\s·.]/g,'')}",
            chain_code,
            "for(const rx of " + json.dumps(entries, ensure_ascii=False) + "){const k=key(rx.a,rx.b);reactionMap.set(k,[rx])}",
            "if(chainCandidates(0,'hcl').length!==1)throw Error('CuOH2 HCl candidate missing');",
            "if(!chainCompleteStep(0,'hcl','cuoh2'))throw Error('CuCl2 stage failed');",
            "if(!tubeChain[0].available.includes('cucl2'))throw Error('CuCl2 product missing');",
            "if(tubeChain[0].available.includes('cuoh2'))throw Error('Consumed hydroxide retained');",
            "if(chainCandidates(0,'naoh').length!==1)throw Error('CuCl2 NaOH candidate missing');",
            "if(!chainCompleteStep(0,'naoh','cucl2'))throw Error('Third reaction failed');",
            "if(tubes[0].length!==4||renders!==2)throw Error('Chain did not extend');",
            "if(chainCandidates(0,'hcl').length!==1)throw Error('Fifth reagent candidate missing');",
            "if(!chainCompleteStep(0,'hcl','cuoh2'))throw Error('Fifth reagent stage failed');",
            "if(tubes[0].length!==5||renders!==3)throw Error('Fifth reagent not added');",
        ))
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for chain checks")
    def test_open_tube_does_not_react_with_escaped_carbon_dioxide(self):
        js = self.html.split("<script>", 1)[1].split("</script>", 1)[0]
        chain_code = js[js.index("function key(a,b)"):js.index("// Unified source of gas colours")]
        script = "\n".join((
            "const reagentMap=new Map(Object.entries(" + json.dumps(self.reagents, ensure_ascii=False) + "));",
            "const reactionMap=new Map();",
            "const tubes=[['fecl3','na2co3']];",
            "const tubeChain=[null];",
            "function renderTubes(){}",
            "function normalizeReagentSearch(s){return String(s).toLowerCase().replace(/[₀₁₂₃₄₅₆₇₈₉]/g,x=>'0123456789'['₀₁₂₃₄₅₆₇₈₉'.indexOf(x)]).replace(/[\\s·.]/g,'')}",
            chain_code,
            "const first={eq:'2FeCl₃ + 3Na₂CO₃ + 3H₂O → 2Fe(OH)₃↓ + 3CO₂↑ + 6NaCl'};",
            "const products=chainProductIds(first);",
            "if(products.includes('co2'))throw Error('Escaped CO2 retained in open tube');",
            "if(!products.includes('feoh3')||!products.includes('nacl'))throw Error('Retained products missing');",
            "tubeChain[0]={available:products,steps:[{reaction:first}]};",
            "reactionMap.set(key('co2','naoh'),[{a:'co2',b:'naoh',eq:'CO₂ + 2NaOH → Na₂CO₃ + H₂O',t:'n'}]);",
            "if(chainCandidates(0,'naoh').length)throw Error('NaOH reacted with escaped gas');",
            "if(tubeChain[0].steps.length!==1)throw Error('History was modified');",
        ))
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lesson_no_reaction_is_visible_and_gas_animation_stops(self):
        self.assertIn('lessonChain.noReactionNotice=true;lessonRenderExperiment();return;', self.html)
        self.assertIn('lessonChain.noReactionNotice?{...last,gas:""}:last', self.html)
        self.assertIn('class="chain-no-reaction"', self.html)
        self.assertIn('lessonChain.noReactionNotice=false;', self.html)

    def test_lesson_two_tubes_keep_independent_state_and_ink(self):
        self.assertIn('id="lessonTube1"', self.html)
        self.assertIn('id="lessonTube2"', self.html)
        self.assertIn('let lessonTubeStates=[null,null,null,null]', self.html)
        self.assertIn('lessonTubeStates[lessonActiveTube]=lessonCaptureTube()', self.html)
        self.assertIn('lessonApplyTube(lessonTubeStates[index])', self.html)
        self.assertIn('ink:lessonLabInkStrokes', self.html)
        self.assertIn('lessonLabInkStrokes=state.ink', self.html)

    def test_lesson_tube_count_modes_are_separate_workbenches(self):
        for count in range(1, 5):
            self.assertIn(f'data-lesson-count="{count}"', self.html)
            self.assertIn(f'id="lessonTube{count}"', self.html)
        self.assertIn('lessonVisibleTubeCount=count', self.html)
        self.assertIn('btn.hidden=Number(btn.dataset.lessonTube)>=lessonVisibleTubeCount', self.html)
        self.assertIn('const lessonModeStates={}', self.html)
        self.assertIn('lessonModeStates[lessonVisibleTubeCount]={tubes:lessonTubeStates,active:lessonActiveTube}', self.html)
        self.assertIn('lessonTubeStates=target.tubes', self.html)
        self.assertIn('lessonApplyTube(lessonTubeStates[lessonActiveTube])', self.html)

    def test_stylus_smoothing_is_shared_by_canvas_and_pdf_export(self):
        self.assertIn('function lessonSmoothPoints(points)', self.html)
        self.assertIn('function lessonPointerSamples(event,converter)', self.html)
        self.assertIn('event.getCoalescedEvents()', self.html)
        self.assertIn('lessonSmoothPoints(stroke.points).forEach', self.html)
        self.assertIn('lessonSmoothPoints(stroke.points).entries()', self.html)
        self.assertIn('const pts=lessonSmoothPoints(stroke.points||[])', self.html)
        self.assertIn('lessonAddStrokeSamples(lessonDrawing,event,lessonGetPoint,canvas)', self.html)

    def test_mobile_comparison_bench_and_white_precipitates_are_visible(self):
        self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))!important', self.html)
        self.assertIn('.tube-slot:has(.pptLayer):before{content:none}', self.html)
        self.assertIn('.rack-board{display:none!important}', self.html)
        self.assertIn('border:1px solid rgba(86,105,117,.52)', self.html)
        self.assertIn("?'rgba(181,198,207,.22)':rawSol", self.html)

    def test_lesson_pdf_export_rebuilds_pages_and_validates_output(self):
        self.assertIn('await sourcePage.render({canvasContext:context,viewport}).promise', self.html)
        self.assertIn('sheet.drawImage(embedded,{x:0,y:0,width:base.width,height:base.height})', self.html)
        self.assertNotIn('await pdf.copyPages(source,source.getPageIndices())', self.html)
        self.assertIn('const sheet=pdf.addPage([base.width,base.height])', self.html)
        self.assertIn('trailer.includes("%%EOF")', self.html)
        self.assertIn('setTimeout(()=>URL.revokeObjectURL(url),60000)', self.html)

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
            js.index("const PRECIPITATE_STYLES="):js.index("function bubblesHTML(")
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
            "function bubblesHTML(x,v=[])",
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
