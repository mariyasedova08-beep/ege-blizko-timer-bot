"""Pure, AST-scoped patch for both reviewed production variants of kulek_rewards."""
import ast
from pathlib import Path

HEADER = '''    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(9, 0):
        return
    key = previous_month_key(_month_key())
'''
REPLACEMENT = '''    now = datetime.now(bot.TIMEZONE)
    key = _october_close_key(now)
    if key is None:
        return
    if key == "2026-10" and not _october_probnik_ready():
        return
'''
INSTALL = '    current = month_payload(_month_key(), force=True)\n'
NEW_INSTALL = '''    import october_2026_close
    october_2026_close.install()

''' + INSTALL


def transform(data):
    source = data.decode('utf-8')
    for name in ('breakthrough_prompt_tick','monthly_close_tick','install'):
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name == name)
        lines = source.splitlines(keepends=True)
        a,b = sum(map(len,lines[:node.lineno-1])),sum(map(len,lines[:node.end_lineno]))
        fragment = source[a:b]
        old,new = (INSTALL,NEW_INSTALL) if name == 'install' else (HEADER,REPLACEMENT)
        if fragment.count(new) == 1:
            continue
        if fragment.count(old) != 1:
            raise ValueError('UNREVIEWED_OCTOBER_ANCHOR_'+name)
        source = source[:a]+fragment.replace(old,new,1)+source[b:]
    result = source.encode()
    compile(result,'kulek_rewards.py','exec')
    return result
