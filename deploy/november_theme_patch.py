"""Append a self-contained visual skin without replacing production HTML/JS."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- EGE-NOVEMBER-2026:STYLE -->'
SCRIPT = '<!-- EGE-NOVEMBER-2026:SCRIPT -->'


def transform(data, role, css=None, script=None):
    if role not in ('teacher', 'student'):
        raise ValueError('NOVEMBER_INVALID_ROLE')
    css = (ROOT/'ege_november_theme.css').read_text() if css is None else css
    script = (ROOT/'ege_november_theme.js').read_text() if script is None else script
    source = data.decode('utf-8')
    style_block = START+'\n<style id="ege-november-theme">\n'+css+'\n</style>\n'
    script_block = SCRIPT+'\n<script id="ege-november-decor" data-cabinet-role="'+role+'">\n'+script+'\n</script>\n'
    if START in source or SCRIPT in source:
        if source.count(style_block)==1 and source.count(script_block)==1:
            return data
        raise ValueError('NOVEMBER_EXISTING_THEME_DIFFERS')
    if source.count('</head>')!=1 or source.count('</body>')!=1 or 'id="app"' not in source:
        raise ValueError('NOVEMBER_UNKNOWN_HTML_STRUCTURE')
    source = source.replace('</head>',style_block+'</head>',1)
    source = source.replace('</body>',script_block+'</body>',1)
    return source.encode('utf-8')
