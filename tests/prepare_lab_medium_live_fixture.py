"""Offline fixtures for a read-only Chromium smoke test of the REAL lab-app HTML.

Pure AST extraction: importing the Telegram bot or touching a database is forbidden.
"""
import ast
import json
import re
from pathlib import Path
from ege_lab_exchange_matrix import generate_exchange_reactions

ROOT = Path(__file__).resolve().parents[1]
def literal(name, path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except (TypeError, ValueError):
                pass
    raise RuntimeError(f"Missing literal {name}: {path}")

html = literal("HTML", ROOT / "ege_lab_webapp.py")
preview = (ROOT / "preview" / "ege-blizko-lab-lesson-30-70-offline.html").read_text(encoding="utf-8")
match = re.search(r"const LESSON_PREVIEW_PAYLOAD=(\{.*?\});\n", preview)
assert match, "Missing preview payload"
data = json.loads(match.group(1))
assert data["ok"]
assert len(data["data"]["medium_reactions"]) == 89, "Unreviewed reactions leaked into preview"
# Add current exchange matrix to the real lab HTML's offline API fixture.
# The Telegram runtime itself is intentionally not imported in these tests.
reactions=data["data"]["reactions"]
approved_pairs=[(row["a"],row["b"]) for row in reactions]
approved_pairs += [(row["a"],row["b"]) for row in data["data"]["medium_reactions"]]
extra=generate_exchange_reactions(data["data"]["reagents"],approved_pairs)
reactions.extend(extra)
print("EXCHANGE_BROWSER_FIXTURE_ROWS="+str(len(extra)))
out = Path("/tmp")
(out / "ege-live-lesson-smoke.html").write_text(html, encoding="utf-8")
(out / "ege-live-lesson-smoke.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print("LIVE_MEDIUM_FIXTURE_OK")
