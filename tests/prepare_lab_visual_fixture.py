"""Build a standalone browser fixture from the laboratory's production HTML and data."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "lab-visual-preview"
OUT.mkdir(exist_ok=True)


def static_value(filename, name):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    for entry in tree.body:
        if isinstance(entry, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in entry.targets
        ):
            try:
                return ast.literal_eval(entry.value)
            except (TypeError, ValueError):
                pass
    raise ValueError(f"Missing literal {name} in {filename}")


html = static_value("ege_lab_webapp.py", "HTML")
reagents = static_value("ege_lab_substances.py", "REAGENTS")
reactions = []
for filename, variable in (
    ("ege_lab_webapp.py", "REACTIONS"),
    ("ege_lab_inorganic_reactions.py", "EXTRA_REACTIONS"),
    ("ege_task6_reactions.py", "TASK6_REACTIONS"),
):
    for a, b, eq, kind, sign, solution, precipitate, gas, heat in static_value(filename, variable):
        reactions.append(dict(a=a, b=b, eq=eq, t=kind, sign=sign,
                              sol=solution, ppt=precipitate, gas=gas, heat=bool(heat),
                              excess="", condition=""))
for filename, variable in (
    ("ege_lab_inorganic_reactions.py", "REACTION_VARIANTS"),
    ("ege_task6_reactions.py", "TASK6_VARIANTS"),
):
    reactions.extend(static_value(filename, variable))

assert len(reagents) == 195
assert len(reactions) == 435
payload = {
    "ok": True,
    "data": {
        "reagents": reagents,
        "reactions": reactions,
        "lab": ["cuso4", "fecl3", "na2co3", "nacl", "na2so4"],
        "tools": ["hcl", "naoh", "agno3", "bacl2"],
        "stats": {"experiments": 0, "predictions": 0, "accuracy": 0,
                  "labworks_completed": 0},
        "coverage": {"substances": len(reagents), "reactions": len(reactions)},
        "task6": [], "task6_progress": {}, "task6_session": None,
        "oge12": [], "oge23": [],
    },
}
(OUT / "lab.html").write_text(html, encoding="utf-8")
(OUT / "fixture.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print("LAB_BROWSER_FIXTURE_OK")
