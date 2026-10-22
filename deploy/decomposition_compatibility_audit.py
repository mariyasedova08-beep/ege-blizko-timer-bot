"""Read-only source audit; proposed insertions exist in memory only.

No application imports, database reads, file writes or service changes. Remote
mode reads a fixed allowlist, prints hashes/booleans only, and never exports code.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

PRODUCTION_DIR = Path('/opt/bots/ege-blizko')
FILES = (
    'run_bot_production.py', 'kulek_rewards.py',
    'decomposition_trainer.py', 'decomposition_trainer_bank.py',
    'decomposition_trainer_questions.tsv',
    'run_bot_live7.py', 'public_channel_trainers.py',
)
NEW_FILES = frozenset(FILES[2:5])
MAX_BYTES = 1_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tree_digest(tree):
    return digest(ast.dump(tree, include_attributes=False).encode())


def _unique(items):
    items = list(items)
    if len(items) != 1:
        raise ValueError('ANCHOR_NOT_UNIQUE')
    return items[0]


def _function(tree, name):
    return _unique(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _is_install(node, module):
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == module and node.value.func.attr == 'install'
            and not node.value.args and not node.value.keywords)


def _insertion(source, node, snippet, after):
    lines = source.splitlines(keepends=True)
    if node.lineno != node.end_lineno:
        raise ValueError('MULTILINE_ANCHOR_REVIEW_REQUIRED')
    line = lines[node.lineno - 1]
    indent = line[:len(line) - len(line.lstrip())]
    if not indent or len(indent.expandtabs(8)) != node.col_offset:
        raise ValueError('INLINE_ANCHOR_REVIEW_REQUIRED')
    if after and not line.endswith('\n'):
        raise ValueError('ANCHOR_NEWLINE_REQUIRED')
    newline = '\r\n' if line.endswith('\r\n') else '\n'
    insertion = ''.join(indent + part + newline for part in snippet)
    offset = sum(map(len, lines[:node.end_lineno if after else node.lineno - 1]))
    return source[:offset] + insertion + source[offset:]


def plan_startup(source):
    original = ast.parse(source)
    main = _function(original, 'main')
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) and
           ((isinstance(n, ast.Import) and any(a.name == 'decomposition_trainer' for a in n.names))
            or (isinstance(n, ast.ImportFrom) and n.module == 'decomposition_trainer'))
           for n in ast.walk(original)):
        raise ValueError('ALREADY_CONNECTED_REVIEW_REQUIRED')
    anchor = _unique(n for n in main.body if _is_install(n, 'middle_salts_trainer'))
    gate = _unique(n for n in main.body if _is_install(n, 'public_channel_trainers'))
    if main.body.index(anchor) >= main.body.index(gate):
        raise ValueError('PUBLIC_GATE_ORDER_INVALID')
    proposed = _insertion(source, anchor,
                          ['import decomposition_trainer', 'decomposition_trainer.install()'], True)
    patched = ast.parse(proposed)
    body = _function(patched, 'main').body
    index = next(i for i, n in enumerate(body) if _is_install(n, 'middle_salts_trainer'))
    del body[index + 1:index + 3]
    if tree_digest(patched) != tree_digest(original):
        raise ValueError('UNRELATED_AST_CHANGE')
    return proposed


def plan_rewards(source):
    original = ast.parse(source)
    fn = _function(original, '_trainer_goals')
    if any(isinstance(n, ast.Constant) and n.value == 'decomposition' for n in ast.walk(fn)):
        raise ValueError('REWARD_RULE_ALREADY_PRESENT_REVIEW_REQUIRED')
    loop = _unique(n for n in ast.walk(fn) if isinstance(n, ast.For)
                   and isinstance(n.iter, ast.Name) and n.iter.id == 'catalog'
                   and ast.dump(n.target) == ast.dump(ast.parse('for code, title in catalog:\n pass').body[0].target))
    expected = ast.dump(ast.parse('table = TRAINER_TABLES.get(code, f"{code}_sessions")').body[0])
    anchor = _unique(n for n in loop.body if ast.dump(n) == expected)
    normalize = ast.dump(ast.parse('code = str(code)').body[0])
    if not any(ast.dump(n) == normalize for n in loop.body[:loop.body.index(anchor)]):
        raise ValueError('CODE_NORMALIZATION_NOT_FOUND')
    proposed = _insertion(source, anchor, ['if code == "decomposition":', '    continue'], False)
    patched = ast.parse(proposed)
    guard = ast.dump(ast.parse('if code == "decomposition":\n continue').body[0])
    fn2 = _function(patched, '_trainer_goals')
    loop2 = _unique(n for n in ast.walk(fn2) if isinstance(n, ast.For)
                    and isinstance(n.iter, ast.Name) and n.iter.id == 'catalog')
    to_remove = _unique(n for n in loop2.body if ast.dump(n) == guard)
    loop2.body.remove(to_remove)
    if tree_digest(patched) != tree_digest(original):
        raise ValueError('UNRELATED_AST_CHANGE')
    return proposed


def _read(root, name):
    path = root / name
    if path.is_symlink():
        raise ValueError('SYMLINK_REFUSED')
    if not path.exists():
        return None
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_BYTES:
        raise ValueError('SOURCE_FILE_REFUSED')
    data = path.read_bytes()
    after = path.stat()
    if ((before.st_ino, before.st_size, before.st_mtime_ns) !=
            (after.st_ino, after.st_size, after.st_mtime_ns)):
        raise ValueError('SOURCE_CHANGED_DURING_AUDIT')
    return data


def audit(root):
    root = Path(root).absolute()
    if root != root.resolve(strict=True) or not root.is_dir():
        raise ValueError('PLAIN_SOURCE_DIRECTORY_REQUIRED')
    report = {'schema': 1, 'files': {}, 'plans': {}, 'routing_signatures': {},
              'production_modified': False, 'application_imported': False,
              'database_read': False, 'routing_behavior_verified': False,
              'approved_for_release': False}
    sources = {}
    for name in FILES:
        data = _read(root, name)
        report['files'][name] = {'status': 'missing' if data is None else 'present',
                                 'sha256': None if data is None else digest(data)}
        sources[name] = data
    blocked = any(sources[n] is not None for n in NEW_FILES)
    for name, planner in [('run_bot_production.py', plan_startup), ('kulek_rewards.py', plan_rewards)]:
        try:
            if sources[name] is None:
                raise ValueError('SOURCE_MISSING')
            proposed = planner(sources[name].decode('utf-8'))
            report['plans'][name] = {'status': 'INSERTION_POSSIBLE_IN_MEMORY',
                                     'proposed_sha256': digest(proposed.encode('utf-8'))}
        except (ValueError, SyntaxError, UnicodeError) as exc:
            blocked = True
            report['plans'][name] = {'status': 'BLOCKED',
                'reason': str(exc) if type(exc) is ValueError else type(exc).__name__}
    for name in ('run_bot_live7.py', 'public_channel_trainers.py'):
        expected = ('start_router', 'trivial_callback')
        try:
            tree = ast.parse(sources[name].decode('utf-8'))
            for symbol in expected:
                node = _unique(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == symbol)
                args = node.args
                match = ([a.arg for a in args.args] == ['update', 'context'] and
                         not args.posonlyargs and not args.kwonlyargs and not args.defaults
                         and not args.kw_defaults and args.vararg is None and args.kwarg is None)
                report['routing_signatures'][name + ':' + symbol] = match
                blocked |= not match
        except (AttributeError, ValueError, SyntaxError, UnicodeError):
            blocked = True
            report['routing_signatures'][name] = False
    report['status'] = ('BLOCKED_REVIEW_REQUIRED' if blocked else
                        'INSERTIONS_POSSIBLE_ROUTING_BEHAVIOR_STILL_UNVERIFIED')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['remote'], required=True)
    parser.parse_args()
    try:
        report = audit(PRODUCTION_DIR)
    except (OSError, ValueError):
        parser.exit(1, 'READONLY_AUDIT_BLOCKED\n')
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == '__main__':
    main()
