"""Interactive chemistry laboratory Mini App for EGE BLIZKO."""
import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import run_bot_live90 as live90
from ege_lab_substances import REAGENTS as LAB_REAGENTS, category_counts
from ege_lab_inorganic_reactions import EXTRA_REACTIONS, REACTION_VARIANTS, validate_reactions
from ege_task6_bank import TASK6_BANK, validate_task6_bank
from ege_task6_reactions import TASK6_REACTIONS, TASK6_VARIANTS, validate_task6_reactions
import ege_task6_progress

bot = live90.bot
DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
URL = os.getenv(
    "EGE_LAB_WEBAPP_URL",
    f"https://{DOMAIN}/lab-app" if DOMAIN else "",
).strip()
BUILD = "20261009-oge23-general-lab-visuals-v1"

def _oge12_bank_payload():
    try:
        from oge_task12_bank import OGE12_BANK
        return OGE12_BANK
    except Exception as exc:
        print(f"OGE12 bank load error: {type(exc).__name__}: {exc}", flush=True)
        return []

def _oge23_bank_payload():
    try:
        from oge_task23_bank import OGE23_BANK
        return OGE23_BANK
    except Exception as exc:
        print(f"OGE23 bank load error: {type(exc).__name__}: {exc}", flush=True)
        return []
_INSTALLED = False
_previous_get = None
_previous_post = None
_previous_hub = None

# id -> (formula, category, solution colour)
REAGENTS = {
    "hcl": ("HCl", "Кислоты", "#f8fbff"),
    "h2so4": ("H₂SO₄", "Кислоты", "#f8fbff"),
    "hno3": ("HNO₃", "Кислоты", "#f8fbff"),
    "naoh": ("NaOH", "Основания", "#f8fbff"),
    "koh": ("KOH", "Основания", "#f8fbff"),
    "nh3": ("NH₃·H₂O", "Основания", "#f8fbff"),
    "agno3": ("AgNO₃", "Соли", "#f8fbff"),
    "bacl2": ("BaCl₂", "Соли", "#f8fbff"),
    "cacl2": ("CaCl₂", "Соли", "#f8fbff"),
    "cuso4": ("CuSO₄", "Соли", "#42baf5"),
    "feso4": ("FeSO₄", "Соли", "#bfe7c5"),
    "fecl3": ("FeCl₃", "Соли", "#d99d2b"),
    "znso4": ("ZnSO₄", "Соли", "#f8fbff"),
    "alcl3": ("AlCl₃", "Соли", "#f8fbff"),
    "pbno3": ("Pb(NO₃)₂", "Соли", "#f8fbff"),
    "na2co3": ("Na₂CO₃", "Соли", "#f8fbff"),
    "na2so3": ("Na₂SO₃", "Соли", "#f8fbff"),
    "na2s": ("Na₂S", "Соли", "#f8fbff"),
    "na2sio3": ("Na₂SiO₃", "Соли", "#f8fbff"),
    "ki": ("KI", "Соли", "#f8fbff"),
    "kbr": ("KBr", "Соли", "#f8fbff"),
    "k2cro4": ("K₂CrO₄", "Соли", "#f5d532"),
    "k2cr2o7": ("K₂Cr₂O₇", "Соли", "#ef7c2d"),
    "kmno4": ("KMnO₄", "Соли", "#b32a9a"),
    "nh4cl": ("NH₄Cl", "Соли", "#f8fbff"),
    "nacl": ("NaCl", "Соли", "#f8fbff"),
    "na2so4": ("Na₂SO₄", "Соли", "#f8fbff"),
}

# The standalone catalogue is now authoritative; the legacy inline block above
# remains temporarily for a low-risk migration and is overridden here.
REAGENTS = dict(LAB_REAGENTS)

