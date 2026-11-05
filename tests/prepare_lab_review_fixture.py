"""Full current laboratory payload for isolated browser tests, no live imports."""
import json
from pathlib import Path
from lab_isolated_data import load_candidate

data = load_candidate()
out = Path('lab-visual-preview')
out.mkdir(exist_ok=True)
(out/'review.html').write_text(data['HTML'])
(out/'review.json').write_text(json.dumps({'ok':True,'data':{
    'reagents':data['REAGENTS'],'reactions':data['reaction_payload'](),
    'medium_reactions':data['MEDIUM_REACTIONS'],
    'lab':[],'tools':[],'task6':[],'oge12':[],'oge23':[],
    'task6_progress':{},'task6_session':None,
    'stats':{'experiments':0,'predictions':0,'accuracy':0,'labworks_completed':0},
    'coverage':{'substances':len(data['REAGENTS']),'reactions':len(data['reaction_payload']())},
    'preview':True}},ensure_ascii=False))
print('FULL_CURRENT_BROWSER_FIXTURE_OK')
