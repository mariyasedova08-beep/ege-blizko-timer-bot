"""Evaluate chemistry-only AST nodes. Never import the laboratory or Telegram bot."""
import ast
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load_candidate():
    substances = runpy.run_path(str(ROOT / 'ege_lab_substances.py'))
    inorganic = runpy.run_path(str(ROOT / 'ege_lab_inorganic_reactions.py'))
    task6 = runpy.run_path(str(ROOT / 'ege_task6_reactions.py'))
    matrix = runpy.run_path(str(ROOT / 'ege_lab_exchange_matrix.py'))
    bank = runpy.run_path(str(ROOT / 'ege_task6_bank.py'))
    namespace = {**inorganic, **task6, **matrix, **bank, 'LAB_REAGENTS': substances['REAGENTS']}
    tree = ast.parse((ROOT / 'ege_lab_webapp.py').read_text())
    names = {'REAGENTS','REACTIONS','AMPHOTERIC_OXIDE_REACTIONS','_EXPLICIT_PAIRS',
             'EXCHANGE_REACTIONS','AMPHOTERIC_STAGES','HTML'}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == 'reaction_payload':
            nodes.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in {'REAGENTS','REACTIONS','_EXPLICIT_PAIRS'} and func.attr in {'setdefault','extend'}:
                nodes.append(node)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<isolated-chemistry>','exec'), namespace)
    return namespace
