"""Build inert HTML + full current chemistry data, without importing the bot."""
import base64
import gzip
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from lab_isolated_data import load_candidate


def build():
    data = load_candidate()
    html = data['HTML'].replace(
        '<script src="https://telegram.org/js/telegram-web-app.js"></script>',
        '<script>window.Telegram={WebApp:{initData:"",initDataUnsafe:{},ready(){},expand(){}}};</script>')
    html = html.replace('<body>', '<body><div style="padding:6px 12px;background:#F4D9E6;color:#171719;font:12px sans-serif">Тестовая лаборатория · Статистика бота не сохраняется</div>', 1)
    atrament = (ROOT/'vendor/atrament/index.cjs').read_text()
    atrament_license = (ROOT/'vendor/atrament/LICENSE.md').read_text()
    atrament_script = '<script>/*\n'+atrament_license+'\n*/\nwindow.LessonAtrament=(()=>{const exports={};\n'+atrament+'\nreturn exports.default;})();</script>'
    html = html.replace('</head>', atrament_script+'</head>', 1)
    # Atrament owns smoothing; do not expose the unrelated legacy finish filter.
    html = re.sub(r'<label[^>]*><input id="lessonBeautify"[^>]*>.*?</label>',
                  '<input id="lessonBeautify" type="checkbox" checked hidden>', html, count=1)
    # Teacher pilot exposes only the two lesson workflows.
    html = re.sub(r'<button(?: class="on")? data-page="(?:work|oge|ege|exam|stats)">.*?</button>\n?', '', html)
    html = re.sub(r'<div class="lab-nav">.*?</div>', '', html, count=1, flags=re.S)
    html = html.replace('Опыты, тренажёры и экзаменационная практика',
                        'Свободный опыт и режим урока')
    for page in ('work', 'oge', 'ege', 'exam', 'stats'):
        html = html.replace(f'<section id="{page}" class="page">',
                            f'<section id="{page}" class="page" hidden>')
    # This comparison screen exists only in the isolated bundle, never in the bot.
    pen_test = (ROOT/'preview/pen-comparison.html').read_text()
    vendor = (ROOT/'vendor/perfect-freehand/index.cjs').read_text()
    license_text = (ROOT/'vendor/perfect-freehand/LICENSE').read_text()
    pen_test = pen_test.replace('__PFH_VENDOR__', vendor).replace('__PFH_LICENSE_COMMENT__', '/*\n'+license_text+'\n*/')
    html = html.replace('<button id="lessonPilotHelp"', '<button id="penCompareOpen" type="button">Проверить ручку</button>\n <button id="lessonPilotHelp"', 1)
    html = html.replace('</body>', pen_test+'\n</body>', 1)
    payload = {'ok': True, 'data': {
        'reagents': data['REAGENTS'], 'reactions': data['reaction_payload'](),
        'medium_reactions': data['MEDIUM_REACTIONS'],
        'lab': ['cuso4','fecl3','na2co3','nacl','na2so4'],
        'tools': ['naoh','hcl','agno3','bacl2'],
        'task6': [], 'oge12': [], 'oge23': [],
        'task6_progress': {}, 'task6_session': None,
        'stats': {'experiments':0,'predictions':0,'accuracy':0,'labworks_completed':0},
        'coverage': {'substances':len(data['REAGENTS']), 'reactions':len(data['reaction_payload']()),
                     'medium_reactions':len(data['MEDIUM_REACTIONS'])}, 'preview':True}}
    # No timestamps: same reviewed runtime files always produce the same bundle.
    names = ['ege_lab_webapp.py','ege_lab_substances.py','ege_lab_inorganic_reactions.py',
             'ege_lab_exchange_matrix.py','ege_lab_mn_cr_pdf_import.py','ege_task6_reactions.py',
             'deploy/build_lab_sandbox.py','preview/pen-comparison.html',
             'vendor/perfect-freehand/index.cjs','vendor/perfect-freehand/LICENSE',
             'vendor/atrament/index.cjs','vendor/atrament/LICENSE.md']
    hashes = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    runtime_id = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:16]
    html_bytes = html.encode()
    payload_bytes = json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    bundle = {'format':'ege-lab-sandbox-v1','build':runtime_id,'source_sha256':hashes,
              'html_sha256':hashlib.sha256(html_bytes).hexdigest(),
              'payload_sha256':hashlib.sha256(payload_bytes).hexdigest(),
              'html_gzip_base64':base64.b64encode(gzip.compress(html_bytes,mtime=0)).decode(),
              'payload_gzip_base64':base64.b64encode(gzip.compress(payload_bytes,mtime=0)).decode()}
    return json.dumps(bundle,sort_keys=True,separators=(',',':')).encode()


if __name__ == '__main__':
    out=ROOT/'preview/lab-sandbox/bundle.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    raw=build();out.write_bytes(raw)
    print('SANDBOX_BUNDLE',len(raw),hashlib.sha256(raw).hexdigest())
