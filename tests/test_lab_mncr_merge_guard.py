"""Offline simulation of the four exact staging conflicts; no server access."""
import runpy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = runpy.run_path(str(ROOT / "deploy/resolve_lab_mncr_staging_conflicts.py"))
resolve = FUNCTIONS["reconcile"]
validate = FUNCTIONS["validate_merged"]

def fixture():
    return """HTML = '''<html><head><style>
<<<<<<< ours
.lesson-studio{display:grid}
=======
body[data-lab-theme] .reaction-status{color:var(--lab-accent)}
>>>>>>> theirs
</style></head><body>
<div class="lab-nav">
<<<<<<< ours
<a href="/lab-solubility">solubility</a>
=======
<button id="labThemeButton">theme</button>
>>>>>>> theirs
</div>
<button data-page="guided">guided</button><button data-page="lesson">lesson</button>
<div id="lessonMediumField"></div><div id="tubeMediumField"></div>
<script>window.Telegram={WebApp:{}};</script>
<script>
function renderGuided(){}
function lessonSetup(){}
function lessonRenderPage(){}
function nextExam(){}
function renderOge(){}
function renderEge(){}
document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>{
<<<<<<< ours
 b.classList.add("on");document.getElementById(b.dataset.page).classList.add("on");if(b.dataset.page==="lesson"){lessonRenderPage();}if(b.dataset.page==="exam"&&!exam)nextExam();if(b.dataset.page==="oge")renderOge();if(b.dataset.page==="ege")renderEge();
=======
 b.classList.add("on");document.getElementById(b.dataset.page).classList.add("on");if(b.dataset.page==="exam"&&!exam)nextExam();if(b.dataset.page==="guided")renderGuided();if(b.dataset.page==="oge")renderOge();if(b.dataset.page==="ege")renderEge();
>>>>>>> theirs
});
function initialize(){
<<<<<<< ours
renderTubes();renderStats();lessonSetup();
=======
renderTubes();renderStats();renderGuided();
>>>>>>> theirs
}
</script></body></html>'''
"""

class ReleaseMergeConflictGuard(unittest.TestCase):
    def test_union_retains_all_four_conflict_features(self):
        merged, resolutions = resolve(fixture())
        self.assertEqual(len(resolutions), 4)
        self.assertNotIn("<<<<<<<", merged)
        self.assertIn("body[data-lab-theme]", merged)
        self.assertIn("href=\"/lab-solubility\"", merged)
        self.assertIn('id="labThemeButton"', merged)
        self.assertIn('lessonSetup();renderGuided();', merged)
        validate(merged)

    def test_fail_closed_if_conflict_count_differs(self):
        with self.assertRaisesRegex(ValueError, "EXACTLY four"):
            resolve(fixture().replace("<<<<<<< ours\n.lesson-studio{display:grid}\n=======\nbody[data-lab-theme] .reaction-status{color:var(--lab-accent)}\n>>>>>>> theirs\n", ".lesson-studio{display:grid}\n"))

    def test_fail_closed_if_wrong_features(self):
        with self.assertRaisesRegex(ValueError, "Conflict 2"):
            resolve(fixture().replace('id="labThemeButton"', 'id="wrongButton"'))

if __name__ == "__main__":
    unittest.main()
