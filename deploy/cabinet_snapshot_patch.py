"""Pure scoped hook into the already installed October exception."""
import ast

HOOK = '    import cabinet_schedule_snapshot\n    cabinet_schedule_snapshot.install()\n'


def transform(data):
    source = data.decode('utf-8')
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install']
    if len(nodes) != 1:
        raise ValueError('CABINET_SNAPSHOT_INSTALL_ANCHOR_MISSING')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    fragment = source[start:end]
    if fragment.count(HOOK) == 1:
        return data
    anchor = '    _INSTALLED = True\n'
    if fragment.count(anchor) != 1 or 'cabinet_schedule_snapshot' in source:
        raise ValueError('CABINET_SNAPSHOT_UNKNOWN_SOURCE')
    source = source[:start] + fragment.replace(anchor, HOOK + anchor, 1) + source[end:]
    result = source.encode('utf-8')
    compile(result, 'october_2026_close.py', 'exec')
    return result
