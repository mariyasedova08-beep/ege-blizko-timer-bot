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

bot = live90.bot
DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
URL = os.getenv(
    "EGE_LAB_WEBAPP_URL",
    f"https://{DOMAIN}/lab-app" if DOMAIN else "",
).strip()
BUILD = "20261007-lab-v12-ege24"
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

def pair_key(a, b):
    return "|".join(sorted((a, b)))

def reaction_payload():
    return [
        {"a":a,"b":b,"eq":eq,"t":kind,"sign":sign,"sol":sol,"ppt":ppt,"gas":gas,"heat":bool(heat)}
        for a,b,eq,kind,sign,sol,ppt,gas,heat in REACTIONS
    ]

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
.lab-bench{background:linear-gradient(180deg,#fff 0 68%,#f2ece8 68% 73%,#d7c0ad 73% 100%);border:1px solid #eadfe4;border-radius:22px;min-height:565px;padding:14px;position:relative;overflow:hidden;box-shadow:0 8px 25px rgba(35,20,28,.05)}
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
.tube-callout{position:absolute;z-index:30;width:300px;left:50%;bottom:calc(100% + 18px);transform:translateX(-50%);pointer-events:none}
.tube-callout.edge-left{left:0;transform:none}
.tube-callout.edge-right{left:auto;right:0;transform:none}
.tube-callout .reaction-card{margin:0;box-shadow:0 14px 34px rgba(240,0,135,.22)}
.tube-callout:after{content:"";position:absolute;left:50%;bottom:-10px;width:18px;height:18px;background:#f9dce9;border-right:2px solid #f00087;border-bottom:2px solid #f00087;transform:translateX(-50%) rotate(45deg)}
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
.reaction-equation{background:rgba(255,255,255,.82);border:1px solid rgba(240,0,135,.22);border-radius:13px;padding:9px 10px;font-size:13px;font-weight:900;line-height:1.25;letter-spacing:0;white-space:nowrap;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}
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
.oge-switch{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0 12px}
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
 .logo{font-size:11px;width:auto;height:auto;padding:7px 9px;border-radius:999px}
}
</style></head><body><div class="app">
<div class="logo">ЕГЭ БЛИЗКО</div><h1>🧪 Лаборатория</h1>
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
    <div id="reagentFilters" class="reagent-filters">
      <button class="reagent-filter on" data-cat="Все">Все</button>
      <button class="reagent-filter" data-cat="Кислоты">Кислоты</button>
      <button class="reagent-filter" data-cat="Основания">Основания</button>
      <button class="reagent-filter" data-cat="Соли">Соли</button>
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
    <div class="selected-card"><b>Выбрана пробирка <span id="selectedTubeLabel">1</span></b><span>Добавь до двух реактивов</span></div>
    <div class="control-stack">
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
</div>
<div id="ogeBox"></div>
</div></section>

<section id="ege" class="page"><div class="card">
<div class="ege-switch">
  <button id="ege24Tab" class="on">№24</button>
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
let data, reagentMap=new Map(), reactionMap=new Map(), selectedTube=0, selectedReagentCategory="Все";
let tubes=[[],[],[],[]], tubeHeat=[false,false,false,false], unknownOrder=[], unknownSelected=0, toolSelected="", attempts=0, exam=null, locked=false;
let ogeMode=12,ogeIndex12=0,ogeIndex17=0,ogeLocked=false;
let egeMode="24",egeIndex24=0,egeSignsIndex=0,egeQualityIndex=0,egeLocked=false;

function key(a,b){return [a,b].sort().join("|")}
function reagent(id){return reagentMap.get(id)}
function api(payload){return fetch("/lab-app/api",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.assign({init_data:tg.initData,launch:labLaunch},payload))}).then(r=>r.json())}
function findReaction(a,b,heated){let x=reactionMap.get(key(a,b));return x&&(!x.heat||heated)?x:null}
function reactionExpected(a,b){return reactionMap.get(key(a,b))||null}
function reactionResultHTML(x,heated=false){
 if(!x)return '<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">Нет данных</span></div><div class="reaction-sign">Этот опыт пока не добавлен в базу.</div></div>';
 if(x.heat&&!heated)return '<div class="reaction-card"><div class="reaction-head"><span class="reaction-status">🔥 Нужен нагрев</span></div><div class="reaction-sign">Без нагревания видимого результата не показываем.</div><div class="reaction-equation">'+x.eq+'</div></div>';
 const noVisible=x.t==="n";
 const icon=x.t==="p"?"⬇️":x.t==="g"?"🫧":x.t==="c"?"🎨":x.t==="x"?"✨":"✓";
 const title=noVisible?"Реакция протекает":"Реакция протекает";
 const sign=noVisible?"Без видимого признака":x.sign;
 return '<div class="reaction-card '+(noVisible?'no-visible':'')+'"><div class="reaction-head"><span class="reaction-status">'+icon+' '+title+'</span></div><div class="reaction-sign">Признак: '+sign+'</div><div class="reaction-equation">'+x.eq+'</div>'+(noVisible?'<div class="reaction-note">Реакция есть, но визуального эффекта в пробирке нет.</div>':'')+'</div>';
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
 const strong=["CO₂","SO₂","H₂S"].includes(x.gas);
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
 return (strong?'<div class="boilLayer">'+boil.join("")+'</div>':'')+'<div class="bubbleLayer '+(strong?'strong':'')+'">'+parts.join("")+'</div><div class="surfaceFizz">'+fizz.join("")+'</div><div class="gasPlume" style="--gasColor:'+gasColor+'"></div>';
}
function tubeHTML(v,i,active,heated){
 const x=v.length===2?findReaction(v[0],v[1],heated):null;
 const base=v.length?reagent(v[v.length-1])[2]:"#f8fbff";
 const sol=x?x.sol:base;
 const reactionVisual=x?(precipitateHTML(x)+bubblesHTML(x)+'<i class="reactionGlow"></i>'):"";
 const shimmer=(heated&&v.length)?'<i class="heatShimmer"></i>':"";
 return '<div class="tube '+(active?'on':'')+'"><i class="liq" style="height:'+(v.length?58:0)+'%;background:'+sol+'"></i>'+reactionVisual+shimmer+'</div>';
}
function renderTubes(){
 const box=document.getElementById("tubes");box.innerHTML="";
 tubes.forEach((v,i)=>{
  const wrap=document.createElement("div");wrap.className="tube-slot"+(i===selectedTube?" active-slot":"");
  const x=v.length===2?reactionExpected(v[0],v[1]):null;
  let callout="";
  if(i===selectedTube&&v.length===2){
    const cls=i===0?" edge-left":i===3?" edge-right":"";
    callout='<div class="tube-callout'+cls+'">'+reactionResultHTML(x,tubeHeat[i])+'</div>';
  }
  wrap.innerHTML=callout+tubeHTML(v,i,i===selectedTube,tubeHeat[i])+'<div class="tubeLabel">'+(i+1)+'</div><div class="tubeSmall">'+(v.map(q=>reagent(q)[0]).join(" + ")||"пусто")+'</div>';
  wrap.onclick=()=>{selectedTube=i;syncTubePicker();renderTubes()};box.appendChild(wrap);
 });
}
function syncTubePicker(){
 const lab=document.getElementById("selectedTubeLabel");if(lab)lab.textContent=String(selectedTube+1);
 const root=document.getElementById("mobileTubePicker");if(!root)return;
 root.querySelectorAll("[data-tube]").forEach(btn=>btn.classList.toggle("on",Number(btn.dataset.tube)===selectedTube));
}
function renderReagents(){
 const box=document.getElementById("reagents");box.innerHTML="";
 const order=["Кислоты","Основания","Соли"];
 order.forEach(cat=>{
   if(selectedReagentCategory!=="Все"&&selectedReagentCategory!==cat)return;
   const entries=Object.entries(data.reagents).filter(([id,v])=>v[1]===cat);
   if(!entries.length)return;
   const group=document.createElement("div");group.className="reagent-group";
   const title=document.createElement("div");title.className="reagent-group-title";title.textContent=cat;group.appendChild(title);
   entries.forEach(([id,v])=>{
     const b=document.createElement("button");b.className="reagent-item";
     b.innerHTML='<span class="drop-icon" style="--rc:'+v[2]+'"></span><span><div class="rformula">'+v[0]+'</div><div class="rcat">'+v[1]+'</div></span>';
     b.onclick=()=>add(id);group.appendChild(b);
   });
   box.appendChild(group);
 });
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
function add(id){
 if(tubes[selectedTube].length>=2)return;
 tubeHeat[selectedTube]=false;
 tubes[selectedTube].push(id);
 if(tubes[selectedTube].length===2){
  let x=reactionExpected(tubes[selectedTube][0],tubes[selectedTube][1]);
  document.getElementById("result").innerHTML=x?(x.heat?"Нужен нагрев 🔥":"Карточка реакции показана над пробиркой ↑"):"Этот опыт пока не добавлен в базу";
  if(x&&!x.heat)api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()});
 }
 renderTubes();
}
document.getElementById("heat").onclick=()=>{
 let v=tubes[selectedTube];tubeHeat[selectedTube]=true;
 let x=v.length===2?findReaction(v[0],v[1],true):null;
 if(x){document.getElementById("result").innerHTML="Карточка реакции показана над пробиркой ↑";api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()})}
 else if(v.length===2){document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🔥 Нагрев</span></div><div class="reaction-sign">При нагревании видимого изменения нет.</div></div>'}
 renderTubes();
};
document.getElementById("clear").onclick=()=>{tubes[selectedTube]=[];tubeHeat[selectedTube]=false;document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🧽 Готово</span></div><div class="reaction-sign">Пробирка очищена.</div></div>';renderTubes()};

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
 document.getElementById("ege24Tab").classList.toggle("on",mode==="24");
 document.getElementById("egeSignsTab").classList.toggle("on",mode==="signs");
 document.getElementById("egeQualityTab").classList.toggle("on",mode==="quality");
 renderEge();
}
function renderEge(){
 const box=document.getElementById("egeBox");egeLocked=false;
 if(egeMode==="24")return renderEge24(box);
 if(egeMode==="signs")return renderEgeSigns(box);
 return renderEgeQuality(box);
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
document.getElementById("ege24Tab").onclick=()=>setEgeMode("24");
document.getElementById("egeSignsTab").onclick=()=>setEgeMode("signs");
document.getElementById("egeQualityTab").onclick=()=>setEgeMode("quality");

const OGE12=[
 {a:"ki",b:"agno3",pair:"KI + AgNO₃",options:["выделение газа без запаха","выделение газа с запахом","выпадение белого осадка","выпадение жёлтого осадка"],correct:3},
 {a:"hcl",b:"na2so3",pair:"HCl + Na₂SO₃",options:["выпадение белого осадка","выделение бесцветного газа с запахом","изменение цвета раствора","видимые признаки отсутствуют"],correct:1},
 {a:"cuso4",b:"naoh",pair:"CuSO₄ + NaOH",options:["выпадение белого осадка","выпадение голубого осадка","выделение газа","видимые признаки отсутствуют"],correct:1},
 {a:"fecl3",b:"naoh",pair:"FeCl₃ + NaOH",options:["выпадение бурого осадка","выпадение голубого осадка","выделение газа","видимые признаки отсутствуют"],correct:0},
 {a:"naoh",b:"hno3",pair:"NaOH + HNO₃",options:["выделение газа","видимые признаки отсутствуют","растворение осадка","образование осадка"],correct:1},
 {a:"na2co3",b:"cacl2",pair:"Na₂CO₃ + CaCl₂",options:["выделение газа","видимые признаки отсутствуют","растворение осадка","образование осадка"],correct:3}
];
const OGE17=[
 {left:"na2co3",right:"na2sio3",leftName:"Na₂CO₃",rightName:"Na₂SiO₃",options:[["hcl","HCl"],["naoh","NaOH"],["agno3","AgNO₃"],["bacl2","BaCl₂"]],correct:"hcl",heat:false},
 {left:"nh4cl",right:"nacl",leftName:"NH₄Cl",rightName:"NaCl",options:[["naoh","NaOH"],["agno3","AgNO₃"],["hcl","HCl"],["bacl2","BaCl₂"]],correct:"naoh",heat:true}
];
function ogeTube(pair,heated,label){
 return '<div class="oge-demo-two">'+tubeHTML(pair,0,false,heated)+'<div class="oge-demo-label">'+label+'</div></div>';
}
function renderOge(){
 ogeLocked=false;
 document.getElementById("oge12Tab").classList.toggle("on",ogeMode===12);
 document.getElementById("oge17Tab").classList.toggle("on",ogeMode===17);
 if(ogeMode===12){
   const q=OGE12[ogeIndex12%OGE12.length],box=document.getElementById("ogeBox");
   box.innerHTML='<div class="oge-task"><div class="oge-kicker">ОГЭ · задание №12</div><div class="oge-title">Какой признак реакции наблюдается?</div><div class="oge-pair">'+q.pair+'</div><div id="ogeOptions" class="oge-options"></div><div id="ogeDemo" class="oge-demo"></div><div id="ogeFeedback" class="oge-feedback"></div><button id="ogeNext" class="oge-next" style="display:none">Следующее</button></div>';
   q.options.forEach((label,i)=>{
     const b=document.createElement("button");b.textContent=(i+1)+") "+label;b.onclick=()=>answerOge12(i);document.getElementById("ogeOptions").appendChild(b);
   });
   document.getElementById("ogeNext").onclick=()=>{ogeIndex12++;renderOge()};
 } else {
   const q=OGE17[ogeIndex17%OGE17.length],box=document.getElementById("ogeBox");
   box.innerHTML='<div class="oge-task"><div class="oge-kicker">ОГЭ · задание №17</div><div class="oge-title">Каким реактивом можно различить вещества?</div><div class="oge-pair">'+q.leftName+' и '+q.rightName+'</div><div id="ogeOptions" class="oge-options"></div><div id="ogeDemo" class="oge-demo"></div><div id="ogeFeedback" class="oge-feedback"></div><button id="ogeNext" class="oge-next" style="display:none">Следующее</button></div>';
   q.options.forEach(([id,label],i)=>{
     const b=document.createElement("button");b.textContent=(i+1)+") "+label;b.onclick=()=>answerOge17(id,b);document.getElementById("ogeOptions").appendChild(b);
   });
   document.getElementById("ogeNext").onclick=()=>{ogeIndex17++;renderOge()};
 }
}
function markOgeButtons(correctIndex,chosenIndex){
 [...document.getElementById("ogeOptions").children].forEach((b,i)=>{
   if(i===correctIndex)b.classList.add("correct");else if(i===chosenIndex)b.classList.add("wrong");
   b.disabled=true;
 });
}
function answerOge12(choice){
 if(ogeLocked)return;ogeLocked=true;
 const q=OGE12[ogeIndex12%OGE12.length],ok=choice===q.correct,x=reactionExpected(q.a,q.b);
 markOgeButtons(q.correct,choice);
 document.getElementById("ogeDemo").innerHTML='<div class="oge-demo-one">'+tubeHTML([q.a,q.b],0,false,true)+'</div>';
 document.getElementById("ogeFeedback").innerHTML=(ok?'✅ <b>Верно.</b> ':'❌ <b>Смотри на опыт.</b> ')+reactionResultHTML(x,true);
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
document.getElementById("oge12Tab").onclick=()=>{ogeMode=12;renderOge()};
document.getElementById("oge17Tab").onclick=()=>{ogeMode=17;renderOge()};

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
 data=j.data;Object.entries(data.reagents).forEach(x=>reagentMap.set(x[0],x[1]));data.reactions.forEach(x=>reactionMap.set(key(x.a,x.b),x));
 renderTubes();renderReagents();setupMobileTubePicker();setupReagentFilters();setupLab();renderStats();
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
                "lab":["cuso4","fecl3","na2co3","nacl","na2so4"],
                "tools":["naoh","hcl","agno3","bacl2"],
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