# a, b, equation, kind(p precipitate/g gas/c colour/n no visible/x combo),
# observation, solution colour, precipitate colour, gas, heat_required
REACTIONS = [
    ("agno3","hcl","AgNO₃ + HCl → AgCl↓ + HNO₃","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("agno3","nacl","AgNO₃ + NaCl → AgCl↓ + NaNO₃","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("agno3","kbr","AgNO₃ + KBr → AgBr↓ + KNO₃","p","кремовый AgBr","#f8fbff","#eadb9a","",0),
    ("agno3","ki","AgNO₃ + KI → AgI↓ + KNO₃","p","жёлтый AgI","#f8fbff","#f4d534","",0),
    ("agno3","na2co3","2AgNO₃ + Na₂CO₃ → Ag₂CO₃↓ + 2NaNO₃","p","жёлтый Ag₂CO₃","#f8fbff","#e6cf44","",0),
    ("agno3","na2s","2AgNO₃ + Na₂S → Ag₂S↓ + 2NaNO₃","p","чёрный Ag₂S","#f8fbff","#151515","",0),
    ("agno3","fecl3","3AgNO₃ + FeCl₃ → 3AgCl↓ + Fe(NO₃)₃","p","белый AgCl","#fff3e8","#ffffff","",0),
    ("agno3","alcl3","3AgNO₃ + AlCl₃ → 3AgCl↓ + Al(NO₃)₃","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("agno3","nh4cl","AgNO₃ + NH₄Cl → AgCl↓ + NH₄NO₃","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("agno3","cacl2","2AgNO₃ + CaCl₂ → 2AgCl↓ + Ca(NO₃)₂","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("agno3","bacl2","2AgNO₃ + BaCl₂ → 2AgCl↓ + Ba(NO₃)₂","p","белый AgCl","#f8fbff","#ffffff","",0),
    ("bacl2","h2so4","BaCl₂ + H₂SO₄ → BaSO₄↓ + 2HCl","p","белый BaSO₄","#f8fbff","#ffffff","",0),
    ("bacl2","na2so4","BaCl₂ + Na₂SO₄ → BaSO₄↓ + 2NaCl","p","белый BaSO₄","#f8fbff","#ffffff","",0),
    ("bacl2","na2co3","BaCl₂ + Na₂CO₃ → BaCO₃↓ + 2NaCl","p","белый BaCO₃","#f8fbff","#ffffff","",0),
    ("bacl2","na2so3","BaCl₂ + Na₂SO₃ → BaSO₃↓ + 2NaCl","p","белый BaSO₃","#f8fbff","#ffffff","",0),
    ("bacl2","k2cro4","BaCl₂ + K₂CrO₄ → BaCrO₄↓ + 2KCl","p","жёлтый BaCrO₄","#f8fbff","#f2d327","",0),
    ("cacl2","na2co3","CaCl₂ + Na₂CO₃ → CaCO₃↓ + 2NaCl","p","белый CaCO₃","#f8fbff","#ffffff","",0),
    ("cacl2","na2so3","CaCl₂ + Na₂SO₃ → CaSO₃↓ + 2NaCl","p","белый CaSO₃","#f8fbff","#ffffff","",0),
    ("cacl2","na2sio3","CaCl₂ + Na₂SiO₃ → CaSiO₃↓ + 2NaCl","p","белый CaSiO₃","#f8fbff","#ffffff","",0),
    ("cuso4","naoh","CuSO₄ + 2NaOH → Cu(OH)₂↓ + Na₂SO₄","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),
    ("cuso4","koh","CuSO₄ + 2KOH → Cu(OH)₂↓ + K₂SO₄","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),
    ("cuso4","na2s","CuSO₄ + Na₂S → CuS↓ + Na₂SO₄","p","чёрный CuS","#f8fbff","#151515","",0),
    ("feso4","naoh","FeSO₄ + 2NaOH → Fe(OH)₂↓ + Na₂SO₄","p","светло-зелёный Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("feso4","koh","FeSO₄ + 2KOH → Fe(OH)₂↓ + K₂SO₄","p","светло-зелёный Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("feso4","na2s","FeSO₄ + Na₂S → FeS↓ + Na₂SO₄","p","чёрный FeS","#f8fbff","#181818","",0),
    ("fecl3","naoh","FeCl₃ + 3NaOH → Fe(OH)₃↓ + 3NaCl","p","бурый Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("fecl3","koh","FeCl₃ + 3KOH → Fe(OH)₃↓ + 3KCl","p","бурый Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("fecl3","nh3","FeCl₃ + 3NH₃·H₂O → Fe(OH)₃↓ + 3NH₄Cl","p","бурый Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("fecl3","na2co3","2FeCl₃ + 3Na₂CO₃ + 3H₂O → 2Fe(OH)₃↓ + 3CO₂↑ + 6NaCl","x","бурый осадок + CO₂","#fff3e8","#9a4a2b","CO₂",0),
    ("znso4","naoh","ZnSO₄ + 2NaOH → Zn(OH)₂↓ + Na₂SO₄","p","белый Zn(OH)₂","#f8fbff","#ffffff","",0),
    ("znso4","koh","ZnSO₄ + 2KOH → Zn(OH)₂↓ + K₂SO₄","p","белый Zn(OH)₂","#f8fbff","#ffffff","",0),
    ("znso4","na2s","ZnSO₄ + Na₂S → ZnS↓ + Na₂SO₄","p","белый ZnS","#f8fbff","#ffffff","",0),
    ("alcl3","naoh","AlCl₃ + 3NaOH → Al(OH)₃↓ + 3NaCl","p","белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("alcl3","koh","AlCl₃ + 3KOH → Al(OH)₃↓ + 3KCl","p","белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("alcl3","na2s","2AlCl₃ + 3Na₂S + 6H₂O → 2Al(OH)₃↓ + 3H₂S↑ + 6NaCl","x","белый осадок + H₂S","#f8fbff","#ffffff","H₂S",0),
    ("pbno3","ki","Pb(NO₃)₂ + 2KI → PbI₂↓ + 2KNO₃","p","ярко-жёлтый PbI₂","#f8fbff","#f4c928","",0),
    ("pbno3","kbr","Pb(NO₃)₂ + 2KBr → PbBr₂↓ + 2KNO₃","p","белый PbBr₂","#f8fbff","#f6f1d8","",0),
    ("pbno3","h2so4","Pb(NO₃)₂ + H₂SO₄ → PbSO₄↓ + 2HNO₃","p","белый PbSO₄","#f8fbff","#ffffff","",0),
    ("pbno3","na2s","Pb(NO₃)₂ + Na₂S → PbS↓ + 2NaNO₃","p","чёрный PbS","#f8fbff","#151515","",0),
    ("na2co3","hcl","Na₂CO₃ + 2HCl → 2NaCl + CO₂↑ + H₂O","g","пузырьки CO₂","#f8fbff","","CO₂",0),
    ("na2co3","h2so4","Na₂CO₃ + H₂SO₄ → Na₂SO₄ + CO₂↑ + H₂O","g","пузырьки CO₂","#f8fbff","","CO₂",0),
    ("na2co3","hno3","Na₂CO₃ + 2HNO₃ → 2NaNO₃ + CO₂↑ + H₂O","g","пузырьки CO₂","#f8fbff","","CO₂",0),
    ("na2so3","hcl","Na₂SO₃ + 2HCl → 2NaCl + SO₂↑ + H₂O","g","SO₂, резкий запах","#f8fbff","","SO₂",0),
    ("na2so3","h2so4","Na₂SO₃ + H₂SO₄ → Na₂SO₄ + SO₂↑ + H₂O","g","SO₂, резкий запах","#f8fbff","","SO₂",0),
    ("na2s","hcl","Na₂S + 2HCl → 2NaCl + H₂S↑","g","H₂S, неприятный запах","#f8fbff","","H₂S",0),
    ("na2s","h2so4","Na₂S + H₂SO₄ → Na₂SO₄ + H₂S↑","g","H₂S, неприятный запах","#f8fbff","","H₂S",0),
    ("na2sio3","hcl","Na₂SiO₃ + 2HCl → H₂SiO₃↓ + 2NaCl","p","белый студенистый H₂SiO₃","#f8fbff","#ffffff","",0),
    ("na2sio3","h2so4","Na₂SiO₃ + H₂SO₄ → H₂SiO₃↓ + Na₂SO₄","p","белый студенистый H₂SiO₃","#f8fbff","#ffffff","",0),
    ("nh4cl","naoh","NH₄Cl + NaOH —t°→ NaCl + NH₃↑ + H₂O","g","NH₃ после нагревания","#f8fbff","","NH₃",1),
    ("nh4cl","koh","NH₄Cl + KOH —t°→ KCl + NH₃↑ + H₂O","g","NH₃ после нагревания","#f8fbff","","NH₃",1),
    ("k2cro4","hcl","2K₂CrO₄ + 2HCl ⇄ K₂Cr₂O₇ + 2KCl + H₂O","c","жёлтый → оранжевый","#ef7c2d","","",0),
    ("k2cr2o7","naoh","K₂Cr₂O₇ + 2NaOH ⇄ K₂CrO₄ + Na₂CrO₄ + H₂O","c","оранжевый → жёлтый","#f5d532","","",0),
    ("k2cr2o7","koh","K₂Cr₂O₇ + 2KOH ⇄ 2K₂CrO₄ + H₂O","c","оранжевый → жёлтый","#f5d532","","",0),
    ("kmno4","na2so3","2KMnO₄ + 3Na₂SO₃ + H₂O → 2MnO₂↓ + 3Na₂SO₄ + 2KOH","p","бурый MnO₂","#f3eee6","#69432e","",0),
    ("hcl","naoh","HCl + NaOH → NaCl + H₂O","n","без видимого признака","#f8fbff","","",0),
    ("hcl","koh","HCl + KOH → KCl + H₂O","n","без видимого признака","#f8fbff","","",0),
    ("h2so4","naoh","H₂SO₄ + 2NaOH → Na₂SO₄ + 2H₂O","n","без видимого признака","#f8fbff","","",0),
    ("h2so4","koh","H₂SO₄ + 2KOH → K₂SO₄ + 2H₂O","n","без видимого признака","#f8fbff","","",0),
    ("hno3","naoh","HNO₃ + NaOH → NaNO₃ + H₂O","n","без видимого признака","#f8fbff","","",0),
    ("hno3","koh","HNO₃ + KOH → KNO₃ + H₂O","n","без видимого признака","#f8fbff","","",0),
]

REACTIONS.extend(EXTRA_REACTIONS)
REACTIONS.extend(TASK6_REACTIONS)
validate_reactions(set(REAGENTS))
validate_task6_reactions(set(REAGENTS))
validate_task6_bank(set(REAGENTS))

def pair_key(a, b):
    return "|".join(sorted((a, b)))

def reaction_payload():
    payload = [
        {
            "a":a,"b":b,"eq":eq,"t":kind,"sign":sign,"sol":sol,
            "ppt":ppt,"gas":gas,"heat":bool(heat),"excess":"","condition":""
        }
        for a,b,eq,kind,sign,sol,ppt,gas,heat in REACTIONS
    ]
    payload.extend(dict(item) for item in REACTION_VARIANTS)
    payload.extend(dict(item) for item in TASK6_VARIANTS)
    return payload

def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ege_lab_stats(
                uid INTEGER PRIMARY KEY,
                experiments INTEGER NOT NULL DEFAULT 0,
                predictions INTEGER NOT NULL DEFAULT 0,
                correct INTEGER NOT NULL DEFAULT 0,
                labworks INTEGER NOT NULL DEFAULT 0,
                updated TEXT
            )"""
        )
        conn.commit()

def stats(uid):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT experiments,predictions,correct,labworks FROM ege_lab_stats WHERE uid=?",
            (int(uid),),
        ).fetchone()
    a,b,c,d = map(int, row or (0,0,0,0))
    return {
        "experiments": a,
        "predictions": b,
        "correct_predictions": c,
        "labworks_completed": d,
        "accuracy": round(100*c/b) if b else 0,
    }

def record_event(uid, event_type, correct=False):
    ensure_tables()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """INSERT INTO ege_lab_stats(uid,updated) VALUES(?,?)
               ON CONFLICT(uid) DO UPDATE SET updated=excluded.updated""",
            (int(uid), now),
        )
        if event_type == "experiment":
            conn.execute("UPDATE ege_lab_stats SET experiments=experiments+1 WHERE uid=?", (int(uid),))
        elif event_type == "prediction":
            conn.execute(
                "UPDATE ege_lab_stats SET predictions=predictions+1,correct=correct+? WHERE uid=?",
                (1 if correct else 0, int(uid)),
            )
        elif event_type == "labwork":
            conn.execute("UPDATE ege_lab_stats SET labworks=labworks+1 WHERE uid=?", (int(uid),))
        conn.commit()
    return stats(uid)

def validate_init_data(raw, max_age=86400):
    try:
        fields = dict(parse_qsl(str(raw or ""), keep_blank_values=True))
        received = fields.pop("hash", "")
        token = os.getenv("BOT_TOKEN", "")
        if not received or not token:
            return None
        check = "\n".join(f"{k}={v}" for k,v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected):
            return None
        now = int(time.time())
        auth = int(fields.get("auth_date") or 0)
        if auth <= 0 or auth > now + 300 or now - auth > max_age:
            return None
        user = json.loads(fields.get("user") or "{}")
        return int(user["id"])
    except Exception:
        return None

HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--pink:#f00087;--soft:#f4d9e6;--milk:#f8f5f2;--ink:#171719}
*{box-sizing:border-box}body{margin:0;background:var(--milk);color:var(--ink);font:14px system-ui,-apple-system,sans-serif}
.app{max-width:1180px;margin:auto;padding:14px}.logo{color:var(--pink);font-weight:900}.tabs,.grid,.answers,.tools,.stats{display:grid;gap:8px}
.lab-shell{display:grid;grid-template-columns:240px minmax(0,1fr) 210px;gap:12px;align-items:stretch}
.lab-side,.lab-controls{background:#fff;border:1px solid #efc5da;border-radius:22px;padding:13px;box-shadow:0 8px 25px rgba(35,20,28,.05)}
.lab-side h2,.lab-controls h2,.bench-head h2{margin:0 0 10px;font-size:16px}
.reagent-search{display:grid;grid-template-columns:minmax(0,1fr) 38px;gap:6px;margin:10px 0 8px}
.reagent-search input{width:100%;min-width:0;border:1px solid #efc5da;background:#fff;border-radius:13px;padding:10px 11px;font:700 13px system-ui,-apple-system,sans-serif;color:#171719;outline:none}
.reagent-search input:focus{border-color:#f00087;box-shadow:0 0 0 2px rgba(240,0,135,.10)}
.reagent-search button{padding:0;width:38px;height:38px;border-radius:12px;font-size:15px}
.reagent-search-hint{font-size:10px;color:#8b8387;margin:0 0 8px}
.reagent-empty{padding:14px 10px;border:1px dashed #efc5da;border-radius:14px;background:#fff8fb;color:#746a6f;font-size:12px;text-align:center}
.reagent-filters{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin:10px 0 12px}
.reagent-filter{border:1px solid #f0cadc;background:#fff8fb;color:#4c4046;border-radius:999px;padding:8px 7px;font-size:11px;font-weight:900}
.reagent-filter.on{background:var(--pink);color:#fff;border-color:var(--pink)}
.reagent-group{margin:4px 0 12px}
.reagent-group-title{font-size:11px;font-weight:950;color:#2d2629;background:#f8e6ef;border-radius:999px;padding:7px 10px;margin:4px 0 7px;display:inline-flex}
.reagent-list{display:flex;flex-direction:column;gap:7px;max-height:590px;overflow:auto;padding-right:2px}
.reagent-item{width:100%;display:flex;align-items:center;gap:9px;text-align:left;padding:9px 10px;border-radius:14px;border:1px solid #eee1e8;background:#fff}
.reagent-item:hover,.reagent-item:active{background:#fff5fa;border-color:#f1bad6}
.drop-icon{width:24px;height:32px;position:relative;flex:0 0 24px}
.drop-icon:before{content:"";position:absolute;left:5px;top:2px;width:13px;height:18px;border-radius:50% 50% 55% 55%;background:var(--rc);transform:rotate(45deg);box-shadow:inset 3px 3px 5px rgba(255,255,255,.55),0 2px 4px rgba(0,0,0,.08)}
.rformula{font-weight:900;font-size:13px}.rcat{font-size:10px;color:#8b8387;margin-top:2px}
.lab-bench{background:linear-gradient(180deg,#fff 0 68%,#f2ece8 68% 73%,#d7c0ad 73% 100%);border:1px solid #eadfe4;border-radius:22px;min-height:565px;padding:14px;position:relative;overflow:hidden;box-shadow:0 8px 25px rgba(35,20,28,.05);align-self:start;width:100%}
.bench-head{display:flex;justify-content:space-between;gap:10px;align-items:center}
.bench-hint{font-size:11px;color:#81797d}
.rack-wrap{position:absolute;left:7%;right:7%;bottom:88px}
.rack-board{position:absolute;left:-2%;right:-2%;top:82px;height:26px;border-radius:9px;background:linear-gradient(#7f6653,#4c392d);box-shadow:0 7px 12px rgba(64,40,28,.25);z-index:0}
.rack-board:before,.rack-board:after{content:"";position:absolute;top:20px;width:16px;height:100px;background:linear-gradient(90deg,#705642,#4d382c);border-radius:4px}
.rack-board:before{left:5%}.rack-board:after{right:5%}
.rack{position:relative;z-index:2;display:grid;grid-template-columns:repeat(4,1fr);gap:20px;align-items:end;padding:0 9%}
.tube-slot{position:relative;min-width:0}
.mobile-tube-picker{display:none;gap:7px;justify-content:center;margin:12px 0 4px}
.mobile-tube-picker button{width:42px;height:42px;padding:0;border-radius:13px;font-size:14px}
.mobile-tube-picker button.on{background:var(--pink);color:#fff;border-color:var(--pink)}
.tube-callout{position:absolute;z-index:30;width:300px;left:50%;bottom:calc(100% + 18px);transform:translateX(-50%);pointer-events:auto}
.tube-callout.edge-left{left:0;transform:none}
.tube-callout.edge-right{left:auto;right:0;transform:none}
.tube-callout .reaction-card{margin:0;box-shadow:0 14px 34px rgba(240,0,135,.22)}
.tube-callout:after{content:"";position:absolute;left:50%;bottom:-10px;width:18px;height:18px;background:#f9dce9;border-right:2px solid #f00087;border-bottom:2px solid #f00087;transform:translateX(-50%) rotate(45deg);pointer-events:none}
.tube-callout.edge-left:after{left:21%}.tube-callout.edge-right:after{left:79%}
.lab-controls .control-stack{display:flex;flex-direction:column;gap:8px}
.lab-controls button{width:100%}
.selected-card{background:#fff7fb;border:1px solid #f1c8dc;border-radius:16px;padding:10px;margin-bottom:10px}
.selected-card b{display:block;font-size:12px}.selected-card span{display:block;font-size:10px;color:#7f777b;margin-top:3px}
.lab-result{margin-top:12px;padding:12px;border-radius:15px;background:#fff4f9;border:1px solid #f1c8dc;min-height:74px;line-height:1.4}
.reaction-card{margin-top:4px;border-radius:18px;border:2px solid #f00087;background:linear-gradient(145deg,#fff8fc,#f9dce9);padding:13px;box-shadow:0 10px 24px rgba(240,0,135,.14);animation:reactionPop .34s ease-out}
.reaction-card.no-visible{border-color:#cfc6cb;background:#fff}
.reaction-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.reaction-status{display:inline-flex;align-items:center;gap:6px;background:#f00087;color:#fff;font-size:11px;font-weight:950;border-radius:999px;padding:6px 9px}
.reaction-card.no-visible .reaction-status{background:#8e858a}
.reaction-sign{font-size:15px;font-weight:950;line-height:1.25;color:#171719;margin-bottom:8px}
.reaction-equation{background:rgba(255,255,255,.82);border:1px solid rgba(240,0,135,.22);border-radius:13px;padding:9px 10px;font-size:13px;font-weight:900;line-height:1.25;letter-spacing:0;white-space:nowrap;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;touch-action:pan-x;cursor:grab;scrollbar-width:auto;scrollbar-color:#8f878b #f6edf2}
.reaction-equation:active{cursor:grabbing}
.reaction-equation::-webkit-scrollbar{height:10px}
.reaction-equation::-webkit-scrollbar-track{background:#f6edf2;border-radius:999px}
.reaction-equation::-webkit-scrollbar-thumb{background:#8f878b;border-radius:999px;border:2px solid #f6edf2}
.reaction-note{font-size:10px;color:#7c7277;margin-top:7px}
@keyframes reactionPop{0%{transform:scale(.97);opacity:.35}100%{transform:scale(1);opacity:1}}
.mode-note{font-size:10px;color:#8b8387;margin-top:8px}

.tabs{grid-template-columns:repeat(4,1fr);margin:12px 0}.tabs button{font-size:12px}
button{border:1px solid #efc5da;background:#fff;border-radius:14px;padding:11px 9px;font-weight:800;color:#222}
button.on,button.primary{background:var(--pink);color:#fff}.page{display:none}.page.on{display:block}
.card{background:#fff;border:1px solid #efc5da;border-radius:20px;padding:14px;margin-top:10px}
.rack{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.tube{height:185px;border:2px solid rgba(127,137,151,.52);border-top:0;border-radius:0 0 30px 30px;position:relative;overflow:hidden;background:linear-gradient(90deg,rgba(255,255,255,.92) 0 13%,rgba(226,233,241,.35) 18%,rgba(255,255,255,.72) 50%,rgba(214,224,235,.35) 82%,rgba(255,255,255,.9) 100%);box-shadow:inset 5px 0 8px rgba(255,255,255,.75),inset -5px 0 7px rgba(109,122,140,.12),0 5px 12px rgba(54,42,51,.10);transition:.22s}
.tube:before{content:"";position:absolute;z-index:8;left:-3px;right:-3px;top:-2px;height:12px;border:2px solid rgba(120,130,143,.52);border-radius:50%;background:rgba(255,255,255,.75);box-shadow:inset 0 -2px 2px rgba(113,126,143,.12)}
.tube:after{content:"";position:absolute;z-index:7;left:13%;top:14px;width:10%;height:72%;border-radius:8px;background:linear-gradient(rgba(255,255,255,.75),rgba(255,255,255,.08));filter:blur(.2px);pointer-events:none}
.tube.on{border-color:var(--pink);box-shadow:inset 5px 0 8px rgba(255,255,255,.75),inset -5px 0 7px rgba(109,122,140,.12),0 0 0 2px rgba(240,0,135,.11),0 6px 16px rgba(240,0,135,.16)}
.liq{position:absolute;bottom:0;left:2px;right:2px;height:0;z-index:1;transition:height .5s ease,background 1.1s ease;box-shadow:inset 0 8px 11px rgba(255,255,255,.24),inset 0 -8px 10px rgba(0,0,0,.06)}
.liq:before{content:"";position:absolute;left:0;right:0;top:-5px;height:10px;border-radius:50%;background:inherit;filter:brightness(1.08);box-shadow:inset 0 2px 3px rgba(255,255,255,.58),0 1px 1px rgba(0,0,0,.10)}
.pptLayer{position:absolute;z-index:3;left:3px;right:3px;bottom:2px;height:54%;pointer-events:none;overflow:hidden;border-radius:0 0 24px 24px}
.particle{position:absolute;bottom:var(--b);left:var(--l);width:var(--s);height:var(--s);background:var(--pc);opacity:.90;filter:drop-shadow(0 1px 1px rgba(0,0,0,.13));animation:settle .9s cubic-bezier(.2,.7,.3,1) both}
.particle.floc{border-radius:44% 56% 48% 52%;transform:rotate(var(--r)) scaleX(1.45);filter:blur(.25px) drop-shadow(0 1px 1px rgba(0,0,0,.11))}
.particle.gel{border-radius:50% 44% 52% 46%;opacity:.62;filter:blur(1.2px);transform:scaleX(1.8)}
.particle.crystal{border-radius:2px;transform:rotate(var(--r));opacity:.94;box-shadow:0 0 2px rgba(255,255,255,.45)}
.particle.fine{border-radius:50%;opacity:.72;filter:blur(.35px)}
@keyframes settle{from{transform:translateY(-75px) scale(.55);opacity:.1}to{opacity:.88}}
.bubbleLayer{position:absolute;z-index:6;left:3px;right:3px;bottom:2px;height:82%;overflow:visible;border-radius:0 0 24px 24px;pointer-events:none}
.bubbleLayer.strong:before{content:"";position:absolute;left:6%;right:6%;bottom:6%;height:36%;border-radius:50%;background:radial-gradient(ellipse at center,rgba(255,255,255,.72) 0 16%,rgba(255,255,255,.24) 17% 48%,rgba(255,255,255,0) 70%);filter:blur(2px);animation:boilPulse .55s ease-in-out infinite alternate}
.boilLayer{position:absolute;z-index:5;left:4px;right:4px;bottom:2px;height:59%;overflow:hidden;border-radius:0 0 24px 24px;pointer-events:none}
.boilCell{position:absolute;bottom:2px;left:var(--l);width:var(--w);height:var(--h);border-radius:50% 50% 40% 40%;background:radial-gradient(ellipse at 50% 75%,rgba(255,255,255,.46),rgba(255,255,255,.08) 55%,transparent 70%);filter:blur(.4px);animation:boilCell var(--d) ease-in-out infinite;animation-delay:var(--delay)}
@keyframes boilCell{0%{transform:translateY(8px) scale(.75,.55);opacity:.2}40%{opacity:.85}100%{transform:translateY(-20px) scale(1.12,.95);opacity:.05}}
@keyframes boilPulse{from{transform:scale(.88,.7);opacity:.35}to{transform:scale(1.08,1.0);opacity:.8}}
.bubble{position:absolute;bottom:4px;left:var(--l);width:var(--s);height:var(--s);border:2.2px solid rgba(255,255,255,.98);border-radius:50%;background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.92) 0 16%,rgba(255,255,255,.28) 17% 42%,rgba(255,255,255,.07) 43% 100%);box-shadow:0 0 0 1px rgba(80,105,130,.26),inset -2px -2px 4px rgba(80,105,130,.16),0 2px 5px rgba(40,55,70,.15);animation:rise var(--d) ease-in infinite;animation-delay:var(--delay)}
.bubbleLayer.no2 .bubble{border-color:rgba(150,64,24,.96);background:radial-gradient(circle at 32% 28%,rgba(255,221,195,.92) 0 14%,rgba(202,92,38,.64) 15% 48%,rgba(137,55,22,.34) 49% 100%);box-shadow:0 0 0 1px rgba(114,43,16,.50),inset -2px -2px 4px rgba(108,40,15,.34),0 2px 6px rgba(92,37,17,.28)}
.surfaceFizz.no2 i{border-color:rgba(153,65,24,.95);background:rgba(198,86,34,.62);box-shadow:0 0 0 1px rgba(108,43,17,.42)}
.boilLayer.no2 .boilCell{background:radial-gradient(ellipse at 50% 75%,rgba(217,113,62,.62),rgba(150,61,25,.28) 55%,transparent 72%)}
.solidBed{position:absolute;left:12%;right:12%;bottom:6%;height:26%;z-index:5;pointer-events:none}
.solidChunk{position:absolute;left:var(--l);bottom:var(--b);width:var(--s);height:calc(var(--s)*.62);background:var(--sc);border-radius:35% 45% 38% 48%;transform:rotate(var(--r));box-shadow:inset 2px 2px 3px rgba(255,255,255,.48),0 1px 2px rgba(0,0,0,.16)}
.metalReactionBed{position:absolute;z-index:5;left:10%;right:10%;bottom:5%;height:30%;pointer-events:none}
.metalPiece{position:absolute;left:12%;right:12%;bottom:5%;height:34%;border-radius:45% 52% 42% 50%;background:var(--metalColor);box-shadow:inset 4px 4px 7px rgba(255,255,255,.34),inset -3px -3px 6px rgba(0,0,0,.16),0 2px 4px rgba(0,0,0,.18)}
.metalCrystal{position:absolute;left:var(--l);bottom:var(--b);width:var(--s);height:var(--s);background:var(--depositColor);border-radius:28% 58% 36% 60%;transform:rotate(var(--r));box-shadow:inset 1px 1px 2px rgba(255,255,255,.65),0 1px 2px rgba(0,0,0,.28);animation:depositGrow .65s ease-out both}
@keyframes depositGrow{from{transform:rotate(var(--r)) scale(.15);opacity:.1}to{transform:rotate(var(--r)) scale(1);opacity:1}}
.surfaceFizz{position:absolute;z-index:7;left:10%;right:10%;bottom:56%;height:16px;pointer-events:none}
.surfaceFizz i{position:absolute;bottom:0;left:var(--l);width:var(--s);height:var(--s);border-radius:50%;border:1.8px solid rgba(255,255,255,.98);background:rgba(255,255,255,.36);box-shadow:0 0 0 1px rgba(70,90,110,.2);animation:pop 1.15s ease-out infinite;animation-delay:var(--delay)}
.gasPlume{position:absolute;z-index:7;left:18%;right:18%;top:8px;height:44%;pointer-events:none;opacity:.72;filter:blur(4px);background:radial-gradient(ellipse at center,var(--gasColor) 0 25%,rgba(255,255,255,0) 70%);animation:plume 1.8s ease-in-out infinite alternate}
@keyframes rise{0%{transform:translateY(0) translateX(0) scale(.72);opacity:.35}10%{opacity:1}75%{transform:translateY(-92px) translateX(var(--drift)) scale(1.08);opacity:1}100%{transform:translateY(-138px) translateX(calc(var(--drift)*.5)) scale(1.18);opacity:.15}}
@keyframes pop{0%{transform:translateY(0) scale(.7);opacity:.2}55%{opacity:1}100%{transform:translateY(-18px) scale(1.3);opacity:0}}
@keyframes plume{from{transform:translateY(2px) scale(.9);opacity:.28}to{transform:translateY(-6px) scale(1.08);opacity:.7}}
.heatShimmer{position:absolute;z-index:6;left:12%;right:12%;top:11%;height:24%;background:repeating-linear-gradient(90deg,transparent 0 7px,rgba(240,0,135,.08) 8px 9px,transparent 10px 15px);filter:blur(3px);animation:shimmer .9s ease-in-out infinite alternate}
@keyframes shimmer{to{transform:translateY(-4px) skewX(-4deg);opacity:.35}}
.reactionGlow{position:absolute;z-index:4;inset:38% 4px 4px;border-radius:10px 10px 24px 24px;box-shadow:inset 0 0 18px rgba(255,255,255,.6);animation:flash 1s ease-out}
@keyframes flash{0%{background:rgba(255,255,255,.8)}100%{background:transparent}}
.tubeLabel{text-align:center;font-weight:800;margin-top:5px}.tubeSmall{text-align:center;font-size:11px;color:#777;min-height:30px}
.labVisual{display:flex;justify-content:center;margin:12px 0}.labVisual .tube{width:92px;height:190px}
.grid{grid-template-columns:repeat(3,1fr)}.grid button small{display:block;color:#777;font-weight:600;margin-top:3px}
.tools,.answers{grid-template-columns:1fr 1fr}.result{padding:10px;background:#fff3f9;border-radius:13px;margin-top:8px;min-height:44px}
.stats{grid-template-columns:1fr 1fr}.stat{background:#fff;border:1px solid #efc5da;border-radius:16px;padding:14px}.stat b{font-size:28px;color:var(--pink);display:block}
.oge-switch{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0 12px}
.oge-switch button{padding:12px}.oge-switch button.on{background:var(--pink);color:#fff;border-color:var(--pink)}
.oge-task{background:#fff;border:1px solid #efc5da;border-radius:20px;padding:14px}
.oge-kicker{font-size:11px;color:var(--pink);font-weight:900;margin-bottom:5px}.oge-title{font-size:18px;font-weight:950;line-height:1.2}
.oge-pair{margin-top:12px;padding:12px;border-radius:15px;background:#fff7fb;border:1px solid #f1c8dc;font-weight:900;font-size:15px}
.oge-options{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.oge-options button{min-height:48px;text-align:left}
.oge-options button.correct{background:#edf8f1;border-color:#a8d5b9}.oge-options button.wrong{background:#fff0f2;border-color:#e6a9b4}
.oge-demo{display:flex;justify-content:center;gap:28px;align-items:flex-end;margin:16px 0 6px;min-height:230px}
.oge-demo-one{width:106px}.oge-demo-two{width:106px}.oge-demo .tube{height:190px}
.oge-demo-label{text-align:center;font-size:11px;font-weight:900;margin-top:5px}

.oge-feedback{margin-top:10px}.oge-next{margin-top:10px;width:100%}
.oge23-wrap{display:grid;gap:11px}
.oge23-mode{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.oge23-mode button.on{background:var(--terracotta);color:#fff;border-color:var(--terracotta)}
.oge23-condition{padding:15px 16px;border:1px solid #ead4c7;border-radius:16px;background:#fffaf6;font-size:16px;line-height:1.55}
.oge23-condition b{color:var(--rose-deep);font-weight:750}
.oge23-step{padding:15px;border:1px solid #eadfd8;border-radius:17px;background:#fff}
.oge23-step h3{margin:0 0 8px;font-size:17px}
.oge23-step-note{font-size:14px;line-height:1.5;color:#81736d;margin-bottom:11px}
.oge23-reagents{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.oge23-reagent{min-height:72px;padding:9px 7px;text-align:center;border:1px solid #dfc8bb;border-radius:14px;background:#fffaf7}
.oge23-reagent b{display:block;font-size:15px;margin-bottom:4px}.oge23-reagent span{font-size:10px;color:#81736d}
.oge23-reagent.on{background:#f2ddd2;border-color:#c86f4a;box-shadow:0 0 0 2px rgba(200,111,74,.08)}
.oge23-reagent.disabled{opacity:.48}
.oge23-mainbtn{width:100%;margin-top:9px;min-height:44px}
.oge23-lab{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.oge23-bottle{min-width:0;padding:10px;border:1px solid #e6d7ce;border-radius:17px;background:#fffaf7}
.oge23-bottle-title{text-align:center;font-size:13px;font-weight:700;margin-bottom:7px}
.oge23-glass{width:74px;height:112px;margin:0 auto 9px;border:2px solid #bcc5ca;border-top:8px solid #dbe1e4;border-radius:9px 9px 22px 22px;position:relative;background:linear-gradient(90deg,rgba(255,255,255,.92),rgba(235,242,246,.48),rgba(255,255,255,.92));overflow:hidden}
.oge23-glass:after{content:"";position:absolute;left:5px;right:5px;bottom:5px;height:57%;border-radius:0 0 16px 16px;background:var(--bottle-color,rgba(223,235,241,.42));box-shadow:inset 0 7px 10px rgba(255,255,255,.30);opacity:.88}
.oge23-glass>i{position:absolute;z-index:3;left:5px;right:5px;bottom:calc(57% - 1px);height:7px;border-radius:50%;background:var(--bottle-color,rgba(223,235,241,.42));filter:brightness(1.06)}
.oge23-bottle-colour{display:flex;align-items:center;justify-content:center;gap:5px;margin:-2px 0 7px;font-size:9px;color:#8c7d75}
.oge23-bottle-colour span{width:10px;height:10px;border-radius:50%;background:var(--sw);border:1px solid rgba(0,0,0,.10);box-shadow:inset 0 0 0 1px rgba(255,255,255,.45)}
.oge23-bottle-actions{display:grid;gap:6px}
.oge23-bottle-actions button{width:100%;min-height:38px;padding:7px 6px;font-size:10px}
.oge23-observations{display:grid;gap:6px;margin-top:8px}
.oge23-observation{padding:8px 9px;border:1px solid #eadfd8;border-radius:11px;background:#fff;font-size:10px;line-height:1.35}
.oge23-observation strong{display:block;font-size:11px;margin-bottom:2px}
.oge23-test-visual{display:flex;justify-content:center;margin:7px 0}
.oge23-test-visual .tube{width:64px;height:122px}
.oge23-id-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.oge23-id-card{padding:9px;border:1px solid #eadfd8;border-radius:13px;background:#fffaf7}
.oge23-id-card b{display:block;font-size:11px;margin-bottom:5px}
.oge23-id-card select{min-height:40px}
.oge23-equations{display:grid;gap:10px;margin-top:8px}
.oge23-eq-card{padding:10px;border:1px solid #e5d8d0;border-radius:14px;background:#fffaf7}
.oge23-eq-title{font-size:12px;font-weight:700;margin-bottom:7px}
.oge23-eq-card label{display:block;font-size:10px;color:#81736d;margin:7px 0 3px}
.oge23-eq-card textarea{width:100%;min-height:58px;resize:vertical;border:1px solid #ddc9bd;border-radius:10px;background:#fff;padding:8px;font:500 11px/1.35 system-ui,-apple-system,sans-serif;color:#211916}
.oge23-reference{display:none;margin-top:8px;padding:9px;border-radius:11px;background:#f5ebe4;border:1px solid #e0c8b9;font-size:10px;line-height:1.5;overflow-wrap:anywhere}
.oge23-reference.show{display:block}
.oge23-feedback{padding:9px 10px;border-radius:12px;background:#fff7f2;border:1px solid #ead4c7;font-size:11px;line-height:1.4;margin-top:8px}
.oge23-progress{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}
.oge23-nav{display:grid;grid-template-columns:1fr auto 1fr;gap:7px;align-items:center;margin:8px 0 0}
.oge23-nav button{min-height:38px}.oge23-count{text-align:center;font-size:11px;font-weight:650;color:#765f55;white-space:nowrap}
.oge23-source{font-size:9px;color:#9b8b83;margin-top:7px}
.oge23-mini-tube{position:relative;width:62px;height:120px;margin:7px auto;border:2px solid #bdc6ca;border-top:0;border-radius:0 0 18px 18px;background:linear-gradient(90deg,rgba(255,255,255,.92),rgba(235,242,246,.52),rgba(255,255,255,.92));overflow:hidden}
.oge23-mini-tube:before{content:"";position:absolute;z-index:5;left:-2px;right:-2px;top:0;height:8px;border:2px solid #bdc6ca;border-radius:50%;background:#fbfcfd}
.oge23-mini-liquid{position:absolute;left:3px;right:3px;bottom:3px;height:54%;border-radius:0 0 13px 13px;background:var(--liq,rgba(218,231,238,.42))}
.oge23-mini-ppt{display:none;position:absolute;z-index:3;left:7px;right:7px;bottom:7px;height:25px;border-radius:45%;background:var(--pc,#fff);box-shadow:0 -4px 9px rgba(0,0,0,.08)}
.oge23-mini-bubbles{display:none;position:absolute;z-index:4;inset:30% 8px 8px;background:radial-gradient(circle at 25% 80%,transparent 0 3px,#fff 3.4px 4.2px,transparent 4.5px),radial-gradient(circle at 70% 62%,transparent 0 4px,#fff 4.4px 5px,transparent 5.4px),radial-gradient(circle at 45% 38%,transparent 0 3px,#fff 3.3px 4px,transparent 4.3px);animation:ogeBubbles .9s linear infinite}
.oge23-mini-tube.ppt .oge23-mini-ppt{display:block}
.oge23-mini-tube.gas .oge23-mini-bubbles{display:block}
.oge23-mini-tube.dissolve .oge23-mini-liquid{background:rgba(237,246,250,.20)}
.oge23-task-title{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.oge23-task-title .oge-title{max-width:760px}
.oge23-live-visual{position:relative;display:flex;justify-content:center;align-items:flex-end;min-height:148px;margin:6px 0 8px}
.oge23-live-visual .tube{width:72px!important;height:134px!important;margin:0 auto}
.oge23-live-visual.has-gas .tube{box-shadow:inset 5px 0 8px rgba(255,255,255,.75),inset -5px 0 7px rgba(109,122,140,.12),0 0 0 3px rgba(111,170,197,.12),0 7px 18px rgba(53,104,128,.14)}
.oge23-live-visual.has-gas .bubbleLayer{height:94%!important;left:0!important;right:0!important;overflow:visible!important}
.oge23-live-visual.has-gas .bubble{border-width:3px!important;filter:drop-shadow(0 1px 2px rgba(54,95,120,.28))}
.oge23-live-visual.has-gas .surfaceFizz{left:4%!important;right:4%!important;height:22px!important}
.oge23-live-visual.has-gas .gasPlume{left:4%!important;right:4%!important;height:56%!important;opacity:.95!important;filter:blur(2.5px)!important}
.oge23-gas-badge{position:absolute;z-index:20;top:0;left:50%;transform:translateX(-50%);white-space:nowrap;padding:5px 8px;border-radius:999px;background:#eef8fb;border:1px solid #badce8;color:#28596b;font-size:10px;font-weight:800;box-shadow:0 4px 12px rgba(55,108,130,.10)}
.oge23-available-reagent{display:inline-flex!important;align-items:center;gap:5px}
.oge23-available-reagent i{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--rc);border:1px solid rgba(0,0,0,.10)}

.oge23-table-title{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin:2px 0 8px}
.oge23-table-title b{font-size:13px}.oge23-table-title span{font-size:10px;color:#8a7a72}
.oge23-exp-table{overflow:hidden;border:1px solid #dfcfc5;border-radius:15px;background:#fff;margin-top:8px}
.oge23-exp-row{display:grid;grid-template-columns:minmax(120px,.9fr) minmax(120px,1fr) minmax(120px,1fr);min-height:58px;border-top:1px solid #eadfd8}
.oge23-exp-row:first-child{border-top:0}
.oge23-exp-row.head{min-height:48px;background:#f7eee8;font-size:10px;font-weight:750;color:#564943;text-transform:uppercase;letter-spacing:.02em}
.oge23-exp-cell{display:flex;align-items:center;justify-content:center;min-width:0;padding:8px;border-left:1px solid #eadfd8;text-align:center}
.oge23-exp-cell:first-child{border-left:0;justify-content:flex-start;text-align:left}
.oge23-exp-reagent b{display:block;font-size:13px;margin-bottom:2px}.oge23-exp-reagent span{display:block;font-size:9px;line-height:1.2;color:#8e7e76}
.oge23-exp-row.unused{background:#fbf8f6;color:#9b8d86}.oge23-exp-row.unused .oge23-exp-reagent{opacity:.55}
.oge23-exp-btn{width:100%;min-height:38px;padding:7px 6px!important;border-radius:10px!important;font-size:10px!important;font-weight:650!important}
.oge23-exp-result{width:100%;padding:7px 6px;border-radius:10px;background:#f4eee9;border:1px solid #e6d8cf;font-size:10px;line-height:1.25;color:#594d47}
.oge23-exp-result.positive{background:#f2f8f3;border-color:#bfd8c5;color:#355743}
.oge23-exp-result.none{background:#f6f4f2;color:#83766f}
.oge23-exp-result.hidden{background:#fff8ef;border-color:#ead4b8;color:#735d43}
.oge23-exp-result small{display:block;margin-top:3px;font-size:8px;color:#95867f}
.oge23-reset-row{display:flex;justify-content:flex-end;margin-top:8px}.oge23-reset-row button{min-height:38px}
.oge23-exp-row.task-row{min-height:82px}
.oge23-exp-select{width:100%;min-height:46px;border:1px solid #d9c6ba;border-radius:11px;background:#fff;padding:8px 9px;font-size:12px;font-weight:650;color:#332925}
.oge23-exp-select:focus{outline:2px solid rgba(200,111,74,.18);border-color:#c86f4a}
.oge23-cell-empty{width:100%;padding:9px 6px;border-radius:10px;background:#faf7f5;border:1px dashed #e1d5ce;color:#9a8c85;font-size:10px;line-height:1.25}
.oge23-head-main{display:block;font-size:11px;font-weight:800}
.oge23-head-sub{display:block;margin-top:3px;font-size:9px;font-weight:600;text-transform:none;letter-spacing:0;color:#94847c}
.oge23-conclusion{background:#fff8f2;border-top:2px solid #e7cbbd!important}
.oge23-conclusion .oge23-exp-cell:first-child{font-weight:800;color:#8d493e}
.oge23-conclusion-select{width:100%;min-height:43px;border:1px solid #d9c6ba;border-radius:10px;background:#fff;padding:7px 8px;font-size:11px;font-weight:700}
.oge23-table-check{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}
.oge23-table-check button{min-height:44px}
.oge23-available{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 2px}
.oge23-available span{padding:5px 8px;border:1px solid #e4d4ca;border-radius:999px;background:#fffaf7;font-size:10px;font-weight:650;color:#6b5950}
.oge23-table-feedback{margin-top:8px}
@media(max-width:620px){
 .oge23-condition{font-size:14px;line-height:1.5;padding:13px}
 .oge23-step h3{font-size:16px}
 .oge23-step-note{font-size:12px}
 .oge23-exp-row.task-row{min-height:76px}
 .oge23-exp-select,.oge23-conclusion-select{font-size:10px;padding:6px 4px}
 .oge23-head-main{font-size:10px}.oge23-head-sub{font-size:8px}
 .oge23-table-check{grid-template-columns:1fr}
}

@media(max-width:620px){
 .oge23-table-title{align-items:flex-start;flex-direction:column;gap:2px}
 .oge23-exp-row{grid-template-columns:30% 35% 35%;min-height:64px}
 .oge23-exp-row.head{min-height:44px}
 .oge23-exp-cell{padding:6px 4px}
 .oge23-exp-reagent b{font-size:11px}.oge23-exp-reagent span{font-size:8px}
 .oge23-exp-btn{min-height:36px!important;padding:6px 3px!important;font-size:9px!important}
 .oge23-exp-result{padding:6px 3px;font-size:8.5px;line-height:1.2}
 .oge23-exp-result small{font-size:7.5px}
}

.oge23-chip{padding:5px 8px;border-radius:999px;background:#f2e3da;border:1px solid #e5cec1;font-size:9px;color:#6c554b}
@media(max-width:520px){
 .oge-switch{display:flex!important;overflow-x:auto;grid-template-columns:none!important;gap:7px;scrollbar-width:none}
 .oge-switch::-webkit-scrollbar{display:none}
 .oge-switch button{flex:0 0 auto;white-space:nowrap}
 .oge23-reagents{grid-template-columns:repeat(3,minmax(0,1fr))}
 .oge23-reagent{min-height:66px;padding:8px 5px}
 .oge23-lab{grid-template-columns:1fr 1fr;gap:7px}
 .oge23-bottle{padding:8px 6px}
 .oge23-glass{width:62px;height:96px}
 .oge23-id-grid{grid-template-columns:1fr 1fr}
 .oge23-equations{grid-template-columns:1fr}
}
.oge12-counter{font-size:11px;color:#81736d;background:#fff7f2;border:1px solid #ead4c7;border-radius:999px;padding:6px 9px}
.oge12-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.oge12-match{display:grid;gap:8px;margin-top:12px}
.oge12-row{display:grid;grid-template-columns:minmax(0,1fr) 78px;gap:8px;align-items:center;padding:9px 10px;border:1px solid #ead9cf;border-radius:13px;background:#fffaf7}
.oge12-row.good{background:#f3faf5;border-color:#a9d2b5}.oge12-row.bad{background:#fff4f3;border-color:#dfaaaa}
.oge12-row .pair{font-size:12px;line-height:1.3;font-weight:650}.oge12-row .letter{color:var(--rose-deep);font-weight:750;margin-right:4px}
.oge12-row select{min-height:40px;border:1px solid #dfc8bb;border-radius:10px;background:#fff;padding:6px 7px;font-weight:650}
.oge12-options{display:grid;gap:6px;margin-top:10px}
.oge12-option{display:grid;grid-template-columns:26px minmax(0,1fr);gap:7px;align-items:start;padding:8px 9px;border:1px solid #eadfd8;border-radius:11px;background:#fff;font-size:11px;line-height:1.35}
.oge12-option b{display:grid;place-items:center;width:22px;height:22px;border-radius:7px;background:#f3e2d8;color:#8f483e}
.oge12-actions{display:grid;grid-template-columns:1fr 1.25fr;gap:8px;margin-top:11px}.oge12-actions button{width:100%;min-height:43px}
.oge12-lab{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:13px}
.oge12-tube-card{min-width:0;padding:8px 5px;border:1px solid #eadfd8;border-radius:15px;background:#fff;text-align:center}
.oge12-tube-letter{font-size:12px;font-weight:750;color:var(--rose-deep);margin-bottom:5px}
.oge12-tube{position:relative;width:66px;height:122px;margin:0 auto 7px;border:2px solid #bfc5c9;border-top:0;border-radius:0 0 20px 20px;background:linear-gradient(90deg,rgba(255,255,255,.9),rgba(239,244,247,.55),rgba(255,255,255,.9));overflow:hidden}
.oge12-tube:before{content:"";position:absolute;z-index:6;top:0;left:-2px;right:-2px;height:9px;border:2px solid #bfc5c9;border-radius:50%;background:rgba(250,252,253,.9)}
.oge12-liquid{position:absolute;left:3px;right:3px;bottom:3px;height:52%;border-radius:0 0 15px 15px;background:rgba(215,230,238,.32)}
.oge12-ppt{display:none;position:absolute;z-index:3;left:7px;right:7px;bottom:7px;height:24px;border-radius:45%;background:var(--ppt,#fff);box-shadow:0 -4px 10px rgba(0,0,0,.06)}
.oge12-bubbles{display:none;position:absolute;z-index:4;inset:27% 8px 8px;background:radial-gradient(circle at 25% 80%,transparent 0 3px,#fff 3.3px 4.2px,transparent 4.5px),radial-gradient(circle at 70% 65%,transparent 0 4px,#fff 4.3px 5.1px,transparent 5.4px),radial-gradient(circle at 45% 40%,transparent 0 3px,#fff 3.3px 4px,transparent 4.3px);animation:ogeBubbles .9s linear infinite}
@keyframes ogeBubbles{50%{transform:translateY(-7px)}}
.oge12-tube.is-gas .oge12-bubbles{display:block}
.oge12-tube.is-ppt .oge12-ppt{display:block}
.oge12-tube.is-color .oge12-liquid{background:var(--liq,#e9d59c)}
.oge12-tube.is-dissolve .oge12-liquid{background:rgba(243,247,249,.28)}
.oge12-sign{font-size:10px;line-height:1.25;min-height:25px;color:#665b55}
.oge12-reactants{font-size:9px;line-height:1.2;color:#958781;margin-top:4px;overflow-wrap:anywhere}
.oge12-feedback{margin-top:10px;padding:9px 10px;border-radius:12px;background:#fff7f2;border:1px solid #ead4c7;font-size:11px;line-height:1.4}

.ege-switch{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:10px 0 12px}
.ege-switch button{padding:11px 8px;font-size:11px}.ege-switch button.on{background:var(--pink);color:#fff;border-color:var(--pink)}
.ege-match-grid{display:grid;gap:9px;margin-top:12px}.ege-match-row{display:grid;grid-template-columns:minmax(0,1fr) 92px;gap:8px;align-items:center;background:#fff7fb;border:1px solid #f1c8dc;border-radius:14px;padding:10px}
.ege-match-row b{font-size:13px}.ege-match-row select{width:100%;min-height:42px;border-radius:11px;border:1px solid #e7c6d6;background:#fff;padding:0 8px;font-weight:900}
.ege-choice-list{display:grid;gap:7px;margin-top:10px}.ege-choice{background:#fff;border:1px solid #eadfe4;border-radius:13px;padding:9px 10px;font-size:12px}
.ege-explain{margin-top:10px;display:grid;gap:8px}.ege-mini{display:grid;grid-template-columns:74px minmax(0,1fr);gap:10px;align-items:center;background:#fff;border:1px solid #eadfe4;border-radius:14px;padding:9px}
.ege-mini .tube{height:112px;width:58px;margin:auto}.ege-mini-text{font-size:11px;line-height:1.4}.ege-mini-text b{font-size:12px}

.unknown{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}.unknown button.on{background:var(--pink);color:#fff}
select{width:100%;padding:8px;border:1px solid #efc5da;border-radius:10px;background:#fff}.guess p{display:grid;grid-template-columns:28px 1fr;align-items:center;gap:6px}
h1{margin:5px 0 6px}h2{margin:4px 0 9px}p{line-height:1.35}
.task6-progress{font-size:11px;color:#81797d;margin-bottom:8px}
.task6-text{font-size:14px;line-height:1.45;font-weight:750;background:#fff8fb;border:1px solid #f1c8dc;border-radius:15px;padding:12px}
.task6-option-list{display:grid;grid-template-columns:1fr;gap:6px;margin-top:10px}
.task6-option{padding:8px 10px;border:1px solid #eadde4;border-radius:12px;background:#fff;font-size:12px}
.task6-selects{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.task6-select-card{border:1px solid #efc5da;border-radius:14px;padding:9px;background:#fff}
.task6-select-card b{display:block;margin-bottom:5px}
.task6-select-card select{width:100%;min-height:42px;border:1px solid #e7d7df;border-radius:10px;background:#fff;padding:8px;font-size:13px}
.task6-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
.task6-actions button{width:100%}
.task6-demo{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.task6-demo-card{min-width:0;background:#fff;border:1px solid #eadfe4;border-radius:16px;padding:10px}
.task6-demo-title{font-size:12px;font-weight:900;margin-bottom:7px}
.task6-demo .tube{width:86px;height:150px;margin:0 auto 6px}
.task6-demo .reaction-card{margin-top:8px}
.task6-answer{margin-top:10px}
.task6-why{margin-top:8px;padding:10px;border-radius:13px;background:#fff7fb;border:1px solid #f1c8dc;line-height:1.4}
.task6-source-note{margin-top:8px;padding:10px;border-radius:13px;background:#fff7df;border:1px solid #e8c977;color:#5d4a1c;font-size:12px;line-height:1.4}
.task6-exp-hint{font-size:11px;color:#81797d;margin-top:8px}
@media(max-width:820px){
 .app{padding:10px 10px 90px}
 .tabs{display:flex;overflow-x:auto;gap:7px;margin:10px -2px 12px;padding:0 2px 3px;scrollbar-width:none}.tabs::-webkit-scrollbar{display:none}.tabs button{flex:0 0 auto;padding:9px 12px;font-size:11px}
 .lab-shell{grid-template-columns:1fr;gap:9px}
 .lab-bench{order:1;min-height:500px;padding:12px;border-radius:19px}
 .lab-controls{order:2;padding:11px;border-radius:18px}
 .lab-side{order:3;padding:11px;border-radius:18px}
 .bench-head{align-items:flex-start}.bench-hint{max-width:220px}
 .mobile-tube-picker{display:flex}
 .rack-wrap{left:0;right:0;bottom:70px}
 .rack-board{left:20%;right:20%;top:95px}
 .rack-board:before{left:8%}.rack-board:after{right:8%}
 .rack{display:block;padding:0}
 .tube-slot{display:none}
 .tube-slot.active-slot{display:block;width:118px;margin:0 auto}
 .tube-slot.active-slot .tube{height:220px}
 .tube-slot.active-slot .tubeSmall{font-size:10px;min-height:22px}
 .tube-slot.active-slot .tubeLabel{display:none}
 .tube-callout{width:min(330px,90vw);bottom:calc(100% + 16px)}
 .tube-callout.edge-left,.tube-callout.edge-right{left:50%;right:auto;transform:translateX(-50%)}
 .tube-callout.edge-left:after,.tube-callout.edge-right:after{left:50%}
 .reaction-card{padding:10px;border-radius:15px}.reaction-sign{font-size:13px;margin-bottom:6px}.reaction-equation{font-size:12px;padding:8px}.reaction-status{font-size:10px;padding:5px 8px}
 .control-stack{display:grid!important;grid-template-columns:1fr 1fr;gap:7px}
 .lab-result{min-height:0;padding:9px;font-size:12px}
 .selected-card{padding:8px;margin-bottom:8px}
 .reagent-filters{display:flex;overflow-x:auto;grid-template-columns:none;gap:6px;margin:8px -1px 10px;padding:0 1px 2px;scrollbar-width:none}.reagent-filters::-webkit-scrollbar{display:none}
 .reagent-filter{flex:0 0 auto;padding:7px 10px}
 .reagent-list{max-height:none;display:grid;grid-template-columns:1fr 1fr;gap:7px;overflow:visible}
 .reagent-group{display:contents}
 .reagent-group-title{grid-column:1/-1;margin:6px 0 0}
 .reagent-item{padding:8px;min-height:62px}
 .drop-icon{width:20px;height:28px;flex-basis:20px}.drop-icon:before{width:11px;height:16px;left:4px}
 .rformula{font-size:12px}.rcat{font-size:9px}
}
@media(max-width:520px){
 .lab-bench{min-height:480px}
 .tube-slot.active-slot{width:110px}
 .tube-slot.active-slot .tube{height:210px}
 .reagent-list{grid-template-columns:1fr 1fr}
 .oge-options{grid-template-columns:1fr}.oge-demo{gap:12px}.oge-demo-two{width:96px}.oge-demo .tube{height:170px}
 .ege-switch{grid-template-columns:1fr}.ege-match-row{grid-template-columns:1fr 82px}.ege-mini{grid-template-columns:64px minmax(0,1fr)}
 .task6-selects,.task6-actions,.task6-demo{grid-template-columns:1fr}
 .logo{font-size:11px;width:auto;height:auto;padding:7px 9px;border-radius:999px}
}

/* Autumn student-app visual system */
:root{
  --pink:#C86F4A;
  --soft:#F6E5DC;
  --milk:#FBF6F0;
  --ink:#211916;
  --rose-deep:#A7463F;
  --terracotta:#C86F4A;
  --latte:#EAD5C2;
  --line-autumn:#E8D2C6;
  --paper-autumn:#FFFDFC;
  --muted-autumn:#81736D;
}
body{
  background:
    radial-gradient(circle at 100% 0%,rgba(200,111,74,.10),transparent 22%),
    radial-gradient(circle at 0% 55%,rgba(234,213,194,.28),transparent 28%),
    linear-gradient(180deg,#FCF8F3 0%,#F8F1E9 100%);
  color:var(--ink);
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  font-weight:400
}
.app{max-width:1240px;padding:18px 16px 34px}
.lab-topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:8px}
.lab-brand{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:650;color:var(--rose-deep);letter-spacing:.02em}
.lab-brand:before{content:"🍂";font-size:15px}
.lab-nav{display:flex;gap:8px;flex-wrap:wrap}
.lab-nav a,.lab-nav button{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  min-height:38px;padding:8px 12px;border-radius:999px;
  border:1px solid var(--line-autumn);background:rgba(255,253,252,.86);
  color:#6E4A3E;text-decoration:none;font-size:12px;font-weight:550;
  box-shadow:0 5px 16px rgba(92,61,47,.05)
}
.lab-nav a:hover,.lab-nav button:hover{background:#FFF7F2;border-color:#DDBBA9}
.lab-title-wrap{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin:6px 2px 8px}
.lab-title-wrap h1{
  margin:0;font-family:Georgia,"Times New Roman",serif;
  font-size:32px;font-weight:500;letter-spacing:-.02em;color:#211916
}
.lab-title-note{font-size:11px;color:var(--muted-autumn);padding-bottom:5px}
.logo{
  color:var(--rose-deep);font-weight:650;letter-spacing:.02em;
  width:max-content;padding:7px 10px;border-radius:999px;
  background:rgba(255,253,252,.72);border:1px solid #E9D2C5
}
.tabs{gap:9px;margin:13px 0 15px}
.tabs button{
  background:rgba(255,253,252,.9);border:1px solid #E7CFC1;
  color:#3B302C;border-radius:16px;padding:12px 10px;
  font-size:12px;font-weight:550;box-shadow:0 5px 15px rgba(92,61,47,.035)
}
button.on,button.primary,.tabs button.on{
  background:linear-gradient(145deg,#B95C49,#C87857);
  border-color:#B95C49;color:#fff;box-shadow:0 7px 18px rgba(167,70,63,.14)
}
button{font-weight:550;border-color:#E5CFC3;color:#3B302C;background:#FFFDFC}
.lab-shell{grid-template-columns:250px minmax(0,1fr) 220px;gap:14px}
.lab-side,.lab-controls,.card{
  background:linear-gradient(155deg,rgba(255,253,252,.98),rgba(250,242,237,.94));
  border:1px solid #E8D4C8;box-shadow:0 10px 28px rgba(92,61,47,.055)
}
.lab-side,.lab-controls{border-radius:24px;padding:14px}
.lab-side h2,.lab-controls h2,.bench-head h2{font-size:16px;font-weight:600;color:#2B211D}
.mode-note,.bench-hint,.reagent-search-hint,.rcat{color:var(--muted-autumn);font-weight:400}
.reagent-search input{
  border-color:#E4CEC2;background:#FFFDFC;color:#2B211D;
  font-weight:500;box-shadow:none
}
.reagent-search input:focus{border-color:#C77A5B;box-shadow:0 0 0 2px rgba(200,111,74,.10)}
.reagent-search button{background:#FFFDFC;border-color:#E4CEC2}
.reagent-filter{
  border-color:#E5CEC2;background:#FFF9F5;color:#5C4941;
  font-size:11px;font-weight:550
}
.reagent-filter.on{background:#B95C49;color:#fff;border-color:#B95C49}
.reagent-group-title{
  font-size:11px;font-weight:600;color:#5C443A;background:#F4E3D9;
  border:1px solid #E8D2C6
}
.reagent-item{
  border-color:#EBDED6;background:rgba(255,253,252,.94);border-radius:15px
}
.reagent-item:hover,.reagent-item:active{background:#FFF5EF;border-color:#DDBAA8}
.rformula{font-weight:600}
.lab-bench{
  background:
    linear-gradient(180deg,#FFFDFC 0 68%,#F4ECE6 68% 73%,#D9BEA8 73% 100%);
  border-color:#E7D5CB;border-radius:25px;
  box-shadow:0 12px 32px rgba(92,61,47,.06)
}
.bench-head .logo{font-size:10px;background:#FFF8F3}
.selected-card,.lab-result{
  background:rgba(255,249,245,.9);border-color:#E4CFC3
}
.selected-card b{font-weight:600}.selected-card span{color:var(--muted-autumn)}
.lab-controls button{border-radius:15px;background:#FFFDFC;border-color:#E4CEC2}
.lab-controls button:hover{background:#FFF5EF}
.reaction-card{
  border-color:#C66E54;background:linear-gradient(145deg,#FFFDFC,#F5DED2);
  box-shadow:0 10px 24px rgba(166,81,59,.13)
}
.reaction-status{background:#B95C49;font-weight:600}
.reaction-sign{font-weight:600;color:#211916}
.reaction-equation{font-weight:550;border-color:rgba(184,92,73,.22)}
.tube-callout .reaction-card{box-shadow:0 14px 34px rgba(166,81,59,.16)}
.tube-callout:after{background:#F5DED2;border-right-color:#C66E54;border-bottom-color:#C66E54}
.mobile-tube-picker button.on{background:#B95C49;border-color:#B95C49}
.tube.on{border-color:#C66E54;box-shadow:inset 5px 0 8px rgba(255,255,255,.75),inset -5px 0 7px rgba(109,122,140,.12),0 0 0 2px rgba(198,110,84,.12),0 5px 12px rgba(54,42,51,.10)}
.task6-text,.task6-select-card,.task6-demo-card,.oge-task,.ege-task{
  border-color:#E7D2C6;background:#FFFDFC
}
.task6-option{border-color:#E9DAD2;background:#FFFDFC}
.task6-select-card select{border-color:#E7D4CA}
.task6-source-note{background:#FFF4DF;border-color:#E7C87A}
@media(max-width:820px){
  .lab-topbar{align-items:flex-start}
  .lab-title-wrap{align-items:flex-start}
  .lab-title-note{display:none}
  .lab-title-wrap h1{font-size:28px}
  .lab-nav{justify-content:flex-end}
}
@media(max-width:520px){
  .lab-topbar{gap:8px}
  .lab-nav a,.lab-nav button{padding:7px 9px;font-size:11px}
  .lab-title-wrap h1{font-size:26px}
}

/* Final mobile layout — must stay after all theme overrides */
@media(max-width:820px){
  html,body{max-width:100%;overflow-x:hidden}
  body{font-size:14px}
  .app{width:100%;max-width:100%;padding:10px 10px 30px}

  .lab-topbar{display:grid;grid-template-columns:1fr auto;align-items:center;gap:8px;margin:2px 0 6px}
  .lab-brand{font-size:11px;white-space:nowrap}
  .lab-nav{display:flex;gap:6px;justify-content:flex-end;flex-wrap:nowrap}
  .lab-nav a,.lab-nav button{min-height:34px;padding:7px 9px;font-size:10px;white-space:nowrap;box-shadow:none}

  .lab-title-wrap{display:flex;align-items:center;justify-content:space-between;margin:4px 1px 8px;gap:8px}
  .lab-title-wrap h1{font-size:27px;line-height:1.05}
  .lab-title-note{display:none}
  .lab-title-wrap>.logo{display:none}

  .tabs{
    display:flex!important;grid-template-columns:none!important;
    overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;
    gap:7px;margin:9px -2px 12px;padding:0 2px 4px;
    scrollbar-width:none
  }
  .tabs::-webkit-scrollbar{display:none}
  .tabs button{
    flex:0 0 auto;min-height:42px;padding:9px 14px;
    border-radius:15px;font-size:11px;white-space:nowrap
  }

  .lab-shell{display:grid!important;grid-template-columns:minmax(0,1fr)!important;gap:10px!important;width:100%}
  .lab-bench{order:1;width:100%!important;min-width:0;min-height:520px;padding:11px;border-radius:21px;overflow:hidden}
  .lab-controls{order:2;width:100%!important;min-width:0;padding:11px;border-radius:19px}
  .lab-side{order:3;width:100%!important;min-width:0;padding:11px;border-radius:19px}

  .bench-head{align-items:flex-start}
  .bench-head>.logo{display:none}
  .bench-head h2{font-size:17px;margin-bottom:5px}
  .bench-hint{font-size:11px;max-width:none}

  .mobile-tube-picker{display:flex!important;gap:7px;justify-content:center;margin:11px 0 4px}
  .mobile-tube-picker button{width:42px;height:42px;padding:0;border-radius:13px;font-size:13px}

  .rack-wrap{left:0!important;right:0!important;bottom:62px!important}
  .rack-board{left:19%!important;right:19%!important;top:98px!important;height:23px}
  .rack-board:before{left:8%;height:92px}.rack-board:after{right:8%;height:92px}
  .rack{display:block!important;padding:0!important}
  .tube-slot{display:none!important}
  .tube-slot.active-slot{display:block!important;width:116px!important;margin:0 auto!important}
  .tube-slot.active-slot .tube{height:218px!important}
  .tube-slot.active-slot .tubeSmall{font-size:10px;min-height:22px}
  .tube-slot.active-slot .tubeLabel{display:none}

  .tube-callout{
    width:min(330px,calc(100vw - 38px))!important;
    left:50%!important;right:auto!important;
    transform:translateX(-50%)!important;
    bottom:calc(100% + 14px)!important
  }
  .tube-callout.edge-left,.tube-callout.edge-right{
    left:50%!important;right:auto!important;transform:translateX(-50%)!important
  }
  .tube-callout.edge-left:after,.tube-callout.edge-right:after{left:50%!important}
  .reaction-card{padding:10px;border-radius:15px}
  .reaction-sign{font-size:13px;line-height:1.35;margin-bottom:6px}
  .reaction-equation{font-size:12px;padding:8px;max-width:100%}
  .reaction-status{font-size:10px;padding:5px 8px}
  .reaction-note{font-size:10px}

  .selected-card{padding:9px;margin-bottom:8px}
  .lab-controls .control-stack{display:grid!important;grid-template-columns:1fr 1fr;gap:7px}
  .lab-controls .control-stack button{min-height:44px;padding:9px 8px;font-size:11px;line-height:1.2}
  .lab-result{min-height:0;padding:10px;font-size:12px;margin-top:9px}

  .reagent-search{grid-template-columns:minmax(0,1fr) 40px;gap:7px}
  .reagent-search input{min-height:42px;font-size:13px}
  .reagent-search button{width:40px;height:42px}
  .reagent-filters{
    display:flex!important;grid-template-columns:none!important;overflow-x:auto;
    gap:6px;margin:8px -1px 10px;padding:0 1px 3px;scrollbar-width:none
  }
  .reagent-filters::-webkit-scrollbar{display:none}
  .reagent-filter{flex:0 0 auto;padding:8px 11px;white-space:nowrap}
  .reagent-list{
    max-height:none!important;overflow:visible!important;
    display:grid!important;grid-template-columns:1fr 1fr!important;gap:7px
  }
  .reagent-group{display:contents}
  .reagent-group-title{grid-column:1/-1;margin:8px 0 1px}
  .reagent-item{min-width:0;min-height:60px;padding:8px;border-radius:14px}
  .drop-icon{width:20px;height:28px;flex-basis:20px}
  .drop-icon:before{width:11px;height:16px;left:4px}
  .rformula{font-size:12px}.rcat{font-size:9px}

  .card{border-radius:19px;padding:11px;margin-top:8px}
  .oge-switch,.ege-switch{display:flex!important;overflow-x:auto;grid-template-columns:none!important;gap:7px;scrollbar-width:none}
  .oge-switch::-webkit-scrollbar,.ege-switch::-webkit-scrollbar{display:none}
  .oge-switch button,.ege-switch button{flex:0 0 auto;white-space:nowrap}
  .task6-selects,.task6-actions,.task6-demo{grid-template-columns:1fr!important}
  .oge-options{grid-template-columns:1fr!important}
}

@media(max-width:430px){
  .app{padding-left:8px;padding-right:8px}
  .lab-title-wrap h1{font-size:25px}
  .lab-nav a,.lab-nav button{padding:6px 8px;font-size:9.5px}
  .lab-bench{min-height:500px}
  .tube-slot.active-slot{width:108px!important}
  .tube-slot.active-slot .tube{height:205px!important}
  .rack-board{left:17%!important;right:17%!important;top:92px!important}
  .reagent-list{grid-template-columns:1fr 1fr!important}
}

/* Mobile comparison mode: show all four test tubes at once */
@media(max-width:820px){
  .mobile-tube-picker{display:none!important}

  .lab-bench{
    min-height:430px!important;
    padding:11px 9px!important;
  }

  .rack-wrap{
    left:3px!important;
    right:3px!important;
    bottom:54px!important;
  }

  .rack-board{
    left:2%!important;
    right:2%!important;
    top:74px!important;
    height:20px!important;
  }
  .rack-board:before,.rack-board:after{
    top:16px!important;
    width:11px!important;
    height:74px!important;
  }
  .rack-board:before{left:2.5%!important}
  .rack-board:after{right:2.5%!important}

  .rack{
    display:grid!important;
    grid-template-columns:repeat(4,minmax(0,1fr))!important;
    gap:7px!important;
    align-items:end!important;
    padding:0 5px!important;
  }

  .tube-slot,
  .tube-slot.active-slot{
    display:block!important;
    width:auto!important;
    min-width:0!important;
    margin:0!important;
  }

  .tube-slot .tube,
  .tube-slot.active-slot .tube{
    width:100%!important;
    height:168px!important;
    border-radius:0 0 20px 20px!important;
  }

  .tube-slot .tube:before{
    height:9px!important;
  }

  .tube-slot .tubeLabel,
  .tube-slot.active-slot .tubeLabel{
    display:block!important;
    margin-top:6px!important;
    font-size:12px!important;
    font-weight:600!important;
    text-align:center!important;
  }

  .tube-slot .tubeSmall,
  .tube-slot.active-slot .tubeSmall{
    display:block!important;
    min-height:24px!important;
    margin-top:2px!important;
    padding:0 1px!important;
    font-size:8.5px!important;
    line-height:1.15!important;
    text-align:center!important;
    overflow-wrap:anywhere!important;
  }

  .tube.on{
    box-shadow:
      inset 4px 0 7px rgba(255,255,255,.75),
      inset -4px 0 6px rgba(109,122,140,.12),
      0 0 0 2px rgba(198,110,84,.16),
      0 5px 12px rgba(54,42,51,.10)!important;
  }

  .pptLayer,.bubbleLayer,.boilLayer{
    left:2px!important;
    right:2px!important;
  }

  .tube-callout{
    width:min(330px,calc(100vw - 34px))!important;
    bottom:calc(100% + 12px)!important;
  }
}

@media(max-width:430px){
  .lab-bench{min-height:410px!important}
  .rack-wrap{left:0!important;right:0!important;bottom:48px!important}
  .rack{gap:5px!important;padding:0 3px!important}
  .tube-slot .tube,
  .tube-slot.active-slot .tube{
    height:154px!important;
    border-radius:0 0 18px 18px!important;
  }
  .rack-board{top:68px!important}
  .tube-slot .tubeSmall,
  .tube-slot.active-slot .tubeSmall{
    font-size:8px!important;
  }
}

/* Task 6 full trainer */
.task6-shell{display:grid;gap:11px}
.task6-toolbar{
  display:flex;align-items:center;justify-content:space-between;gap:9px;flex-wrap:wrap;
  padding:10px 11px;border:1px solid #E8D4C8;border-radius:17px;
  background:linear-gradient(145deg,#FFFDFC,#F8ECE5)
}
.task6-modes{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
.task6-modes::-webkit-scrollbar{display:none}
.task6-mode{
  flex:0 0 auto;border:1px solid #E3CABC;background:#FFFDFC;color:#62483E;
  border-radius:999px;padding:7px 10px;font-size:10px;font-weight:550
}
.task6-mode.on{background:#B95C49;color:#fff;border-color:#B95C49}
.task6-summary{font-size:10px;color:#796A64;line-height:1.35}
.task6-weak{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}
.task6-weak span{font-size:9px;padding:5px 7px;border-radius:999px;background:#F4E4DB;color:#795246}
.task6-start{
  padding:17px;border:1px solid #E6D2C6;border-radius:20px;
  background:linear-gradient(145deg,#FFFDFC,#F7E8E0)
}
.task6-start h3{margin:0 0 6px;font-family:Georgia,"Times New Roman",serif;font-size:21px;font-weight:500}
.task6-start p{margin:0;color:#7C6F69;font-size:12px;line-height:1.5}
.task6-start-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:13px}
.task6-start-grid button{min-height:48px;font-weight:550}
.task6-counter{display:flex;justify-content:space-between;gap:9px;align-items:center;color:#82756E;font-size:10px}
.task6-question{
  padding:15px;border:1px solid #E6D3C8;border-radius:20px;
  background:#FFFDFC;line-height:1.53;font-size:14px;font-weight:450
}
.task6-answer-slots{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.task6-slot{
  min-height:59px;text-align:left;border:1px solid #E4CEC1!important;
  background:#FFFDFC!important;border-radius:17px!important;padding:10px 11px!important;
  color:#2D231F!important
}
.task6-slot.on{border-color:#B95C49!important;box-shadow:0 0 0 2px rgba(185,92,73,.09)}
.task6-slot-letter{
  display:inline-grid;place-items:center;width:24px;height:24px;border-radius:9px;
  background:#F2DED3;color:#8F4639;font-size:11px;font-weight:650;margin-right:7px
}
.task6-slot.on .task6-slot-letter{background:#B95C49;color:#fff}
.task6-slot-value{font-size:12px;font-weight:600}
.task6-slot-hint{display:block;margin:5px 0 0 32px;font-size:9px;color:#8A7C75;font-weight:400}
.task6-option-list{display:grid;grid-template-columns:1fr;gap:7px;margin-top:0}
.task6-option-card{
  position:relative;display:grid!important;grid-template-columns:30px minmax(0,1fr) auto;
  align-items:center;gap:9px;width:100%;text-align:left!important;
  min-height:55px;padding:9px 10px!important;border-radius:16px!important;
  border:1px solid #E9DAD2!important;background:#FFFDFC!important;color:#2A211D!important
}
.task6-option-card.selected-x,.task6-option-card.selected-y{border-color:#C98668!important;background:#FFF7F2!important}
.task6-option-card.selected-x.selected-y{border-color:#A7463F!important}
.task6-option-no{display:grid;place-items:center;width:27px;height:27px;border-radius:9px;background:#F4E6DE;font-size:10px;font-weight:600;color:#765044}
.task6-option-formula{font-size:14px;font-weight:600;line-height:1.2}
.task6-option-name{font-size:9px;color:#897B74;margin-top:3px;line-height:1.25}
.task6-option-tags{display:flex;gap:4px;align-items:center}
.task6-option-tag{display:grid;place-items:center;min-width:23px;height:23px;padding:0 6px;border-radius:8px;background:#B95C49;color:#fff;font-size:9px;font-weight:650}
.task6-exp-hint{font-size:10px;color:#81736D;line-height:1.4}
.task6-actions{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.task6-actions button{min-height:44px}
.task6-demo{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}
.task6-demo-card{min-width:0;background:#FFFDFC;border:1px solid #E6D4C9;border-radius:18px;padding:10px}
.task6-demo-title{font-size:10px;font-weight:600;margin-bottom:7px;line-height:1.3}
.task6-demo .tube{width:74px;height:145px;margin:0 auto 7px}
.task6-observation{
  margin-top:8px;padding:9px 10px;border-radius:14px;
  background:linear-gradient(145deg,#FFF9F5,#F6E6DD);
  border:1px solid #E8CFC1
}
.task6-observation b{display:block;font-size:10px;color:#8F4639;margin-bottom:4px}
.task6-observation span{font-size:12px;line-height:1.35;font-weight:500}
.task6-precheck-note{font-size:9px;color:#8B7E77;margin-top:5px}
.task6-check{width:100%;min-height:48px;font-size:13px}
.task6-feedback{display:grid;gap:8px}
.task6-result{
  padding:12px;border-radius:16px;background:#FFFDFC;border:1px solid #E5D2C7;
  font-size:12px;line-height:1.45
}
.task6-result.good{background:#F1F7F2;border-color:#CFE1D3;color:#315E43}
.task6-result.bad{background:#FFF3F0;border-color:#E9C9C0;color:#7D4036}
.task6-why{margin-top:0}
.task6-done{text-align:center;padding:20px 14px;border:1px solid #E5D0C4;border-radius:22px;background:linear-gradient(145deg,#FFFDFC,#F5E2D8)}
.task6-done-icon{font-size:34px;margin-bottom:7px}
.task6-done h3{font-family:Georgia,"Times New Roman",serif;font-size:22px;font-weight:500;margin:0 0 6px}
.task6-done p{font-size:12px;color:#7B6D66;line-height:1.5;margin:0}
@media(max-width:520px){
  .task6-toolbar{align-items:flex-start}
  .task6-modes{width:100%}
  .task6-summary{width:100%}
  .task6-start-grid{grid-template-columns:1fr 1fr}
  .task6-question{padding:13px;font-size:13px}
  .task6-option-card{grid-template-columns:28px minmax(0,1fr) auto}
  .task6-option-formula{font-size:13px}
  .task6-demo{grid-template-columns:1fr 1fr!important}
  .task6-demo .tube{width:68px;height:135px}
}

/* Keep reaction result card fully inside the phone viewport */
@media(max-width:820px){
  .lab-bench{overflow:visible!important}
  .tube-callout,
  .tube-callout.edge-left,
  .tube-callout.edge-right{
    position:fixed!important;
    z-index:999!important;
    left:10px!important;
    right:10px!important;
    width:auto!important;
    max-width:none!important;
    transform:none!important;
    bottom:auto!important;
    max-height:calc(100dvh - 20px)!important;
    overflow:auto!important;
    overscroll-behavior:contain;
    -webkit-overflow-scrolling:touch;
  }
  .tube-callout .reaction-card{
    width:100%!important;
    max-width:100%!important;
    box-sizing:border-box!important;
  }
  .tube-callout .reaction-equation{
    white-space:normal!important;
    overflow-wrap:anywhere!important;
    word-break:normal!important;
  }
  .tube-callout:after,
  .tube-callout.edge-left:after,
  .tube-callout.edge-right:after{
    left:var(--callout-arrow-left,50%)!important;
  }
}
</style></head><body><div class="app">
<div class="lab-topbar">
  <div class="lab-brand">ЕГЭ БЛИЗКО</div>
  <div class="lab-nav">
    <button id="labBackHistory" type="button">← Назад</button>
    <a id="labBackCabinet" href="#">⌂ В кабинет</a>
  </div>
</div>
<div class="lab-title-wrap">
  <div><h1>🧪 Лаборатория</h1><div class="lab-title-note">Опыты, тренажёры и экзаменационная практика</div></div>
  <div class="logo">ЕГЭ БЛИЗКО</div>
</div>
<div class="tabs">
<button class="on" data-page="free">Свободный опыт</button>
<button data-page="work">Лаб. работа</button>
<button data-page="oge">ОГЭ</button>
<button data-page="ege">ЕГЭ</button>
<button data-page="exam">Экзамен</button>
<button data-page="stats">Прогресс</button>
</div>

<section id="free" class="page on">
<div class="lab-shell">
  <aside class="lab-side">
    <h2>Реактивы</h2>
    <div class="mode-note">Нажми на вещество — оно добавится в выбранную пробирку.</div>
    <div id="labCoverage" class="mode-note">Загружаю ЕГЭ-каталог…</div>
    <div class="reagent-search">
      <input id="reagentSearch" type="search" inputmode="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Например: CuSO4">
      <button id="reagentSearchClear" type="button" aria-label="Очистить поиск">✕</button>
    </div>
    <div class="reagent-search-hint">Можно вводить обычные цифры: CuSO4 найдёт CuSO₄.</div>
    <div id="reagentFilters" class="reagent-filters">
      <button class="reagent-filter on" data-cat="Все">Все</button>
      <button class="reagent-filter" data-cat="Металлы">Металлы</button>
      <button class="reagent-filter" data-cat="Неметаллы">Неметаллы</button>
      <button class="reagent-filter" data-cat="Оксиды">Оксиды</button>
      <button class="reagent-filter" data-cat="Гидроксиды">Гидроксиды</button>
      <button class="reagent-filter" data-cat="Кислоты">Кислоты</button>
      <button class="reagent-filter" data-cat="Соли">Соли</button>
      <button class="reagent-filter" data-cat="Прочее">Прочее</button>
    </div>
    <div id="reagents" class="reagent-list"></div>
  </aside>
  <main class="lab-bench">
    <div class="bench-head"><div><h2>Рабочий стол</h2><div class="bench-hint">Выбери пробирку и проведи опыт</div></div><div class="logo">ЕГЭ БЛИЗКО</div></div>
    <div id="mobileTubePicker" class="mobile-tube-picker">
      <button class="on" data-tube="0">1</button><button data-tube="1">2</button><button data-tube="2">3</button><button data-tube="3">4</button>
    </div>
    <div class="rack-wrap"><div class="rack-board"></div><div id="tubes" class="rack"></div></div>
  </main>
  <aside class="lab-controls">
    <h2>Действия</h2>
    <div class="selected-card"><b>Выбрана пробирка <span id="selectedTubeLabel">1</span></b><span>Добавь до двух реактивов; для нужных реакций можно выбрать избыток.</span></div>
    <div class="control-stack">
      <button id="excess">➕ Последний реактив в избытке</button>
      <button id="heat">🔥 Нагреть</button>
      <button id="clear">🧽 Очистить</button>
    </div>
    <div id="result" class="lab-result">Выбери пробирку и добавь реактивы.</div>
  </aside>
</div>
</section>

<section id="work" class="page"><div class="card">
<h2>Определи 5 неизвестных</h2>
<p>CuSO₄, FeCl₃, Na₂CO₃, NaCl и Na₂SO₄. Используй минимум проб.</p>
<div id="unknowns" class="unknown"></div><h3>Реактив</h3><div id="labTools" class="tools"></div>
<button id="test" class="primary">Провести пробу</button><div id="labVisual" class="labVisual"></div><div id="labLog" class="result">Пока ни одной пробы.</div>
<div id="guesses" class="guess"></div><button id="check" class="primary">Проверить</button><div id="workResult" class="result"></div>
</div></section>

<section id="oge" class="page"><div class="card">
<div class="oge-switch">
  <button id="oge12Tab" class="on">№12 · Признак реакции</button>
  <button id="oge17Tab">№17 · Различение веществ</button>
  <button id="oge23Tab">№23 · Практика</button>
</div>
<div id="ogeBox"></div>
</div></section>

<section id="ege" class="page"><div class="card">
<div class="ege-switch">
  <button id="ege6Tab" class="on">№6 · Опыты</button>
  <button id="ege24Tab">№24</button>
  <button id="egeSignsTab">Признаки</button>
  <button id="egeQualityTab">Качественные реакции</button>
</div>
<div id="egeBox"></div>
</div></section>

<section id="exam" class="page"><div class="card">
<h2 id="pair"></h2><p>Что увидишь после смешивания?</p><div id="answers" class="answers"></div>
<div id="examResult" class="result"></div><button id="next">Следующая</button>
</div></section>

<section id="stats" class="page"><div class="card"><h2>Мой прогресс</h2><div id="statsBox" class="stats"></div></div></section>
</div>
<script>
const tg=Telegram.WebApp;tg.ready();tg.expand();
const labQs=new URLSearchParams(location.search),labLaunch=labQs.get("launch")||"";
const labFrom=labQs.get("from")||"",labReturnLaunch=labQs.get("return_launch")||"";

const labBackCabinet=document.getElementById("labBackCabinet");
const labBackHistory=document.getElementById("labBackHistory");
if(labBackCabinet){
  if(labFrom==="admin"){
    labBackCabinet.textContent="⌂ В мой кабинет";
    labBackCabinet.href="/admin-app"+(labReturnLaunch?("?launch="+encodeURIComponent(labReturnLaunch)):"");
  }else{
    labBackCabinet.href="/student-app"+(labLaunch?("?launch="+encodeURIComponent(labLaunch)):"");
  }
}
if(labBackHistory){
  labBackHistory.onclick=function(){
    if(history.length>1){history.back()}
    else if(labBackCabinet){location.href=labBackCabinet.href}
  };
}
let data, reagentMap=new Map(), reactionMap=new Map(), selectedTube=0, selectedReagentCategory="Все", selectedReagentSearch="";
let tubes=[[],[],[],[]], tubeHeat=[false,false,false,false], tubeExcess=["","","",""], unknownOrder=[], unknownSelected=0, toolSelected="", attempts=0, exam=null, locked=false;
let ogeMode=12,ogeIndex12=0,ogeIndex17=0,ogeLocked=false;
let oge23Mode="learn",oge23Index=0,oge23Rows=["",""],oge23Tests=[{},{}],oge23Conclusion=["",""],oge23Identified=false;
let egeMode="6",egeTask6Index=0,egeIndex24=0,egeSignsIndex=0,egeQualityIndex=0,egeLocked=false;
let task6Session=null,task6Progress=null,task6SelectedX="",task6SelectedY="",task6Target="x",task6PendingSession=null;

function key(a,b){return [a,b].sort().join("|")}
function reagent(id){return reagentMap.get(id)}
function api(payload){return fetch("/lab-app/api",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.assign({init_data:tg.initData,launch:labLaunch},payload))}).then(r=>r.json())}
function reactionVariants(a,b){return reactionMap.get(key(a,b))||[]}
function reactionExpected(a,b,excess=""){
 const list=reactionVariants(a,b);
 if(excess){const exact=list.find(x=>x.excess===excess);if(exact)return exact}
 return list.find(x=>!x.excess)||list[0]||null;
}
function findReaction(a,b,heated,excess=""){
 const list=reactionVariants(a,b);
 const eligible=excess ? list.filter(x=>x.excess===excess) : list.filter(x=>!x.excess);
 if(heated){
   const hot=eligible.find(x=>x.heat);
   if(hot)return hot;
 }
 const cold=eligible.find(x=>!x.heat);
 if(cold)return cold;
 const fallback=eligible[0]||null;
 return fallback&&(!fallback.heat||heated)?fallback:null;
}
function reactionResultHTML(x,heated=false){
 if(!x)return '<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">Нет данных</span></div><div class="reaction-sign">Этот опыт пока не добавлен в базу.</div></div>';
 if(x.heat&&!heated)return '<div class="reaction-card"><div class="reaction-head"><span class="reaction-status">🔥 Нужен нагрев</span></div><div class="reaction-sign">Без нагревания видимого результата не показываем.</div><div class="reaction-equation">'+x.eq+'</div></div>';
 const noVisible=x.t==="n", noReaction=x.t==="z";
 const icon=x.t==="p"?"⬇️":x.t==="g"?"🫧":x.t==="c"?"🎨":x.t==="x"?"✨":noReaction?"⛔":"✓";
 const title=noReaction?"Реакция не идёт":"Реакция протекает";
 const sign=noReaction?x.sign:(noVisible?"Без видимого признака":x.sign);
 const condition=x.condition?'<div class="reaction-note">Условие: '+x.condition+'</div>':'';
 const note=noReaction?'<div class="reaction-note">Смесь остаётся без химического превращения в указанных условиях.</div>':(noVisible?'<div class="reaction-note">Реакция есть, но визуального эффекта в пробирке нет.</div>':'');
 return '<div class="reaction-card '+((noVisible||noReaction)?'no-visible':'')+'"><div class="reaction-head"><span class="reaction-status">'+icon+' '+title+'</span></div><div class="reaction-sign">'+(noReaction?'Почему: ':'Признак: ')+sign+'</div><div class="reaction-equation">'+x.eq+'</div>'+condition+note+'</div>';
}
function pptTexture(x){
 const s=(x&&x.sign||"").toLowerCase();
 if(s.includes("студенист"))return "gel";
 if(s.includes("agcl"))return "floc";
 if(s.includes("baso₄")||s.includes("baso4")||s.includes("caco₃")||s.includes("caso₃"))return "fine";
 if(s.includes("pbi₂")||s.includes("agi")||s.includes("agbr")||s.includes("bacro₄"))return "crystal";
 if(s.includes("fe(oh)₃"))return "floc";
 return "fine";
}
function precipitateHTML(x){
 if(!x||!x.ppt)return "";
 const cls=pptTexture(x),parts=[];
 for(let n=0;n<24;n++){
  const l=(5+(n*37)%88), b=(2+(n*17)%30), s=(cls==="gel"?11+(n%5)*4:cls==="floc"?7+(n%5)*3:4+(n%4)*2), r=((n*31)%90-45)+"deg";
  parts.push('<i class="particle '+cls+'" style="--l:'+l+'%;--b:'+b+'%;--s:'+s+'px;--r:'+r+';--pc:'+x.ppt+'"></i>');
 }
 return '<div class="pptLayer">'+parts.join("")+'</div>';
}
function bubblesHTML(x){
 if(!x||!x.gas)return "";
 const parts=[],fizz=[],boil=[];
 const strong=["CO₂","SO₂","H₂S","NO₂"].includes(x.gas);
 const count=strong?42:30;
 for(let n=0;n<count;n++){
   parts.push('<i class="bubble" style="--l:'+(4+(n*23)%91)+'%;--s:'+(strong?8+(n%7)*2.4:7+(n%6)*2.2)+'px;--d:'+(strong?.88+(n%5)*.12:1.12+(n%5)*.17)+'s;--delay:-'+((n%11)*.13)+'s;--drift:'+(((n%5)-2)*8)+'px"></i>');
 }
 for(let n=0;n<(strong?16:10);n++){
   fizz.push('<i style="--l:'+(3+(n*31)%92)+'%;--s:'+(4+(n%5)*2.2)+'px;--delay:-'+((n%7)*.14)+'s"></i>');
 }
 if(strong){
   for(let n=0;n<11;n++){
     boil.push('<i class="boilCell" style="--l:'+(2+(n*17)%86)+'%;--w:'+(16+(n%4)*7)+'px;--h:'+(10+(n%4)*4)+'px;--d:'+(0.55+(n%4)*.11)+'s;--delay:-'+((n%5)*.12)+'s"></i>');
   }
 }
 let gasColor='rgba(255,255,255,.55)';
 if(x.gas==="SO₂")gasColor='rgba(220,225,230,.44)';
 if(x.gas==="H₂S")gasColor='rgba(205,210,205,.36)';
 if(x.gas==="NH₃")gasColor='rgba(235,235,255,.40)';
 if(x.gas==="NO₂")gasColor='rgba(196,88,22,.90)';
 if(x.gas==="Cl₂")gasColor='rgba(190,210,92,.46)';
 const gasClass=x.gas==="NO₂"?" no2":"";
 return (strong?'<div class="boilLayer'+gasClass+'">'+boil.join("")+'</div>':'')+'<div class="bubbleLayer '+(strong?'strong':'')+gasClass+'">'+parts.join("")+'</div><div class="surfaceFizz'+gasClass+'">'+fizz.join("")+'</div><div class="gasPlume" style="--gasColor:'+gasColor+'"></div>';
}
function solidReagentHTML(v,x){
 if(!v.length||x)return "";
 const solids=v.filter(id=>String((reagent(id)||[])[3]||"").includes("тв."));
 if(!solids.length)return "";
 const id=solids[solids.length-1],r=reagent(id),parts=[];
 for(let n=0;n<18;n++){
   parts.push('<i class="solidChunk" style="--l:'+(3+(n*29)%82)+'%;--b:'+(1+(n*13)%18)+'%;--s:'+(8+(n%5)*3)+'px;--r:'+(((n*31)%80)-40)+'deg;--sc:'+r[2]+'"></i>');
 }
 return '<div class="solidBed">'+parts.join("")+'</div>';
}
function metalDepositHTML(v,x){
 if(!x||!x.ppt)return "";
 const metalId=v.find(id=>String((reagent(id)||[])[1]||"")==="Металлы");
 if(!metalId)return "";
 const m=reagent(metalId),crystals=[];
 for(let n=0;n<22;n++){
   crystals.push('<i class="metalCrystal" style="--l:'+(12+(n*31)%70)+'%;--b:'+(8+(n*17)%30)+'%;--s:'+(4+(n%5)*3)+'px;--r:'+(((n*37)%100)-50)+'deg;--depositColor:'+x.ppt+'"></i>');
 }
 return '<div class="metalReactionBed"><i class="metalPiece" style="--metalColor:'+m[2]+'"></i>'+crystals.join("")+'</div>';
}
function tubeHTML(v,i,active,heated,excess=""){
 const x=v.length===2?findReaction(v[0],v[1],heated,excess):null;
 const base=v.length?reagent(v[v.length-1])[2]:"#f8fbff";
 const sol=x?x.sol:base;
 const hasLiquid=v.some(id=>{
   const st=String((reagent(id)||[])[3]||"");
   return !st.includes("тв.")&&!st.includes("газ");
 });
 const liquidHeight=x&&x.t!=="z"?58:(hasLiquid?58:0);
 const solids=solidReagentHTML(v,x);
 const hasMetalDeposit=!!(x&&x.ppt&&v.some(id=>String((reagent(id)||[])[1]||"")==="Металлы"));
 const deposit=hasMetalDeposit?metalDepositHTML(v,x):"";
 const reactionVisual=x&&x.t!=="z"?((hasMetalDeposit?"":precipitateHTML(x))+bubblesHTML(x)+deposit+'<i class="reactionGlow"></i>'):"";
 const shimmer=(heated&&v.length)?'<i class="heatShimmer"></i>':"";
 return '<div class="tube '+(active?'on':'')+'"><i class="liq" style="height:'+liquidHeight+'%;background:'+sol+'"></i>'+solids+reactionVisual+shimmer+'</div>';
}
function renderTubes(){
 const box=document.getElementById("tubes");box.innerHTML="";
 tubes.forEach((v,i)=>{
  const wrap=document.createElement("div");wrap.className="tube-slot"+(i===selectedTube?" active-slot":"");
  const x=v.length===2?reactionExpected(v[0],v[1],tubeExcess[i]):null;
  let callout="";
  if(i===selectedTube&&v.length===2){
    const cls=i===0?" edge-left":i===3?" edge-right":"";
    callout='<div class="tube-callout'+cls+'">'+reactionResultHTML(x,tubeHeat[i])+'</div>';
  }
  const excessLabel=tubeExcess[i]?'<div class="tubeSmall">избыток: '+reagent(tubeExcess[i])[0]+'</div>':'';
  wrap.innerHTML=callout+tubeHTML(v,i,i===selectedTube,tubeHeat[i],tubeExcess[i])+'<div class="tubeLabel">'+(i+1)+'</div><div class="tubeSmall">'+(v.map(q=>reagent(q)[0]).join(" + ")||"пусто")+'</div>'+excessLabel;
  wrap.onclick=()=>{selectedTube=i;syncTubePicker();renderTubes()};box.appendChild(wrap);
 });
 positionMobileReactionCallout();
}
function positionMobileReactionCallout(){
 if(window.innerWidth>820)return;
 requestAnimationFrame(()=>{
  const callout=document.querySelector(".tube-slot.active-slot .tube-callout");
  const tube=document.querySelector(".tube-slot.active-slot .tube");
  if(!callout||!tube)return;
  const pad=10, gap=12, tr=tube.getBoundingClientRect();
  const ch=callout.getBoundingClientRect().height;
  let top=tr.top-ch-gap;
  if(top<pad) top=Math.min(tr.bottom+gap,Math.max(pad,window.innerHeight-ch-pad));
  if(top+ch>window.innerHeight-pad) top=Math.max(pad,window.innerHeight-ch-pad);
  callout.style.top=Math.round(top)+"px";
  const arrow=Math.max(18,Math.min(window.innerWidth-pad*2-18,(tr.left+tr.width/2)-pad));
  callout.style.setProperty("--callout-arrow-left",Math.round(arrow)+"px");
 });
}
window.addEventListener("resize",positionMobileReactionCallout);
window.addEventListener("scroll",positionMobileReactionCallout,{passive:true});
function syncTubePicker(){
 const lab=document.getElementById("selectedTubeLabel");if(lab)lab.textContent=String(selectedTube+1);
 const root=document.getElementById("mobileTubePicker");if(!root)return;
 root.querySelectorAll("[data-tube]").forEach(btn=>btn.classList.toggle("on",Number(btn.dataset.tube)===selectedTube));
}
function normalizeReagentSearch(value){
 const subs={"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","₅":"5","₆":"6","₇":"7","₈":"8","₉":"9"};
 return String(value||"").toLowerCase().replace(/[₀₁₂₃₄₅₆₇₈₉]/g,ch=>subs[ch]).replace(/[\s·.]/g,"");
}
function reagentMatchesSearch(id,v){
 const q=normalizeReagentSearch(selectedReagentSearch);
 if(!q)return true;
 const formula=normalizeReagentSearch(v[0]);
 const name=normalizeReagentSearch(v[4]||"");
 const rid=normalizeReagentSearch(id);
 return formula.includes(q)||name.includes(q)||rid.includes(q);
}
function renderReagents(){
 const box=document.getElementById("reagents");box.innerHTML="";
 const order=["Металлы","Неметаллы","Оксиды","Гидроксиды","Кислоты","Соли","Прочее"];
 let shown=0;
 order.forEach(cat=>{
   if(!selectedReagentSearch&&selectedReagentCategory!=="Все"&&selectedReagentCategory!==cat)return;
   const entries=Object.entries(data.reagents).filter(([id,v])=>v[1]===cat&&reagentMatchesSearch(id,v));
   if(!entries.length)return;
   shown+=entries.length;
   const group=document.createElement("div");group.className="reagent-group";
   const title=document.createElement("div");title.className="reagent-group-title";title.textContent=cat;group.appendChild(title);
   entries.forEach(([id,v])=>{
     const b=document.createElement("button");b.className="reagent-item";
     b.innerHTML='<span class="drop-icon" style="--rc:'+v[2]+'"></span><span><div class="rformula">'+v[0]+'</div><div class="rcat">'+v[1]+(v[3]?' · '+v[3]:'')+'</div></span>';
     b.onclick=()=>add(id);group.appendChild(b);
   });
   box.appendChild(group);
 });
 if(!shown){
   const empty=document.createElement("div");empty.className="reagent-empty";
   empty.textContent="Вещество не найдено. Проверь формулу или попробуй ввести её без индексов.";
   box.appendChild(empty);
 }
}
function setupMobileTubePicker(){
 const root=document.getElementById("mobileTubePicker");if(!root)return;
 root.querySelectorAll("[data-tube]").forEach(btn=>{
   btn.onclick=()=>{selectedTube=Number(btn.dataset.tube);syncTubePicker();renderTubes();};
 });
 syncTubePicker();
}
function setupReagentFilters(){
 const root=document.getElementById("reagentFilters");if(!root)return;
 root.querySelectorAll("[data-cat]").forEach(btn=>{
   btn.onclick=()=>{
     selectedReagentCategory=btn.dataset.cat;
     root.querySelectorAll("[data-cat]").forEach(x=>x.classList.toggle("on",x===btn));
     renderReagents();
   };
 });
}
function setupReagentSearch(){
 const input=document.getElementById("reagentSearch"),clear=document.getElementById("reagentSearchClear");
 if(!input||!clear)return;
 const apply=()=>{selectedReagentSearch=input.value.trim();renderReagents()};
 input.addEventListener("input",apply);
 input.addEventListener("search",apply);
 input.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();apply();input.blur()}});
 clear.onclick=()=>{input.value="";selectedReagentSearch="";renderReagents();input.focus()};
}
function add(id){
 if(tubes[selectedTube].length>=2)return;
 tubeHeat[selectedTube]=false;tubeExcess[selectedTube]="";
 tubes[selectedTube].push(id);
 if(tubes[selectedTube].length===2){
  let x=reactionExpected(tubes[selectedTube][0],tubes[selectedTube][1],"");
  document.getElementById("result").innerHTML=x?(x.heat?"Нужен нагрев 🔥":"Карточка реакции показана над пробиркой ↑"):"Этот опыт пока не добавлен в базу";
  if(x&&!x.heat)api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()});
 }
 renderTubes();
}
document.getElementById("excess").onclick=()=>{
 const v=tubes[selectedTube];
 if(v.length!==2){document.getElementById("result").textContent="Сначала добавь два реактива.";return}
 tubeExcess[selectedTube]=v[v.length-1];
 const x=reactionExpected(v[0],v[1],tubeExcess[selectedTube]);
 document.getElementById("result").innerHTML=x&&x.excess?"Показываю реакцию при избытке "+reagent(tubeExcess[selectedTube])[0]+".":"Для этой пары отдельный результат избытка пока не требуется.";
 renderTubes();
};
document.getElementById("heat").onclick=()=>{
 let v=tubes[selectedTube];tubeHeat[selectedTube]=true;
 let x=v.length===2?findReaction(v[0],v[1],true,tubeExcess[selectedTube]):null;
 if(x){document.getElementById("result").innerHTML="Карточка реакции показана над пробиркой ↑";api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()})}
 else if(v.length===2){document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🔥 Нагрев</span></div><div class="reaction-sign">При нагревании видимого изменения нет.</div></div>'}
 renderTubes();
};
document.getElementById("clear").onclick=()=>{tubes[selectedTube]=[];tubeHeat[selectedTube]=false;tubeExcess[selectedTube]="";document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🧽 Готово</span></div><div class="reaction-sign">Пробирка очищена.</div></div>';renderTubes()};

function setupLab(){
 unknownOrder=[...data.lab].sort(()=>Math.random()-.5);
 const u=document.getElementById("unknowns");u.innerHTML="";
 "ABCDE".split("").forEach((label,i)=>{const b=document.createElement("button");b.textContent=label;b.onclick=()=>{unknownSelected=i;[...u.children].forEach((q,n)=>q.classList.toggle("on",n===i))};u.appendChild(b)});u.children[0].classList.add("on");
 const tools=document.getElementById("labTools");tools.innerHTML="";
 data.tools.forEach(id=>{const b=document.createElement("button");b.textContent=reagent(id)[0];b.onclick=()=>{toolSelected=id;[...tools.children].forEach(q=>q.classList.remove("on"));b.classList.add("on")};tools.appendChild(b)});
 const guesses=document.getElementById("guesses");guesses.innerHTML="";
 "ABCDE".split("").forEach((label,i)=>{const p=document.createElement("p");p.innerHTML="<b>"+label+"</b><select id='guess"+i+"'><option></option>"+data.lab.map(id=>"<option value='"+id+"'>"+reagent(id)[0]+"</option>").join("")+"</select>";guesses.appendChild(p)});
 document.getElementById("labLog").textContent="Пока ни одной пробы.";document.getElementById("workResult").textContent="";document.getElementById("labVisual").innerHTML="";attempts=0;
}
document.getElementById("test").onclick=()=>{
 if(!toolSelected)return;
 attempts++;
 const unknown=unknownOrder[unknownSelected],x=findReaction(unknown,toolSelected,true);
 const label="ABCDE"[unknownSelected]+" + "+reagent(toolSelected)[0]+" — "+(x?x.sign:"без видимого признака");
 document.getElementById("labVisual").innerHTML=tubeHTML([unknown,toolSelected],0,false,true);
 document.getElementById("labLog").innerHTML+=("<br>"+attempts+". "+label);
};
document.getElementById("check").onclick=()=>{
 let n=0;for(let i=0;i<5;i++)if(document.getElementById("guess"+i).value===unknownOrder[i])n++;
 document.getElementById("workResult").textContent="Верно "+n+"/5";
 if(n===5)api({action:"event",type:"labwork"}).then(j=>{data.stats=j.stats;renderStats()});
};

const EGE24=[
 {kind:"signs",title:"Задание №24 · признаки реакции",pairs:[
   ["AgNO₃ + NaCl","agno3","nacl"],["CuSO₄ + NaOH","cuso4","naoh"],["FeCl₃ + NaOH","fecl3","naoh"],["Na₂CO₃ + HNO₃","na2co3","hno3"]
  ],options:["белый осадок","голубой осадок","бурый осадок","выделение бесцветного газа","видимые признаки отсутствуют"],answers:[1,2,3,4]},
 {kind:"quality",title:"Задание №24 · качественное различение",pairs:[
   ["Na₂SiO₃ и Na₂CO₃","na2sio3","na2co3"],["Na₂SO₄ и Na₂SO₃","na2so4","na2so3"],["NaCl и KI","nacl","ki"],["FeSO₄ и FeCl₃","feso4","fecl3"]
  ],options:[["hcl","HCl"],["bacl2","BaCl₂"],["agno3","AgNO₃"],["naoh","NaOH"],["h2so4","H₂SO₄"]],answers:["hcl","hcl","agno3","naoh"]}
];
const EGESIGNS=[
 ["agno3","nacl","AgNO₃ + NaCl"],["cuso4","naoh","CuSO₄ + NaOH"],["fecl3","naoh","FeCl₃ + NaOH"],["feso4","naoh","FeSO₄ + NaOH"],
 ["na2co3","hno3","Na₂CO₃ + HNO₃"],["na2so3","h2so4","Na₂SO₃ + H₂SO₄"],["na2sio3","hcl","Na₂SiO₃ + HCl"],["k2cro4","hcl","K₂CrO₄ + HCl"]
];
const EGEQUALITY=[
 {left:"na2sio3",right:"na2co3",leftName:"Na₂SiO₃",rightName:"Na₂CO₃",options:[["hcl","HCl"],["naoh","NaOH"],["agno3","AgNO₃"],["bacl2","BaCl₂"]],correct:"hcl"},
 {left:"na2so4",right:"na2so3",leftName:"Na₂SO₄",rightName:"Na₂SO₃",options:[["hcl","HCl"],["agno3","AgNO₃"],["naoh","NaOH"],["kbr","KBr"]],correct:"hcl"},
 {left:"nacl",right:"ki",leftName:"NaCl",rightName:"KI",options:[["agno3","AgNO₃"],["naoh","NaOH"],["h2so4","H₂SO₄"],["bacl2","BaCl₂"]],correct:"agno3"},
 {left:"feso4",right:"fecl3",leftName:"FeSO₄",rightName:"FeCl₃",options:[["naoh","NaOH"],["hcl","HCl"],["agno3","AgNO₃"],["na2so4","Na₂SO₄"]],correct:"naoh"}
];
function setEgeMode(mode){
 egeMode=mode;egeLocked=false;
 document.getElementById("ege6Tab").classList.toggle("on",mode==="6");
 document.getElementById("ege24Tab").classList.toggle("on",mode==="24");
 document.getElementById("egeSignsTab").classList.toggle("on",mode==="signs");
 document.getElementById("egeQualityTab").classList.toggle("on",mode==="quality");
 renderEge();
}
function renderEge(){
 const box=document.getElementById("egeBox");egeLocked=false;
 if(egeMode==="6")return renderEgeTask6(box);
 if(egeMode==="24")return renderEge24(box);
 if(egeMode==="signs")return renderEgeSigns(box);
 return renderEgeQuality(box);
}
function task6Esc(s){
 return String(s==null?"":s).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
}
function task6ChemText(s){
 const subs={"0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉"};
 let out=task6Esc(s);
 return out.replace(/([A-Za-zА-Яа-я\)\]])([0-9]+)/g,(m,a,n)=>a+n.split("").map(x=>subs[x]||x).join(""));
}
function task6TaskById(id){
 return (data.task6||[]).find(q=>String(q.id)===String(id))||null;
}
function task6ModeLabel(mode){
 return mode==="20"?"20 случайных":mode==="all"?"Все 83":mode==="errors"?"Мои ошибки":"10 случайных";
}
function task6ProgressHTML(){
 const p=task6Progress||{total:(data.task6||[]).length,answered:0,first_try_accuracy:0,error_count:0,weak_types:[]};
 const weak=(p.weak_types||[]).map(x=>'<span>'+task6Esc(x.type)+' · '+x.errors+'</span>').join("");
 return '<div class="task6-summary"><b>Прогресс:</b> '+p.answered+'/'+p.total+' решено · '+p.first_try_accuracy+'% с первой попытки · '+p.error_count+' в ошибках'+(weak?'<div class="task6-weak">'+weak+'</div>':'')+'</div>';
}
function task6Toolbar(mode){
 return '<div class="task6-toolbar"><div class="task6-modes">'+
   [["10","10 случайных"],["20","20"],["all","Все 83"],["errors","Мои ошибки"]].map(x=>
     '<button class="task6-mode '+(mode===x[0]?'on':'')+'" data-task6-mode="'+x[0]+'">'+x[1]+'</button>'
   ).join("")+'</div>'+task6ProgressHTML()+'</div>';
}
function bindTask6Modes(){
 document.querySelectorAll("[data-task6-mode]").forEach(btn=>{
   btn.onclick=()=>task6StartMode(btn.dataset.task6Mode);
 });
}
async function task6StartMode(mode){
 const box=document.getElementById("egeBox");
 if(box)box.innerHTML='<div class="task6-start"><h3>Готовлю тренировку…</h3><p>Перемешиваю задания и восстанавливаю прогресс.</p></div>';
 try{
   const j=await api({action:"task6_start",mode:mode});
   if(!j.ok)throw new Error("start");
   task6Session=j.session||{mode:mode,order:[],current_index:0,selected_x:"",selected_y:""};
   task6Progress=j.progress||task6Progress;
 }catch(_){
   const ids=(data.task6||[]).filter(q=>mode==="all"||!q.needs_review).map(q=>String(q.id));
   for(let i=ids.length-1;i>0;i--){const k=Math.floor(Math.random()*(i+1));[ids[i],ids[k]]=[ids[k],ids[i]]}
   const count=mode==="20"?20:mode==="all"?ids.length:10;
   task6Session={mode:mode,order:mode==="errors"?[]:ids.slice(0,count),current_index:0,selected_x:"",selected_y:""};
 }
 task6SelectedX="";task6SelectedY="";task6Target="x";task6PendingSession=null;egeLocked=false;
 renderEge();
}
function task6StartScreen(box){
 box.innerHTML='<div class="task6-shell">'+task6Toolbar("")+
   '<div class="task6-start"><h3>ЕГЭ №6 · экспериментальная химия</h3>'+
   '<p>Выбирай X и Y, проводи виртуальные опыты и делай вывод только по наблюдениям. Уравнения откроются после проверки ответа.</p>'+
   '<div class="task6-start-grid">'+
   '<button data-start-task6="10">10 случайных</button><button data-start-task6="20">20 случайных</button>'+
   '<button data-start-task6="all">Все 83</button><button data-start-task6="errors">Мои ошибки</button>'+
   '</div></div></div>';
 bindTask6Modes();
 document.querySelectorAll("[data-start-task6]").forEach(btn=>btn.onclick=()=>task6StartMode(btn.dataset.startTask6));
}
function task6DoneScreen(box){
 const mode=(task6Session&&task6Session.mode)||"10";
 const noErrors=mode==="errors"&&!(task6Session.order||[]).length;
 box.innerHTML='<div class="task6-shell">'+task6Toolbar(mode)+
   '<div class="task6-done"><div class="task6-done-icon">'+(noErrors?'🌿':'✨')+'</div>'+
   '<h3>'+(noErrors?'Ошибок для повтора пока нет':'Тренировка завершена')+'</h3>'+
   '<p>'+(noErrors?'Решай обычные режимы — сюда будут попадать задания, в которых была ошибка.':'Результат сохранён. Можно начать новую подборку или отдельно повторить ошибки.')+'</p>'+
   '<div class="task6-start-grid"><button data-start-task6="10">Ещё 10</button><button data-start-task6="errors">Повторить ошибки</button></div></div></div>';
 bindTask6Modes();
 document.querySelectorAll("[data-start-task6]").forEach(btn=>btn.onclick=()=>task6StartMode(btn.dataset.startTask6));
}
function task6ResolveToken(token,sx,sy){
 if(token==="$X")return sx;
 if(token==="$Y")return sy;
 return token||"";
}
function task6ResolveExperiment(exp,sx,sy){
 return {
   a:task6ResolveToken(exp.pair[0],sx,sy),
   b:task6ResolveToken(exp.pair[1],sx,sy),
   heat:!!exp.heat,
   excess:task6ResolveToken(exp.excess||"",sx,sy),
   label:exp.label||"Опыт"
 };
}
function task6NeedsSelection(exp,sx,sy){
 const raw=(exp.pair||[]).concat([exp.excess||""]);
 if(raw.includes("$X")&&!sx)return "X";
 if(raw.includes("$Y")&&!sy)return "Y";
 return "";
}
function task6SourceNote(q){
 if(!q.needs_review)return "";
 return '<div class="task6-source-note"><b>⚠️ Примечание к источнику.</b> '+task6ChemText(q.source_note||"Формулировка этого задания в исходном файле требует проверки.")+'</div>';
}
function task6OptionCard(q,o,i){
 const id=o[0],r=reagent(id),formula=r?r[0]:o[1],name=o[1]||"";
 const sx=task6SelectedX===id,sy=task6SelectedY===id;
 const tags=(sx?'<span class="task6-option-tag">X</span>':'')+(sy?'<span class="task6-option-tag">Y</span>':'');
 const duplicate=String(name).replace(/\s/g,"").toLowerCase()===String(formula).replace(/\s/g,"").toLowerCase();
 return '<button class="task6-option-card '+(sx?'selected-x ':'')+(sy?'selected-y':'')+'" data-task6-option="'+id+'">'+
   '<span class="task6-option-no">'+(i+1)+'</span><span><div class="task6-option-formula">'+task6ChemText(formula)+'</div>'+
   (duplicate?'':'<div class="task6-option-name">'+task6ChemText(name)+'</div>')+'</span><span class="task6-option-tags">'+tags+'</span></button>';
}
function task6Slot(target,label,value){
 const r=value?reagent(value):null;
 return '<button class="task6-slot '+(task6Target===target?'on':'')+'" data-task6-target="'+target+'">'+
   '<span class="task6-slot-letter">'+label+'</span><span class="task6-slot-value">'+(r?task6ChemText(r[0]):'выбери вещество')+'</span>'+
   '<span class="task6-slot-hint">'+(task6Target===target?'сейчас заполняем это поле':'нажми, чтобы выбрать сюда')+'</span></button>';
}
function saveTask6Selection(){
 api({action:"task6_save",selected_x:task6SelectedX,selected_y:task6SelectedY}).then(j=>{
   if(j&&j.ok&&j.session)task6Session=j.session;
 }).catch(()=>{});
}
function task6Assign(id){
 if(task6Target==="x"){
   task6SelectedX=id;
   if(!task6SelectedY)task6Target="y";
 }else{
   task6SelectedY=id;
   if(!task6SelectedX)task6Target="x";
 }
 egeLocked=false;task6PendingSession=null;
 saveTask6Selection();
 renderEge();
}
function renderEgeTask6(box){
 if(!task6Session||!Array.isArray(task6Session.order))return task6StartScreen(box);
 const pos=Number(task6Session.current_index||0);
 if(pos>=task6Session.order.length)return task6DoneScreen(box);
 const q=task6TaskById(task6Session.order[pos]);
 if(!q){task6Session.current_index=pos+1;return renderEgeTask6(box)}
 const opts=(q.options||[]).map((o,i)=>task6OptionCard(q,o,i)).join("");
 const expButtons=(q.experiments||[]).map((exp,i)=>'<button type="button" class="task6-exp-btn" data-exp="'+i+'">🧪 '+task6Esc(exp.label||("Опыт "+(i+1)))+'</button>').join("");
 box.innerHTML='<div class="task6-shell">'+task6Toolbar(task6Session.mode)+
   '<div class="task6-counter"><span>'+task6ModeLabel(task6Session.mode)+'</span><span>Задание '+(pos+1)+' из '+task6Session.order.length+' · стр. '+q.source_page+'</span></div>'+
   '<div class="task6-question">'+task6ChemText(q.text)+'</div>'+
   task6SourceNote(q)+
   '<div class="task6-answer-slots">'+task6Slot("x","X",task6SelectedX)+task6Slot("y","Y",task6SelectedY)+'</div>'+
   '<div class="task6-option-list">'+opts+'</div>'+
   '<div class="task6-exp-hint">Сначала выбери X и Y. До проверки опыт показывает только наблюдение — без уравнения и названия продукта.</div>'+
   '<div class="task6-actions">'+expButtons+'</div>'+
   '<div id="task6Demo" class="task6-demo"></div>'+
   '<button id="task6Check" class="primary task6-check">Проверить ответ</button>'+
   '<div id="task6Feedback" class="task6-feedback"></div>'+
   '<button id="task6Next" class="oge-next" style="display:none">Следующее задание</button>'+
 '</div>';
 bindTask6Modes();
 document.querySelectorAll("[data-task6-target]").forEach(btn=>btn.onclick=()=>{task6Target=btn.dataset.task6Target;renderEge()});
 document.querySelectorAll("[data-task6-option]").forEach(btn=>btn.onclick=()=>task6Assign(btn.dataset.task6Option));
 document.querySelectorAll(".task6-exp-btn").forEach(btn=>btn.onclick=()=>runTask6Experiment(q,Number(btn.dataset.exp)));
 document.getElementById("task6Check").onclick=()=>checkTask6(q);
 document.getElementById("task6Next").onclick=()=>{
   if(task6PendingSession)task6Session=task6PendingSession;
   else task6Session.current_index=Number(task6Session.current_index||0)+1;
   task6SelectedX="";task6SelectedY="";task6Target="x";task6PendingSession=null;egeLocked=false;renderEge();
 };
}
function task6ColorName(hex){
 const h=String(hex||"").toLowerCase();
 const colors={"#ffffff":"белый","#39bced":"голубой","#9a4a2b":"бурый","#69432e":"бурый","#151515":"чёрный","#f4d534":"жёлтый","#e6cf44":"жёлтый","#eadb9a":"кремовый","#89b98e":"светло-зелёный","#666b70":"тёмно-серый","#b96f4a":"красно-бурый"};
 return colors[h]||"";
}
function task6ObservationText(x,heated){
 if(!x)return "Для выбранной комбинации в базе пока нет наблюдения.";
 if(x.heat&&!heated)return "Без нагревания заметного изменения не наблюдается.";
 if(x.t==="z"||x.t==="n")return "Видимых изменений не наблюдается.";
 const parts=[];
 if(x.ppt)parts.push("образуется "+(task6ColorName(x.ppt)?task6ColorName(x.ppt)+" ":"")+"осадок");
 if(x.gas)parts.push(x.gas==="NO₂"?"выделяется бурый газ":"наблюдается выделение газа");
 const s=String(x.sign||"").toLowerCase();
 if(!x.ppt&&!x.gas&&s.includes("раствор"))parts.push(s.includes("осад")?"осадок растворяется":"твёрдое вещество растворяется");
 if(!x.ppt&&!x.gas&&(s.includes("окраск")||x.t==="c"))parts.push("изменяется внешний вид или окраска раствора");
 if(!parts.length)parts.push("наблюдается химическое изменение");
 return parts.join("; ")+".";
}
function task6ObservationHTML(x,heated){
 return '<div class="task6-observation"><b>👀 Наблюдение</b><span>'+task6Esc(task6ObservationText(x,heated))+'</span>'+
 '<div class="task6-precheck-note">Уравнение и продукты откроются только после проверки ответа.</div></div>';
}
function task6ExperimentCard(q,expIndex,sx,sy,reveal=false){
 const exp=q.experiments[expIndex],resolved=task6ResolveExperiment(exp,sx,sy);
 const x=findReaction(resolved.a,resolved.b,resolved.heat,resolved.excess||"");
 const aLabel=reagent(resolved.a)?reagent(resolved.a)[0]:resolved.a;
 const bLabel=reagent(resolved.b)?reagent(resolved.b)[0]:resolved.b;
 const tube=tubeHTML([resolved.a,resolved.b],0,false,resolved.heat,resolved.excess||"");
 const condition=(resolved.heat?" · нагрев":"")+(resolved.excess?" · избыток "+(reagent(resolved.excess)?reagent(resolved.excess)[0]:resolved.excess):"");
 const result=reveal
   ? (x?reactionResultHTML(x,resolved.heat):'<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">Нет данных</span></div><div class="reaction-sign">Этот вариант опыта пока не смоделирован.</div></div>')
   : task6ObservationHTML(x,resolved.heat);
 return '<div class="task6-demo-card"><div class="task6-demo-title">'+task6Esc(resolved.label)+': '+task6ChemText(aLabel)+' + '+task6ChemText(bLabel)+task6ChemText(condition)+'</div>'+tube+result+'</div>';
}
function runTask6Experiment(q,expIndex){
 const sx=task6SelectedX,sy=task6SelectedY;
 const exp=q.experiments[expIndex],need=task6NeedsSelection(exp,sx,sy);
 if(need){
   document.getElementById("task6Feedback").innerHTML='<div class="task6-result bad">Сначала выбери вещество '+need+'.</div>';
   return;
 }
 const demo=document.getElementById("task6Demo");
 const selector='[data-exp="'+expIndex+'"]';
 const old=demo.querySelector(selector);
 const wrap=document.createElement("div");wrap.dataset.exp=String(expIndex);
 wrap.innerHTML=task6ExperimentCard(q,expIndex,sx,sy,false);
 if(old)old.replaceWith(wrap);else demo.appendChild(wrap);
 api({action:"event",type:"experiment"}).then(j=>{if(j&&j.stats){data.stats=j.stats;renderStats()}}).catch(()=>{});
}
async function checkTask6(q){
 if(egeLocked)return;
 const sx=task6SelectedX,sy=task6SelectedY;
 if(!sx||!sy){
   document.getElementById("task6Feedback").innerHTML='<div class="task6-result bad">Выбери и X, и Y.</div>';
   return;
 }
 egeLocked=true;
 let answer={correct:sx===q.answer_x&&sy===q.answer_y,answer_x:q.answer_x,answer_y:q.answer_y,scored:!q.needs_review,progress:task6Progress,session:null};
 try{
   const j=await api({action:"task6_answer",task_id:q.id,answer_x:sx,answer_y:sy});
   if(j&&j.ok&&j.result){answer=j.result;if(answer.lab_stats){data.stats=answer.lab_stats;renderStats();}}
 }catch(_){}
 const correctX=q.options.find(x=>x[0]===answer.answer_x),correctY=q.options.find(x=>x[0]===answer.answer_y);
 task6Progress=answer.progress||task6Progress;
 task6PendingSession=answer.session||null;
 document.getElementById("task6Demo").innerHTML=(q.experiments||[]).map((exp,i)=>
   '<div data-exp="'+i+'">'+task6ExperimentCard(q,i,answer.answer_x,answer.answer_y,true)+'</div>'
 ).join("");
 const review=q.needs_review
   ? '<div class="task6-source-note"><b>⚠️ Это задание не влияет на статистику.</b> В исходнике есть неоднозначность формулировки.</div>'
   : '';
 const why=q.why?task6ChemText(q.why):'Сопоставь наблюдаемые признаки с обоими опытами и проверь уравнения реакций выше.';
 document.getElementById("task6Feedback").innerHTML=
   '<div class="task6-result '+(answer.correct?'good':'bad')+'">'+
   (answer.correct?'✅ Верно.':'❌ Пока нет. Правильная пара: X — '+task6ChemText(correctX?correctX[1]:answer.answer_x)+', Y — '+task6ChemText(correctY?correctY[1]:answer.answer_y)+'.')+
   '</div><div class="task6-why"><b>Разбор:</b> '+why+'</div>'+review;
 document.getElementById("task6Check").disabled=true;
 document.getElementById("task6Next").style.display="block";
}
function renderEge24(box){
 const q=EGE24[egeIndex24%EGE24.length];
 let rows='',choices='';
 if(q.kind==="signs"){
   q.pairs.forEach((p,i)=>{rows+='<div class="ege-match-row"><b>'+"АБВГ"[i]+') '+p[0]+'</b><select id="ege24sel'+i+'"><option value="">—</option>'+q.options.map((o,n)=>'<option value="'+(n+1)+'">'+(n+1)+'</option>').join("")+'</select></div>'});
   choices=q.options.map((o,i)=>'<div class="ege-choice"><b>'+(i+1)+')</b> '+o+'</div>').join("");
 }else{
   q.pairs.forEach((p,i)=>{rows+='<div class="ege-match-row"><b>'+"АБВГ"[i]+') '+p[0]+'</b><select id="ege24sel'+i+'"><option value="">—</option>'+q.options.map((o,n)=>'<option value="'+o[0]+'">'+(n+1)+'</option>').join("")+'</select></div>'});
   choices=q.options.map((o,i)=>'<div class="ege-choice"><b>'+(i+1)+')</b> '+o[1]+'</div>').join("");
 }
 box.innerHTML='<div class="oge-task"><div class="oge-kicker">ЕГЭ · №24</div><div class="oge-title">'+q.title+'</div><div class="ege-match-grid">'+rows+'</div><div class="ege-choice-list">'+choices+'</div><button id="ege24Check" class="primary" style="margin-top:12px;width:100%">Проверить</button><div id="ege24Feedback" class="ege-explain"></div><button id="ege24Next" class="oge-next" style="display:none">Следующее задание</button></div>';
 document.getElementById("ege24Check").onclick=()=>checkEge24(q);
 document.getElementById("ege24Next").onclick=()=>{egeIndex24++;renderEge()};
}
function checkEge24(q){
 if(egeLocked)return;egeLocked=true;
 let ok=true,html='';
 q.pairs.forEach((p,i)=>{
   const val=document.getElementById("ege24sel"+i).value,ans=q.answers[i];
   if(String(val)!==String(ans))ok=false;
   if(q.kind==="signs"){
     const x=reactionExpected(p[1],p[2]);
     html+='<div class="ege-mini"><div>'+tubeHTML([p[1],p[2]],0,false,true)+'</div><div class="ege-mini-text"><b>'+"АБВГ"[i]+') '+p[0]+'</b><br>'+reactionResultHTML(x,true)+'</div></div>';
   }else{
     const tool=ans,lx=reactionExpected(p[1],tool),rx=reactionExpected(p[2],tool);
     html+='<div class="ege-mini"><div>🧪</div><div class="ege-mini-text"><b>'+"АБВГ"[i]+') '+p[0]+' → '+reagent(tool)[0]+'</b><br>'+(lx?lx.sign:"без видимого признака")+' / '+(rx?rx.sign:"без видимого признака")+'</div></div>';
   }
 });
 document.getElementById("ege24Feedback").innerHTML='<div class="result">'+(ok?'✅ Всё верно.':'❌ Есть ошибки — посмотри, что реально происходит в пробирках.')+'</div>'+html;
 document.getElementById("ege24Next").style.display="block";
 api({action:"event",type:"prediction",correct:ok}).then(j=>{data.stats=j.stats;renderStats()});
}
function renderEgeSigns(box){
 const [a,b,label]=EGESIGNS[egeSignsIndex%EGESIGNS.length],x=reactionExpected(a,b);
 const options=["образование осадка","выделение газа","изменение цвета","без видимого признака"];
 const correct=x.t==="p"||x.t==="x"?0:x.t==="g"?1:x.t==="c"?2:3;
 box.innerHTML='<div class="oge-task"><div class="oge-kicker">ЕГЭ · признаки реакций</div><div class="oge-title">Что наблюдается в ходе реакции?</div><div class="oge-pair">'+label+'</div><div id="egeSignsOptions" class="oge-options"></div><div id="egeSignsDemo" class="oge-demo"></div><div id="egeSignsFeedback"></div><button id="egeSignsNext" class="oge-next" style="display:none">Следующая</button></div>';
 options.forEach((o,i)=>{const bt=document.createElement("button");bt.textContent=(i+1)+") "+o;bt.onclick=()=>{if(egeLocked)return;egeLocked=true;[...document.getElementById("egeSignsOptions").children].forEach((z,n)=>{z.disabled=true;if(n===correct)z.classList.add("correct");else if(n===i)z.classList.add("wrong")});document.getElementById("egeSignsDemo").innerHTML='<div class="oge-demo-one">'+tubeHTML([a,b],0,false,true)+'</div>';document.getElementById("egeSignsFeedback").innerHTML=(i===correct?'✅ <b>Верно.</b>':'❌ <b>Смотри на опыт.</b>')+reactionResultHTML(x,true);document.getElementById("egeSignsNext").style.display="block";api({action:"event",type:"prediction",correct:i===correct}).then(j=>{data.stats=j.stats;renderStats()})};document.getElementById("egeSignsOptions").appendChild(bt)});
 document.getElementById("egeSignsNext").onclick=()=>{egeSignsIndex++;renderEge()};
}
function renderEgeQuality(box){
 const q=EGEQUALITY[egeQualityIndex%EGEQUALITY.length];
 box.innerHTML='<div class="oge-task"><div class="oge-kicker">ЕГЭ · качественные реакции</div><div class="oge-title">Чем можно различить эти вещества?</div><div class="oge-pair">'+q.leftName+' и '+q.rightName+'</div><div id="egeQualityOptions" class="oge-options"></div><div id="egeQualityDemo" class="oge-demo"></div><div id="egeQualityFeedback"></div><button id="egeQualityNext" class="oge-next" style="display:none">Следующая</button></div>';
 q.options.forEach(([id,label],i)=>{const bt=document.createElement("button");bt.textContent=(i+1)+") "+label;bt.onclick=()=>answerEgeQuality(q,id,i);document.getElementById("egeQualityOptions").appendChild(bt)});
 document.getElementById("egeQualityNext").onclick=()=>{egeQualityIndex++;renderEge()};
}
function answerEgeQuality(q,id,chosen){
 if(egeLocked)return;egeLocked=true;
 const ci=q.options.findIndex(x=>x[0]===q.correct),ok=id===q.correct;
 [...document.getElementById("egeQualityOptions").children].forEach((z,n)=>{z.disabled=true;if(n===ci)z.classList.add("correct");else if(n===chosen)z.classList.add("wrong")});
 const lx=reactionExpected(q.left,id),rx=reactionExpected(q.right,id);
 document.getElementById("egeQualityDemo").innerHTML=ogeTube([q.left,id],true,q.leftName+' + '+reagent(id)[0])+ogeTube([q.right,id],true,q.rightName+' + '+reagent(id)[0]);
 document.getElementById("egeQualityFeedback").innerHTML='<div class="result">'+(ok?'✅ Реактив позволяет различить вещества.':'❌ Этим реактивом надёжно различить вещества нельзя.')+'</div><div style="margin-top:8px">'+(lx?reactionResultHTML(lx,true):'<div class="result">'+q.leftName+': видимого признака нет.</div>')+'</div><div style="margin-top:8px">'+(rx?reactionResultHTML(rx,true):'<div class="result">'+q.rightName+': видимого признака нет.</div>')+'</div>';
 document.getElementById("egeQualityNext").style.display="block";
 api({action:"event",type:"prediction",correct:ok}).then(j=>{data.stats=j.stats;renderStats()});
}
document.getElementById("ege6Tab").onclick=()=>setEgeMode("6");
document.getElementById("ege24Tab").onclick=()=>setEgeMode("24");
document.getElementById("egeSignsTab").onclick=()=>setEgeMode("signs");
document.getElementById("egeQualityTab").onclick=()=>setEgeMode("quality");

const OGE17=[
 {left:"na2co3",right:"na2sio3",leftName:"Na₂CO₃",rightName:"Na₂SiO₃",options:[["hcl","HCl"],["naoh","NaOH"],["agno3","AgNO₃"],["bacl2","BaCl₂"]],correct:"hcl",heat:false},
 {left:"nh4cl",right:"nacl",leftName:"NH₄Cl",rightName:"NaCl",options:[["naoh","NaOH"],["agno3","AgNO₃"],["hcl","HCl"],["bacl2","BaCl₂"]],correct:"naoh",heat:true}
];
function ogeTube(pair,heated,label){
 return '<div class="oge-demo-two">'+tubeHTML(pair,0,false,heated)+'<div class="oge-demo-label">'+label+'</div></div>';
}
function oge12Bank(){return (data&&Array.isArray(data.oge12))?data.oge12:[]}
function oge12Subscripts(s){
 const sub={"0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉"};
 return String(s||"").replace(/[0-9]/g,ch=>sub[ch]||ch);
}
function oge12Visual(sign){
 const s=String(sign||"").toLowerCase();
 let cls="",ppt="#ffffff",liq="#dbe8ee";
 if(s.includes("газ"))cls="is-gas";
 else if(s.includes("осад"))cls="is-ppt";
 else if(s.includes("растворен"))cls="is-dissolve";
 else if(s.includes("цвет")||s.includes("окраск")||s.includes("обесцвеч"))cls="is-color";
 if(s.includes("жёлт")||s.includes("желт"))ppt="#e6c83c";
 else if(s.includes("бур"))ppt="#8f4b32";
 else if(s.includes("чёр")||s.includes("чер"))ppt="#252525";
 else if(s.includes("голуб"))ppt="#55bfe8";
 else if(s.includes("зел"))ppt="#86a889";
 else if(s.includes("син"))ppt="#4f86d9";
 if(s.includes("жёлт")||s.includes("желт"))liq="#e7d26a";
 else if(s.includes("зел"))liq="#9cc5a6";
 else if(s.includes("крас"))liq="#d98e80";
 return {cls:cls,ppt:ppt,liq:liq};
}
function oge12TubeCard(letter,pair,sign,revealed){
 const v=oge12Visual(sign),cls=revealed?v.cls:"";
 const label=revealed?sign:"Проведи решение";
 return '<div class="oge12-tube-card"><div class="oge12-tube-letter">'+letter+'</div>'+
   '<div class="oge12-tube '+cls+'" style="--ppt:'+v.ppt+';--liq:'+v.liq+'"><div class="oge12-liquid"></div><div class="oge12-ppt"></div><div class="oge12-bubbles"></div></div>'+
   '<div class="oge12-sign">'+label+'</div><div class="oge12-reactants">'+oge12Subscripts(pair)+'</div></div>';
}
function renderOge(){
 ogeLocked=false;
 document.getElementById("oge12Tab").classList.toggle("on",ogeMode===12);
 document.getElementById("oge17Tab").classList.toggle("on",ogeMode===17);
 document.getElementById("oge23Tab").classList.toggle("on",ogeMode===23);
 if(ogeMode===12){
   const bank=oge12Bank(),box=document.getElementById("ogeBox");
   if(!bank.length){
     box.innerHTML='<div class="result">Банк №12 не загрузился. Остальные разделы лаборатории продолжают работать.</div>';
     return;
   }
   const q=bank[ogeIndex12%bank.length];
   box.innerHTML='<div class="oge-task">'+
    '<div class="oge12-top"><div class="oge-kicker">ОГЭ · задание №12</div><div class="oge12-counter">'+q.id+' / '+bank.length+'</div></div>'+
    '<div class="oge-title">Сразу три реакции — как в настоящем задании</div>'+
    '<div id="oge12Lab" class="oge12-lab"></div>'+
    '<div id="oge12Rows" class="oge12-match"></div>'+
    '<div class="oge12-options">'+q.options.map((x,i)=>'<div class="oge12-option"><b>'+(i+1)+'</b><span>'+x+'</span></div>').join("")+'</div>'+
    '<div id="oge12Feedback"></div>'+
    '<div class="oge12-actions"><button id="oge12Prev" type="button">← Предыдущее</button><button id="oge12Check" class="primary" type="button">Проверить</button></div>'+
    '<button id="ogeNext" class="oge-next" style="display:none" type="button">Следующее →</button></div>';
   document.getElementById("oge12Lab").innerHTML=["А","Б","В"].map((letter,i)=>oge12TubeCard(letter,q.reactants[i],"",false)).join("");
   const rows=document.getElementById("oge12Rows");
   ["А","Б","В"].forEach((letter,i)=>{
     const row=document.createElement("div");row.className="oge12-row";
     row.innerHTML='<div class="pair"><span class="letter">'+letter+')</span>'+oge12Subscripts(q.reactants[i])+'</div>'+
       '<select aria-label="Ответ '+letter+'"><option value="">—</option><option>1</option><option>2</option><option>3</option><option>4</option></select>';
     rows.appendChild(row);
   });
   document.getElementById("oge12Check").onclick=answerOge12;
   document.getElementById("oge12Prev").onclick=()=>{ogeIndex12=(ogeIndex12-1+bank.length)%bank.length;renderOge()};
   document.getElementById("ogeNext").onclick=()=>{ogeIndex12=(ogeIndex12+1)%bank.length;renderOge()};
 }else if(ogeMode===23){
   renderOge23();
 }else{
   const q=OGE17[ogeIndex17%OGE17.length],box=document.getElementById("ogeBox");
   box.innerHTML='<div class="oge-task"><div class="oge-kicker">ОГЭ · задание №17</div><div class="oge-title">Каким реактивом можно различить вещества?</div><div class="oge-pair">'+q.leftName+' и '+q.rightName+'</div><div id="ogeOptions" class="oge-options"></div><div id="ogeDemo" class="oge-demo"></div><div id="ogeFeedback" class="oge-feedback"></div><button id="ogeNext" class="oge-next" style="display:none">Следующее</button></div>';
   q.options.forEach(([id,label],i)=>{const b=document.createElement("button");b.textContent=(i+1)+") "+label;b.onclick=()=>answerOge17(id,b);document.getElementById("ogeOptions").appendChild(b)});
   document.getElementById("ogeNext").onclick=()=>{ogeIndex17++;renderOge()};
 }
}
function markOgeButtons(correctIndex,chosenIndex){
 [...document.getElementById("ogeOptions").children].forEach((b,i)=>{
   if(i===correctIndex)b.classList.add("correct");else if(i===chosenIndex)b.classList.add("wrong");b.disabled=true;
 });
}
function answerOge12(){
 if(ogeLocked)return;
 const bank=oge12Bank(),q=bank[ogeIndex12%bank.length];
 const rows=[...document.querySelectorAll("#oge12Rows .oge12-row")],chosen=rows.map(r=>r.querySelector("select").value);
 if(chosen.some(x=>!x)){
   document.getElementById("oge12Feedback").innerHTML='<div class="oge12-feedback">Сначала выбери цифру для А, Б и В.</div>';
   return;
 }
 ogeLocked=true;
 const correct=String(q.answer).split(""),ok=chosen.every((x,i)=>x===correct[i]);
 rows.forEach((row,i)=>{
   row.classList.add(chosen[i]===correct[i]?"good":"bad");
   const sel=row.querySelector("select");sel.disabled=true;
 });
 const signs=correct.map((n,i)=>q.options[Number(n)-1]);
 document.getElementById("oge12Lab").innerHTML=["А","Б","В"].map((letter,i)=>oge12TubeCard(letter,q.reactants[i],signs[i],true)).join("");
 document.getElementById("oge12Feedback").innerHTML='<div class="oge12-feedback">'+
   (ok?'✅ <b>Всё верно.</b>':'❌ <b>Есть ошибка.</b>')+
   '<br>Твой ответ: <b>'+chosen.join("")+'</b> · правильный: <b>'+correct.join("")+'</b>'+
   '<br>Теперь сверху одновременно видны признаки всех трёх реакций.</div>';
 document.getElementById("oge12Check").style.display="none";
 document.getElementById("ogeNext").style.display="block";
 api({action:"event",type:"prediction",correct:ok}).then(j=>{data.stats=j.stats;renderStats()});
}
function answerOge17(id,btn){
 if(ogeLocked)return;ogeLocked=true;
 const q=OGE17[ogeIndex17%OGE17.length],ok=id===q.correct,ci=q.options.findIndex(x=>x[0]===q.correct),chosen=q.options.findIndex(x=>x[0]===id);
 markOgeButtons(ci,chosen);
 const lx=reactionExpected(q.left,id),rx=reactionExpected(q.right,id);
 document.getElementById("ogeDemo").innerHTML=ogeTube([q.left,id],q.heat,q.leftName+' + '+btn.textContent.replace(/^\d+\)\s*/,''))+ogeTube([q.right,id],q.heat,q.rightName+' + '+btn.textContent.replace(/^\d+\)\s*/,''));
 let expl='';
 if(ok){
   expl='<b>✅ Реактив подходит.</b><br>В пробирках наблюдаются разные признаки, поэтому вещества можно различить.';
 }else{
   expl='<b>❌ Этот реактив не даёт надёжного различия.</b><br>Сравни, что происходит в обеих пробирках.';
 }
 document.getElementById("ogeFeedback").innerHTML='<div class="result">'+expl+'</div>'+
   '<div style="margin-top:8px">'+(lx?reactionResultHTML(lx,q.heat):'<div class="result">С '+q.leftName+' видимого признака нет.</div>')+'</div>'+
   '<div style="margin-top:8px">'+(rx?reactionResultHTML(rx,q.heat):'<div class="result">С '+q.rightName+' видимого признака нет.</div>')+'</div>';
 document.getElementById("ogeNext").style.display="block";
 api({action:"event",type:"prediction",correct:ok}).then(j=>{data.stats=j.stats;renderStats()});
}

function oge23Bank(){return (data&&Array.isArray(data.oge23))?data.oge23:[]}
function oge23Task(){const bank=oge23Bank();return bank.length?bank[oge23Index%bank.length]:null}
function oge23Reset(){
 oge23Rows=["",""];oge23Tests=[{},{}];oge23Conclusion=["",""];oge23Identified=false;
}
function oge23ExpForTool(task,tool){
 return (task.experiments||[]).find(x=>x.reagent===tool)||null;
}
function oge23Knowledge(id){
 const v=reagent(id)||[];
 return {
   id:id,
   formula:v[0]||id,
   category:v[1]||"",
   color:v[2]||"#f8fbff",
   state:v[3]||"",
   name:v[4]||id
 };
}
function oge23Reagent(task,id){
 const local=(task.reagents||[]).find(x=>x.id===id)||{};
 const k=oge23Knowledge(id);
 return {
   id:id,
   formula:k.formula||local.formula||id,
   name:k.name||local.name||id,
   category:k.category,
   color:k.color,
   state:k.state
 };
}
function oge23GasName(item){
 const lab=item&&item.lab;
 if(lab&&lab.gas)return lab.gas;
 const s=String(item&&item.text||"");
 if(/NH₃|NH3/i.test(s))return "NH₃";
 if(/CO₂|CO2/i.test(s))return "CO₂";
 if(/H₂|H2/i.test(s))return "H₂";
 if(/SO₂|SO2/i.test(s))return "SO₂";
 return "газ";
}
function oge23Visual(task,bottleIndex,tool,item){
 const bottleId=task.bottles[bottleIndex].id;
 const lab=item&&item.lab;
 if(lab){
   const gas=lab.gas?'<div class="oge23-gas-badge">🫧 '+lab.gas+' ↑</div>':'';
   return '<div class="oge23-live-visual '+(lab.gas?'has-gas':'')+'">'+gas+tubeHTML([bottleId,tool],0,false,false)+'</div>';
 }
 const base=oge23Knowledge(bottleId).color||"#f8fbff";
 if(!item||!item.active){
   return '<div class="oge23-mini-tube" style="--liq:'+base+'"><div class="oge23-mini-liquid"></div></div>';
 }
 const exp=item.exp||{},cls=exp.kind==="ppt"?"ppt":exp.kind==="gas"?"gas":exp.kind==="dissolve"?"dissolve":"";
 const gas=exp.kind==="gas"?'<div class="oge23-gas-badge">🫧 '+oge23GasName(item)+' ↑</div>':'';
 return '<div class="oge23-live-visual '+(exp.kind==="gas"?'has-gas':'')+'">'+gas+
   '<div class="oge23-mini-tube '+cls+'" style="--pc:'+(exp.color||"#fff")+';--liq:'+base+'"><div class="oge23-mini-liquid"></div><div class="oge23-mini-ppt"></div><div class="oge23-mini-bubbles"></div></div></div>';
}
function oge23Observation(task,bottleIndex,tool){
 const bankExp=oge23ExpForTool(task,tool);
 const bottleId=task.bottles[bottleIndex].id;
 const lab=reactionExpected(bottleId,tool);
 if(lab){
   const visible=!["n","z"].includes(lab.t);
   const text=lab.t==="z"?"Реакция не идёт.":(lab.t==="n"?"Без видимых изменений.":lab.sign);
   return {text:text,exp:bankExp,lab:lab,active:visible,diagnostic:!!(bankExp&&Number(bankExp.target_bottle)===bottleIndex+1)};
 }
 if(!bankExp)return {text:"Видимых изменений нет.",exp:null,lab:null,active:false,diagnostic:false};
 const active=Number(bankExp.target_bottle)===bottleIndex+1;
 return {text:active?bankExp.observation:"Видимых изменений нет.",exp:bankExp,lab:null,active:active,diagnostic:active};
}
function oge23BottleHTML(task,index){
 const obs=oge23Tests[index]||{},sub=task.bottles[index],k=oge23Knowledge(sub.id);
 const observations=Object.entries(obs).map(([tool,item])=>{
   const r=oge23Reagent(task,tool);
   return '<div class="oge23-observation"><strong>'+r.formula+' · '+r.name+'</strong>'+
    oge23Visual(task,index,tool,item)+'<div>'+item.text+'</div></div>';
 }).join("");
 return '<div class="oge23-bottle"><div class="oge23-bottle-title">Склянка №'+(index+1)+'</div>'+
  '<div class="oge23-glass" style="--bottle-color:'+k.color+'"><i></i></div>'+
  '<div class="oge23-bottle-colour"><span style="--sw:'+k.color+'"></span>Цвет раствора наблюдается в склянке</div>'+
  '<div class="oge23-observations">'+(observations||'<div class="oge23-step-note" style="text-align:center">Опытов пока нет</div>')+'</div></div>';
}
function oge23ShortResult(item){
 if(!item)return "";
 if(!item.active)return "Нет видимых изменений";
 const s=String(item.text||"").toLowerCase(),lab=item.lab||null,kind=(lab&&lab.t)||(item.exp&&item.exp.kind);
 if((lab&&lab.gas)||kind==="gas"){
   const gas=oge23GasName(item);
   const extra=(lab&&lab.sol&&lab.sol!=="#f8fbff"&&lab.sol!=="#ffffff")?" + меняется цвет раствора":"";
   return "🫧 Выделяется "+gas+extra;
 }
 if(kind==="p"||kind==="ppt"){
   if(s.includes("голуб"))return "⬇ Голубой осадок";
   if(s.includes("бур"))return "⬇ Бурый осадок";
   if(s.includes("жёл")||s.includes("желт"))return "⬇ Жёлтый осадок";
   if(s.includes("серо-зел"))return "⬇ Серо-зелёный осадок";
   return "⬇ Белый осадок";
 }
 if(kind==="c")return "🎨 "+(item.text||"Изменение цвета / растворение");
 if(kind==="x")return "✨ "+(item.text||"Есть несколько признаков");
 if(kind==="dissolve")return "✨ Растворение";
 return item.text||"Есть изменения";
}
function oge23RowSelect(task,rowIndex){
 const current=oge23Rows[rowIndex]||"",other=oge23Rows[rowIndex?0:1]||"";
 return '<select class="oge23-exp-select" data-oge23-row="'+rowIndex+'">'+
  '<option value="">Выбери реактив</option>'+
  task.reagents.map(r=>'<option value="'+r.id+'" '+(current===r.id?'selected ':'')+(other===r.id?'disabled ':'')+'>'+r.formula+' · '+r.name+'</option>').join("")+
  '</select>';
}
function oge23TableCell(task,rowIndex,bottleIndex){
 const tool=oge23Rows[rowIndex];
 if(!tool)return '<div class="oge23-cell-empty">Сначала выбери реактив слева</div>';
 const item=(oge23Tests[bottleIndex]||{})[tool];
 if(!item)return '<button type="button" class="oge23-exp-btn" data-oge23-grid-test="'+bottleIndex+'" data-row="'+rowIndex+'" data-tool="'+tool+'">+ Добавить в №'+(bottleIndex+1)+'</button>';
 const cls=item.active?"positive":"none",short=oge23ShortResult(item);
 return '<div class="oge23-exp-result '+cls+'">'+short+
   (oge23Mode==="learn"&&item.active?'<small>'+item.text+'</small>':'')+'</div>';
}
function oge23BottleHead(task,index){
 const chosen=oge23Conclusion[index],b=task.bottles.find(x=>x.id===chosen);
 const candidates=task.bottles.map(x=>oge23Knowledge(x.id).formula).join(" / ");
 return '<span class="oge23-head-main">Склянка №'+(index+1)+'</span><span class="oge23-head-sub">'+(b?oge23Knowledge(b.id).formula+' · '+oge23Knowledge(b.id).name:'кандидаты: '+candidates)+'</span>';
}
function oge23ConclusionSelect(task,index){
 const current=oge23Conclusion[index]||"",other=oge23Conclusion[index?0:1]||"";
 return '<select class="oge23-conclusion-select" data-oge23-conclusion="'+index+'">'+
  '<option value="">Кто в склянке?</option>'+
  task.bottles.map(b=>'<option value="'+b.id+'" '+(current===b.id?'selected ':'')+(other===b.id?'disabled ':'')+'>'+b.formula+' · '+b.name+'</option>').join("")+
  '</select>';
}
function oge23ExperimentTable(task){
 return '<div class="oge23-table-title"><b>Таблица эксперимента</b><span>Сначала выбери реактив в строке, затем добавь его в нужную склянку</span></div>'+
  '<div class="oge23-available"><span>Даны реактивы:</span>'+task.reagents.map(r=>{const k=oge23Knowledge(r.id);return '<span class="oge23-available-reagent"><i style="--rc:'+k.color+'"></i>'+k.formula+(k.state?' · '+k.state:'')+'</span>'}).join("")+'</div>'+
  '<div class="oge23-exp-table">'+
   '<div class="oge23-exp-row head"><div class="oge23-exp-cell">Реактив</div><div class="oge23-exp-cell">'+oge23BottleHead(task,0)+'</div><div class="oge23-exp-cell">'+oge23BottleHead(task,1)+'</div></div>'+
   [0,1].map(rowIndex=>'<div class="oge23-exp-row task-row">'+
    '<div class="oge23-exp-cell">'+oge23RowSelect(task,rowIndex)+'</div>'+
    '<div class="oge23-exp-cell">'+oge23TableCell(task,rowIndex,0)+'</div>'+
    '<div class="oge23-exp-cell">'+oge23TableCell(task,rowIndex,1)+'</div>'+
    '</div>').join("")+
   '<div class="oge23-exp-row oge23-conclusion">'+
    '<div class="oge23-exp-cell">Вывод</div>'+
    '<div class="oge23-exp-cell">'+oge23ConclusionSelect(task,0)+'</div>'+
    '<div class="oge23-exp-cell">'+oge23ConclusionSelect(task,1)+'</div>'+
   '</div>'+
  '</div>'+
  '<div class="oge23-table-check"><button id="oge23ResetExperiments" type="button">↺ Очистить таблицу</button><button id="oge23CheckTable" class="primary" type="button">Проверить таблицу и вывод</button></div>'+
  '<div id="oge23TableFeedback" class="oge23-table-feedback"></div>';
}
function oge23RunTest(task,bottleIndex,tool){
 const o=oge23Observation(task,bottleIndex,tool);
 oge23Tests[bottleIndex][tool]={text:o.text,exp:o.exp,lab:o.lab,active:o.active,diagnostic:o.diagnostic,revealed:true};
 renderOge23();
}
function oge23CheckTable(task){
 const feedback=document.getElementById("oge23TableFeedback");
 if(!oge23Rows[0]||!oge23Rows[1]){
   feedback.innerHTML='<div class="oge23-feedback">Сначала выбери два реактива в строках «Опыт 1» и «Опыт 2».</div>';return;
 }
 const used=[oge23Rows[0],oge23Rows[1]];
 if(new Set(used).size!==2){
   feedback.innerHTML='<div class="oge23-feedback">Для двух опытов выбери два разных реактива.</div>';return;
 }
 const allRun=used.every(tool=>oge23Tests[0][tool]&&oge23Tests[1][tool]);
 if(!allRun){
   feedback.innerHTML='<div class="oge23-feedback">Проведи каждый выбранный реактив с обеими склянками — тогда таблица будет заполнена полностью.</div>';return;
 }
 const pairCorrect=task.correct_reagents.every(x=>used.includes(x));
 if(!pairCorrect){
   feedback.innerHTML='<div class="oge23-feedback">❌ Эти два реактива не дают эталонного решения задания. Посмотри на признаки и замени один из реактивов.</div>';return;
 }
 if(!oge23Conclusion[0]||!oge23Conclusion[1]){
   feedback.innerHTML='<div class="oge23-feedback">Заполни строку «Вывод»: укажи, какое вещество находится в каждой склянке.</div>';return;
 }
 const conclusionCorrect=oge23Conclusion[0]===task.bottles[0].id&&oge23Conclusion[1]===task.bottles[1].id;
 if(!conclusionCorrect){
   feedback.innerHTML='<div class="oge23-feedback">❌ В выводе есть ошибка. Сопоставь признаки реакций со Склянкой №1 и Склянкой №2.</div>';return;
 }
 oge23Identified=true;
 feedback.innerHTML='<div class="oge23-feedback">✅ Таблица заполнена верно. Склянка №1 — <b>'+task.bottles[0].formula+'</b>, Склянка №2 — <b>'+task.bottles[1].formula+'</b>.</div>';
 renderOge23Equations(task);
}
function renderOge23(){
 const bank=oge23Bank(),box=document.getElementById("ogeBox");
 if(!bank.length){
  box.innerHTML='<div class="result">Банк №23 не загрузился. Остальные разделы лаборатории продолжают работать.</div>';
  return;
 }
 const task=oge23Task();
 box.innerHTML='<div class="oge23-wrap">'+
  '<div class="oge-task"><div class="oge23-task-title"><div><div class="oge-kicker">ОГЭ · задание №23</div><div class="oge-title">Практическая работа · вариант '+task.id+'</div></div><div class="oge12-counter">'+task.id+' / '+bank.length+'</div></div>'+
  '<div class="oge23-mode"><button id="oge23Learn" class="'+(oge23Mode==="learn"?"on":"")+'">Учусь</button><button id="oge23Exam" class="'+(oge23Mode==="exam"?"on":"")+'">Как на экзамене</button></div>'+
  '<div class="oge23-condition"><b>Условие.</b> '+task.condition+'</div>'+
  '<div class="oge23-nav"><button id="oge23Prev" type="button">← Пред.</button><div class="oge23-count">вариант '+task.id+' из '+bank.length+'</div><button id="oge23NextTop" type="button">След. →</button></div>'+
  '<div class="oge23-source">Источник: загруженный банк задания №23, стр. '+task.source_page+'</div></div>'+
  '<div class="oge23-step"><h3>Проведи эксперимент</h3>'+
   '<div class="oge23-step-note">Выбери два реактива прямо в таблице. Для каждого выбранного реактива проверь обе склянки. Результат каждого опыта сразу появится в нужной ячейке. В строке «Вывод» укажи, что находится в Склянке №1 и Склянке №2.</div>'+
   oge23ExperimentTable(task)+
   '<div class="oge23-lab">'+oge23BottleHTML(task,0)+oge23BottleHTML(task,1)+'</div>'+
  '</div>'+
  '<div id="oge23Equations"></div></div>';

 const move=d=>{oge23Index=(oge23Index+d+bank.length)%bank.length;oge23Reset();renderOge23()};
 document.getElementById("oge23Prev").onclick=()=>move(-1);
 document.getElementById("oge23NextTop").onclick=()=>move(1);
 document.getElementById("oge23Learn").onclick=()=>{oge23Mode="learn";oge23Reset();renderOge23()};
 document.getElementById("oge23Exam").onclick=()=>{oge23Mode="exam";oge23Reset();renderOge23()};

 document.querySelectorAll("[data-oge23-row]").forEach(sel=>{
   sel.onchange=()=>{
    const row=Number(sel.dataset.oge23Row),old=oge23Rows[row],val=sel.value;
    if(old){
      delete oge23Tests[0][old];delete oge23Tests[1][old];
    }
    oge23Rows[row]=val;oge23Identified=false;
    renderOge23();
   };
 });
 document.querySelectorAll("[data-oge23-grid-test]").forEach(btn=>{
   btn.onclick=()=>oge23RunTest(task,Number(btn.dataset.oge23GridTest),btn.dataset.tool);
 });
 document.querySelectorAll("[data-oge23-conclusion]").forEach(sel=>{
   sel.onchange=()=>{oge23Conclusion[Number(sel.dataset.oge23Conclusion)]=sel.value;oge23Identified=false;renderOge23()};
 });
 const reset=document.getElementById("oge23ResetExperiments");
 if(reset)reset.onclick=()=>{oge23Reset();renderOge23()};
 const check=document.getElementById("oge23CheckTable");
 if(check)check.onclick=()=>oge23CheckTable(task);
 if(oge23Identified)renderOge23Equations(task);
}
function renderOge23Equations(task){
 if(!oge23Identified)return;
 const root=document.getElementById("oge23Equations");if(!root)return;
 root.innerHTML='<div class="oge23-step"><h3>Оформи уравнения</h3><div class="oge23-step-note">Запиши молекулярное, полное и сокращённое ионное уравнения для двух диагностических опытов.</div>'+
  '<div class="oge23-equations">'+task.experiments.map((exp,i)=>{
    const r=oge23Reagent(task,exp.reagent),b=task.bottles[Number(exp.target_bottle)-1];
    return '<div class="oge23-eq-card"><div class="oge23-eq-title">Опыт '+(i+1)+' · '+r.formula+' + '+b.formula+'</div>'+
     '<label>Молекулярное</label><textarea placeholder="Запиши молекулярное уравнение"></textarea>'+
     '<label>Полное ионное</label><textarea placeholder="Запиши полное ионное уравнение"></textarea>'+
     '<label>Сокращённое ионное</label><textarea placeholder="Запиши сокращённое ионное уравнение"></textarea>'+
     '<button type="button" class="oge23-showref oge23-mainbtn" data-i="'+i+'">Сверить с эталоном</button>'+
     '<div id="oge23Ref'+i+'" class="oge23-reference"><b>Молекулярное:</b> '+exp.molecular+'<br><b>Полное ионное:</b> '+exp.full_ionic+'<br><b>Сокращённое ионное:</b> '+exp.net_ionic+'</div></div>';
  }).join("")+'</div>'+
  '<button id="oge23Finish" class="primary oge23-mainbtn">Завершить вариант</button><div id="oge23FinishFeedback"></div></div>';
 root.querySelectorAll(".oge23-showref").forEach(btn=>btn.onclick=()=>document.getElementById("oge23Ref"+btn.dataset.i).classList.add("show"));
 document.getElementById("oge23Finish").onclick=()=>{
   document.getElementById("oge23FinishFeedback").innerHTML='<div class="oge23-feedback">✅ Вариант '+task.id+' завершён. Можно перейти к следующему.</div>';
   api({action:"event",type:"labwork"}).then(j=>{data.stats=j.stats;renderStats()});
 };
}
document.getElementById("oge12Tab").onclick=()=>{ogeMode=12;renderOge()};
document.getElementById("oge17Tab").onclick=()=>{ogeMode=17;renderOge()};
document.getElementById("oge23Tab").onclick=()=>{ogeMode=23;oge23Reset();renderOge()};

function nextExam(){
 locked=false;document.getElementById("examResult").textContent="";
 const pool=data.reactions.filter(x=>!x.heat&&["p","g","c","n"].includes(x.t));
 exam=pool[Math.floor(Math.random()*pool.length)];
 document.getElementById("pair").textContent=reagent(exam.a)[0]+" + "+reagent(exam.b)[0];
 const box=document.getElementById("answers");box.innerHTML="";
 [["p","осадок"],["g","газ"],["c","изменение цвета"],["n","без видимого признака"]].forEach(([v,label])=>{
  const b=document.createElement("button");b.textContent=label;b.onclick=()=>answerExam(v);box.appendChild(b)
 });
}
function answerExam(v){
 if(locked)return;locked=true;const ok=v===exam.t;
 document.getElementById("examResult").innerHTML=(ok?"✅ ":"❌ ")+exam.sign+"<br>"+exam.eq;
 api({action:"event",type:"prediction",correct:ok}).then(j=>{data.stats=j.stats;renderStats()});
}
document.getElementById("next").onclick=nextExam;

function renderStats(){
 const s=data.stats;document.getElementById("statsBox").innerHTML=
 '<div class="stat"><b>'+s.experiments+'</b>опытов</div>'+
 '<div class="stat"><b>'+s.predictions+'</b>прогнозов</div>'+
 '<div class="stat"><b>'+s.accuracy+'%</b>точность</div>'+
 '<div class="stat"><b>'+s.labworks_completed+'</b>лабораторных</div>';
}
document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>{
 document.querySelectorAll("[data-page]").forEach(x=>x.classList.remove("on"));document.querySelectorAll(".page").forEach(x=>x.classList.remove("on"));
 b.classList.add("on");document.getElementById(b.dataset.page).classList.add("on");if(b.dataset.page==="exam"&&!exam)nextExam();if(b.dataset.page==="oge")renderOge();if(b.dataset.page==="ege")renderEge();
});
api({action:"load"}).then(j=>{
 if(!j.ok){document.body.innerHTML="<p>Не удалось открыть лабораторию.</p>";return}
 data=j.data;Object.entries(data.reagents).forEach(x=>reagentMap.set(x[0],x[1]));
 task6Progress=data.task6_progress||null;task6Session=data.task6_session||null;
 if(task6Session){task6SelectedX=task6Session.selected_x||"";task6SelectedY=task6Session.selected_y||"";task6Target=task6SelectedX&&!task6SelectedY?"y":"x";}
 data.reactions.forEach(x=>{const k=key(x.a,x.b);if(!reactionMap.has(k))reactionMap.set(k,[]);reactionMap.get(k).push(x)});
 const cv=document.getElementById("labCoverage");if(cv&&data.coverage)cv.textContent="В текущем ЕГЭ-каталоге: "+data.coverage.substances+" веществ · "+data.coverage.reactions+" реакций/условий.";
 renderTubes();renderReagents();setupMobileTubePicker();setupReagentFilters();setupReagentSearch();setupLab();renderStats();
 const requestedPage=labQs.get("page")||"";
 if(requestedPage){
   const btn=document.querySelector('[data-page="'+requestedPage+'"]');
   if(btn)btn.click();
 }
});
</script></body></html>'''

def do_get(self):
    if urlparse(self.path).path != "/lab-app":
        return _previous_get(self)
    body = HTML.encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type","text/html; charset=utf-8")
    self.send_header("Content-Length",str(len(body)))
    self.send_header("Cache-Control","no-store")
    self.send_header("X-Content-Type-Options","nosniff")
    self.end_headers()
    self.wfile.write(body)

def do_post(self):
    if urlparse(self.path).path != "/lab-app/api":
        return _previous_post(self)
    try:
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>50000:
            raise ValueError("bad length")
        request=json.loads(self.rfile.read(length).decode("utf-8"))
        uid=validate_init_data(request.get("init_data"))
        if not uid and request.get("launch"):
            try:
                import ege_student_webapp
                uid=ege_student_webapp._validate_launch_token(request.get("launch"))
            except Exception:
                uid=None
        action=request.get("action")
        if action=="load":
            # The chemistry content is public. Outside Telegram the page opens
            # in preview mode; inside Telegram we additionally load/save stats.
            preview_stats={
                "experiments":0,"predictions":0,"correct_predictions":0,
                "labworks_completed":0,"accuracy":0,
            }
            return self._send_json(200,{"ok":True,"data":{
                "reagents":REAGENTS,
                "reactions":reaction_payload(),
                "coverage":{"substances":len(REAGENTS),"reactions":len(reaction_payload()),"categories":category_counts()},
                "lab":["cuso4","fecl3","na2co3","nacl","na2so4"],
                "tools":["naoh","hcl","agno3","bacl2"],
                "task6":TASK6_BANK,
                "oge12":_oge12_bank_payload(),
                "oge23":_oge23_bank_payload(),
                "task6_progress":ege_task6_progress.progress(bot.COREAPP_DB_PATH,uid) if uid else {
                    "total":len(TASK6_BANK),"answered":0,"correct_tasks":0,"checks":0,
                    "correct_checks":0,"accuracy":0,"first_try_correct":0,
                    "first_try_accuracy":0,"error_task_ids":[],"error_count":0,"weak_types":[]
                },
                "task6_session":ege_task6_progress.load_session(bot.COREAPP_DB_PATH,uid) if uid else None,
                "stats":stats(uid) if uid else preview_stats,
                "preview":not bool(uid),
            }})
        if action=="event":
            if not uid:
                return self._send_json(200,{"ok":True,"stats":{
                    "experiments":0,"predictions":0,"correct_predictions":0,
                    "labworks_completed":0,"accuracy":0,
                }})
            return self._send_json(200,{"ok":True,"stats":record_event(uid,request.get("type"),bool(request.get("correct")))})

        if action=="task6_start":
            mode=str(request.get("mode") or "10")
            if mode not in {"10","20","all","errors"}:
                mode="10"
            if uid:
                session=ege_task6_progress.start_session(
                    bot.COREAPP_DB_PATH,uid,mode,bot.TIMEZONE
                )
                progress_payload=ege_task6_progress.progress(bot.COREAPP_DB_PATH,uid)
            else:
                session={
                    "mode":mode,
                    "order":ege_task6_progress.build_order(mode,[]),
                    "current_index":0,"selected_x":"","selected_y":""
                }
                progress_payload={
                    "total":len(TASK6_BANK),"answered":0,"correct_tasks":0,"checks":0,
                    "correct_checks":0,"accuracy":0,"first_try_correct":0,
                    "first_try_accuracy":0,"error_task_ids":[],"error_count":0,"weak_types":[]
                }
            return self._send_json(200,{"ok":True,"session":session,"progress":progress_payload})

        if action=="task6_save":
            if uid:
                session=ege_task6_progress.save_selection(
                    bot.COREAPP_DB_PATH,uid,
                    request.get("selected_x"),request.get("selected_y"),bot.TIMEZONE
                )
            else:
                session=None
            return self._send_json(200,{"ok":True,"session":session})

        if action=="task6_answer":
            task_id=str(request.get("task_id") or "")
            answer_x=str(request.get("answer_x") or "")
            answer_y=str(request.get("answer_y") or "")
            if uid:
                result=ege_task6_progress.record_answer(
                    bot.COREAPP_DB_PATH,uid,task_id,answer_x,answer_y,bot.TIMEZONE
                )
                if result.get("scored"):
                    result["lab_stats"]=record_event(
                        uid,"prediction",bool(result.get("correct"))
                    )
            else:
                result=ege_task6_progress.answer_key(task_id,answer_x,answer_y)
                if not result:
                    raise ValueError("unknown task")
                result["progress"]={
                    "total":len(TASK6_BANK),"answered":0,"correct_tasks":0,"checks":0,
                    "correct_checks":0,"accuracy":0,"first_try_correct":0,
                    "first_try_accuracy":0,"error_task_ids":[],"error_count":0,"weak_types":[]
                }
                result["session"]=None
            return self._send_json(200,{"ok":True,"result":result})

        return self._send_json(400,{"ok":False,"error":"bad_action"})
    except Exception as exc:
        print(f"EGE lab api error: {type(exc).__name__}: {exc}",flush=True)
        return self._send_json(400,{"ok":False,"error":"bad_request"})

def webapp_url():
    sep="&" if "?" in URL else "?"
    return f"{URL}{sep}v={BUILD}"

def install():
    global _INSTALLED,_previous_get,_previous_post,_previous_hub
    if _INSTALLED:
        return
    _INSTALLED=True
    ensure_tables()
    ege_task6_progress.ensure_tables(bot.COREAPP_DB_PATH)
    _previous_get=bot.CoreAppWebhookHandler.do_GET
    _previous_post=bot.CoreAppWebhookHandler.do_POST
    bot.CoreAppWebhookHandler.do_GET=do_get
    bot.CoreAppWebhookHandler.do_POST=do_post

    import public_channel_trainers as public
    _previous_hub=public._hub_markup

    async def hub_markup(context):
        markup=await _previous_hub(context)
        rows=[list(row) for row in markup.inline_keyboard]
        if URL and not any(getattr(b,"web_app",None) for row in rows for b in row):
            rows.insert(0,[InlineKeyboardButton("🧪 Лаборатория",web_app=WebAppInfo(url=webapp_url()))])
        return InlineKeyboardMarkup(rows)

    public._hub_markup=hub_markup

    # Maria asked to open the laboratory from her own cabinet too.
    live23=live90.live79.live23
    previous_admin_markup=live23.cabinet_markup

    def admin_markup():
        base=previous_admin_markup()
        rows=[list(row) for row in base.inline_keyboard]
        if URL and not any(
            getattr(button,"web_app",None)
            and getattr(getattr(button,"web_app",None),"url","").startswith(URL)
            for row in rows for button in row
        ):
            rows.insert(
                1 if rows else 0,
                [InlineKeyboardButton("🧪 Лаборатория",web_app=WebAppInfo(url=webapp_url()))],
            )
        return InlineKeyboardMarkup(rows)

    live23.cabinet_markup=admin_markup
    print(
        f"EGE lab ready: reagents={len(REAGENTS)} reactions={len(REACTIONS)} url={URL or 'missing'} admin_button=1",
        flush=True,
    )
