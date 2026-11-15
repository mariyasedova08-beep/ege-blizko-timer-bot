"""Build review copies only; never install, restart or connect to production."""
import argparse
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def decorate(html, surface, enabled=False):
    if surface not in {'student', 'teacher', 'lab'}:
        raise ValueError('Unknown surface')
    if 'data-ege-december-package' in html:
        raise ValueError('Theme already included')
    if html.lower().count('</head>') != 1 or html.lower().count('</body>') != 1:
        raise ValueError('Expected one complete HTML document')
    css = (ROOT / 'theme/december.css').read_text()
    js = (ROOT / 'theme/december.js').read_text()
    mascot = base64.b64encode((ROOT / 'theme/kulek.webp').read_bytes()).decode()
    style = '<style data-ege-december-package="2026">' + css + '</style>\n'
    script = ('<script data-ege-december-package="2026" data-enabled="' + str(enabled).lower()
              + '" data-surface="' + surface + '" data-mascot="data:image/webp;base64,' + mascot + '">'
              + js + '</script>\n')
    head = html.lower().index('</head>')
    html = html[:head] + style + html[head:]
    body = html.lower().index('</body>')
    return html[:body] + script + html[body:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--surface', choices=['student', 'teacher', 'lab'], required=True)
    parser.add_argument('--enable-date-switch', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refuse to overwrite an existing file')
    if str(args.output.resolve()).startswith(('/opt/bots/', '/var/lib/')):
        raise SystemExit('Review output only; managed service paths refused')
    result = decorate(args.source.read_text(), args.surface, args.enable_date_switch)
    args.output.write_text(result)
    print('REVIEW_COPY_CREATED:', args.output)
    print('NO_DEPLOYMENT; activation:', '1 December 2026 00:00 Moscow' if args.enable_date_switch else 'disabled')


if __name__ == '__main__':
    main()
