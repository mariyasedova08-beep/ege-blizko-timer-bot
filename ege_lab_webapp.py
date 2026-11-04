"""Interactive chemistry laboratory Mini App for EGE BLIZKO."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import run_bot_live90 as live90
from ege_lab_substances import REAGENTS as LAB_REAGENTS, category_counts
from ege_lab_inorganic_reactions import EXTRA_REACTIONS, REACTION_VARIANTS, MEDIUM_REACTIONS, validate_reactions
from ege_lab_exchange_matrix import generate_exchange_reactions
from ege_task6_bank import TASK6_BANK, validate_task6_bank
from ege_task6_reactions import TASK6_REACTIONS, TASK6_VARIANTS, validate_task6_reactions
import ege_task6_progress

bot = live90.bot
DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
URL = os.getenv(
    "EGE_LAB_WEBAPP_URL",
    f"https://{DOMAIN}/lab-app" if DOMAIN else "",
).strip()
BUILD = "20261101-isolated-board-review-v1"

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

# Amphoteric solid oxides: show their consumption in hot concentrated alkali.
# Keep these keys local until the shared substance catalogue is updated too.
REAGENTS.setdefault("zno", ("ZnO", "Оксиды", "#f5f6f3", "тв."))
REAGENTS.setdefault("al2o3", ("Al₂O₃", "Оксиды", "#f6f7f5", "тв."))
REAGENTS.setdefault("beo", ("BeO", "Оксиды", "#f5f6f3", "тв."))

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
# Hydroxocomplexes in aqueous concentrated alkali; heating is required in
# the simulator so these transformations are not shown for cold dilute base.
AMPHOTERIC_OXIDE_REACTIONS = [
    ("zno", "naoh", "ZnO + 2NaOH + H₂O → Na₂[Zn(OH)₄]", "x", "растворение твёрдого ZnO с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
    ("zno", "koh", "ZnO + 2KOH + H₂O → K₂[Zn(OH)₄]", "x", "растворение твёрдого ZnO с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
    ("al2o3", "naoh", "Al₂O₃ + 2NaOH + 3H₂O → 2Na[Al(OH)₄]", "x", "растворение твёрдого Al₂O₃ с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
    ("al2o3", "koh", "Al₂O₃ + 2KOH + 3H₂O → 2K[Al(OH)₄]", "x", "растворение твёрдого Al₂O₃ с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
    ("beo", "naoh", "BeO + 2NaOH + H₂O → Na₂[Be(OH)₄]", "x", "растворение твёрдого BeO с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
    ("beo", "koh", "BeO + 2KOH + H₂O → K₂[Be(OH)₄]", "x", "растворение твёрдого BeO с образованием гидроксокомплекса", "#f8fbff", "", "", 1),
]
# Prefer the condition-aware solid-dissolution records if an older catalogue
# happens to contain a shorter entry for the same oxide/alkali pair.
REACTIONS = AMPHOTERIC_OXIDE_REACTIONS + REACTIONS
# Explicit EGE chemistry always has precedence over generated ion-exchange pairs.
# It includes hydrolysis, Fe/Cu redox, Cu basic salts, reagent excess and pH.
_EXPLICIT_PAIRS = [(a, b) for a, b, *_ in REACTIONS]
_EXPLICIT_PAIRS.extend((x["a"], x["b"]) for x in REACTION_VARIANTS)
_EXPLICIT_PAIRS.extend((x["a"], x["b"]) for x in TASK6_VARIANTS)
_EXPLICIT_PAIRS.extend((x["a"], x["b"]) for x in MEDIUM_REACTIONS)
EXCHANGE_REACTIONS = generate_exchange_reactions(REAGENTS, _EXPLICIT_PAIRS)
validate_reactions(set(REAGENTS))
validate_task6_reactions(set(REAGENTS))
validate_task6_bank(set(REAGENTS))

def pair_key(a, b):
    return "|".join(sorted((a, b)))

AMPHOTERIC_STAGES = {"alcl3":("AlCl₃ + 3NaOH → Al(OH)₃↓ + 3NaCl","Al(OH)₃ + NaOH → Na[Al(OH)₄]"),"alno3":("Al(NO₃)₃ + 3NaOH → Al(OH)₃↓ + 3NaNO₃","Al(OH)₃ + NaOH → Na[Al(OH)₄]"),"al2so43":("Al₂(SO₄)₃ + 6NaOH → 2Al(OH)₃↓ + 3Na₂SO₄","Al(OH)₃ + NaOH → Na[Al(OH)₄]"),"znso4":("ZnSO₄ + 2NaOH → Zn(OH)₂↓ + Na₂SO₄","Zn(OH)₂ + 2NaOH → Na₂[Zn(OH)₄]"),"zncl2":("ZnCl₂ + 2NaOH → Zn(OH)₂↓ + 2NaCl","Zn(OH)₂ + 2NaOH → Na₂[Zn(OH)₄]"),"znno3":("Zn(NO₃)₂ + 2NaOH → Zn(OH)₂↓ + 2NaNO₃","Zn(OH)₂ + 2NaOH → Na₂[Zn(OH)₄]")}

def reaction_payload():
    payload = [
        {
            "a":a,"b":b,"eq":eq,"t":kind,"sign":sign,"sol":sol,
            "ppt":ppt,"ppt2":"#e9ca3c" if "FeS↓ + S↓" in eq else "", "gas":gas,"heat":bool(heat),"excess":"",
            "condition":("водный раствор концентрированной щёлочи; нагревание (не сплавление)" if a == "beo" else "концентрированная щёлочь, нагревание" if a in {"zno", "al2o3"} else "")
        }
        for a,b,eq,kind,sign,sol,ppt,gas,heat in REACTIONS
    ]
    # Curated Mn(IV) oxidizer demonstrations. Keep the imported equations,
    # enrich their teaching metadata rather than creating duplicate pairs.
    for row in payload:
        if row["a"] == "mno2" and row["b"] in {"hcl", "hbr"}:
            bromide = row["b"] == "hbr"
            row["oxidizer"] = "MnO₂: Mn(+4) → Mn(+2)"
            row["reducer"] = "HBr: Br(−1) → Br(0)" if bromide else "HCl: Cl(−1) → Cl(0)"
            row["electron_balance"] = ["Mn(+4) + 2e⁻ → Mn(+2)",
                "2Br(−1) − 2e⁻ → Br₂(0)" if bromide else "2Cl(−1) − 2e⁻ → Cl₂(0)"]
            row["condition"] = "водный раствор HBr" if bromide else "концентрированная HCl; нагревание"
            row["sign"] = ("Тёмный твёрдый MnO₂ постепенно расходуется; раствор приобретает оранжево-бурую окраску Br₂."
                if bromide else "Тёмный твёрдый MnO₂ постепенно расходуется; выделяется жёлто-зелёный Cl₂.")
    for row in payload:
        if row["a"] in {"cu2o", "fe3o4", "fe", "al", "cr"} and row["b"] in {"hno3", "hno3_conc", "h2so4_conc"} and row["t"] != "z":
            acid = row["b"]
            row["condition"] = ("концентрированная H₂SO₄; нагревание" if acid == "h2so4_conc" else
                "концентрированная HNO₃" if acid == "hno3_conc" else
                "разбавленная HNO₃; стандартный вариант восстановления до NO (не очень разбавленная кислота)")
            if row["heat"] and acid == "hno3_conc":
                row["condition"] += "; нагревание"
            if row["a"] in {"cu2o", "fe3o4"}:
                sulfur = acid == "h2so4_conc"
                row["oxidizer"] = "H₂SO₄: S(+6) → S(+4)" if sulfur else ("HNO₃: N(+5) → N(+4)" if acid == "hno3_conc" else "HNO₃: N(+5) → N(+2)")
                row["reducer"] = "Cu₂O: Cu(+1) → Cu(+2)" if row["a"] == "cu2o" else "Fe₃O₄: Fe(+2) → Fe(+3)"
                row["electron_balance"] = [("S(+6) + 2e⁻ → S(+4)" if sulfur else "N(+5) + e⁻ → N(+4)" if acid == "hno3_conc" else "N(+5) + 3e⁻ → N(+2)"),
                    "Cu(+1) − e⁻ → Cu(+2)" if row["a"] == "cu2o" else "Fe(+2) − e⁻ → Fe(+3)"]
    payload.extend(dict(item) for item in EXCHANGE_REACTIONS)
    for salt, (first, second) in AMPHOTERIC_STAGES.items():
        if not any({r["a"], r["b"]} == {salt, "naoh"} and not r.get("excess") for r in payload):
            payload.append({"a":salt,"b":"naoh","eq":first,"t":"p",
                "sign":"белый студенистый осадок " + ("Al(OH)₃" if salt.startswith("al") else "Zn(OH)₂"),
                "sol":"#f8fbff","ppt":"#ffffff","gas":"","heat":False,"excess":"","condition":"недостаток щёлочи"})
    for item in REACTION_VARIANTS:
        row = dict(item)
        if row.get("excess") == "naoh" and row["a"] in AMPHOTERIC_STAGES:
            first, second = AMPHOTERIC_STAGES[row["a"]]
            row["stages"] = {"first":first,"second":second,"total":row["eq"]}
        payload.append(row)
    # Potassium hydroxide follows the same two-stage chemistry.
    # Formula substitution is limited to the reviewed sodium/potassium analogues.
    for variant in REACTION_VARIANTS:
        salt = variant["a"]
        if variant.get("excess") != "naoh" or salt not in AMPHOTERIC_STAGES:
            continue
        first_na, second_na = AMPHOTERIC_STAGES[salt]
        first_k = first_na.replace("Na", "K")
        second_k = second_na.replace("Na", "K")
        total_k = variant["eq"].replace("Na", "K")
        if not any({r["a"], r["b"]} == {salt, "koh"} and not r.get("excess") for r in payload):
            payload.append({"a":salt,"b":"koh","eq":first_k,"t":"p",
                "sign":"белый студенистый осадок " + ("Al(OH)₃" if salt.startswith("al") else "Zn(OH)₂"),
                "sol":"#f8fbff","ppt":"#ffffff","gas":"","heat":False,"excess":"","condition":"недостаток щёлочи"})
        payload.append({"a":salt,"b":"koh","eq":total_k,"t":"c",
            "sign":"белый осадок сначала выпадает, затем растворяется в избытке KOH",
            "sol":"#f8fbff","ppt":"","gas":"","heat":False,
            "excess":"koh","condition":"избыток KOH",
            "stages":{"first":first_k,"second":second_k,"total":total_k}})
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
.lesson-pilot-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:6px 10px;margin-bottom:6px;color:#796473;font-size:11px}
.lesson-pilot-bar[hidden]{display:none}
.lesson-pilot-bar button{min-height:32px;padding:5px 9px;font-size:11px;background:#fff;border:1px solid #eadbe4;border-radius:9px;color:#983568}
.lesson-pilot-dialog{max-width:620px;width:calc(100% - 32px);max-height:85vh;overflow:auto;border:1px solid #eadbe4;border-radius:18px;padding:22px;color:#171719;background:#fffdfb}
.lesson-pilot-dialog::backdrop{background:rgba(35,20,28,.35)}
.lesson-pilot-dialog p{font-size:14px;line-height:1.5}
.lesson-pilot-dialog textarea{display:block;width:100%;margin:8px 0;padding:10px;border:1px solid #dcc9d4;border-radius:10px;font:inherit;resize:vertical}
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
.tube-slot:has(.pptLayer){isolation:isolate}
/* The precipitate must be visible inside the glass, without a grey block behind the tube. */
.tube-slot:has(.pptLayer):before{content:none}
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
.reaction-gas{margin-top:8px;padding:8px 9px;background:rgba(255,255,255,.7);border:1px solid rgba(163,124,105,.24);border-radius:10px;font-size:11px;line-height:1.45;color:#423630}
.reaction-gas b{font-weight:650}
.reaction-gas .gas-safety{display:block;margin-top:4px;color:#836d63;font-size:10px}
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
.tube:has(.pptLayer){background:linear-gradient(90deg,rgba(255,255,255,.18),rgba(255,255,255,.035) 26%,transparent 55%,rgba(255,255,255,.12) 86%,rgba(255,255,255,.16));box-shadow:inset 3px 0 4px rgba(255,255,255,.2),inset -3px 0 5px rgba(30,38,47,.07),0 4px 9px rgba(39,38,43,.1)}
.tube:has(.pptLayer):before{background:rgba(246,249,251,.18)}
.tube:has(.pptLayer) .liq{box-shadow:inset 0 7px 10px rgba(255,255,255,.08),inset 0 -7px 9px rgba(0,0,0,.025)}
.liq{position:absolute;bottom:0;left:2px;right:2px;height:0;z-index:1;transition:height .5s ease,background 1.1s ease;box-shadow:inset 0 8px 11px rgba(255,255,255,.24),inset 0 -8px 10px rgba(0,0,0,.06)}
.liq.oxide-turbidity{background:rgba(225,232,235,.80)!important;box-shadow:inset 0 8px 12px rgba(255,255,255,.48),inset 0 -8px 12px rgba(148,161,169,.15)}
.liq.oxide-turbidity:after{content:"";position:absolute;inset:5% 3%;background:radial-gradient(circle at 20% 30%,rgba(255,255,255,.64),transparent 34%),radial-gradient(circle at 72% 62%,rgba(255,255,255,.42),transparent 42%);filter:blur(5px);pointer-events:none}
.liq:before{content:"";position:absolute;left:0;right:0;top:-5px;height:10px;border-radius:50%;background:inherit;filter:brightness(1.08);box-shadow:inset 0 2px 3px rgba(255,255,255,.58),0 1px 1px rgba(0,0,0,.10)}
.pptLayer{position:absolute;z-index:3;left:3px;right:3px;bottom:2px;height:54%;pointer-events:none;overflow:hidden;border-radius:0 0 24px 24px}
.particle{position:absolute;bottom:var(--b);left:var(--l);width:var(--s);height:var(--s);background:var(--pc);opacity:.90;filter:drop-shadow(0 1px 1px rgba(0,0,0,.13));animation:settle .9s cubic-bezier(.2,.7,.3,1) both}
.particle.floc{border-radius:44% 56% 48% 52%;transform:rotate(var(--r)) scaleX(1.45);filter:blur(.25px) drop-shadow(0 1px 1px rgba(0,0,0,.11))}
.particle.gel{border-radius:50% 44% 52% 46%;opacity:.62;filter:blur(1.2px);transform:scaleX(1.8)}
.particle.crystal{border-radius:2px;transform:rotate(var(--r));opacity:.94;box-shadow:0 0 2px rgba(255,255,255,.45)}
.particle.fine{border-radius:48%;opacity:.76;filter:blur(.28px);box-shadow:0 1px 1px rgba(0,0,0,.07)}
.particle.dense{border-radius:37% 53% 44% 48%;opacity:.94;filter:blur(.3px);box-shadow:0 1px 2px rgba(0,0,0,.17)}
.pptLayer.dense-sediment{isolation:isolate}
.pptLayer.light-ppt:before{content:"";position:absolute;left:3%;right:3%;bottom:0;height:38%;background:radial-gradient(ellipse at 50% 95%,rgba(246,249,251,.98) 0 34%,rgba(255,255,255,.82) 58%,rgba(255,255,255,.10) 94%,transparent 100%);border-radius:48% 52% 12% 12%;box-shadow:inset 0 2px 2px rgba(119,135,145,.16),0 -2px 5px rgba(99,119,132,.11);filter:blur(1.2px);pointer-events:none}
.pptLayer.light-ppt .particle{background:rgba(255,255,255,1);border:1px solid rgba(97,116,129,.45);box-shadow:0 1px 3px rgba(58,77,91,.34),inset 0 1px 1px rgba(255,255,255,.98);animation-name:settleLight}
.pptLayer.light-ppt .particle.floc{background:radial-gradient(ellipse at 46% 40%,#fff 22%,rgba(248,251,253,.98) 58%,rgba(230,238,244,.62));border-radius:32% 69% 46% 58%;border-color:rgba(117,134,145,.44);filter:blur(.25px);box-shadow:0 2px 4px rgba(55,75,89,.32)}
.pptLayer.light-ppt .particle.fine{width:calc(var(--s)*1.25);height:calc(var(--s)*1.25);background:rgba(255,255,255,.98);border:1px solid rgba(86,105,117,.52);border-radius:50%;filter:none;box-shadow:0 1px 2px rgba(55,65,75,.28)}
.pptLayer.light-ppt .gel-bed{height:49%;background:radial-gradient(ellipse at 45% 80%,rgba(255,255,255,1) 0 38%,rgba(242,248,251,.98) 65%,rgba(194,209,219,.46) 100%);border:1px solid rgba(99,122,138,.37);box-shadow:0 2px 5px rgba(78,102,119,.27),inset 0 3px 5px rgba(255,255,255,.95);filter:blur(.7px);animation-name:gelBedGrowLight}
.pptLayer.light-ppt .gel-bed:before{background:rgba(255,255,255,.77);filter:blur(5px);opacity:.87}
.pptLayer.light-ppt .gel-cloud{background:radial-gradient(ellipse at 50% 50%,rgba(255,255,255,1) 0 25%,rgba(247,251,253,.94) 48%,rgba(219,232,241,.56) 77%,transparent 100%);border:0;box-shadow:0 1px 3px rgba(86,106,120,.13);filter:blur(1.1px);animation-name:gelCloudSettleLight}
.pptLayer:not(.light-ppt) .particle.floc{border-radius:36% 62% 48% 60%;filter:blur(.35px) drop-shadow(0 1px 1px rgba(0,0,0,.13))}
.pptLayer:not(.light-ppt) .particle.fine{width:calc(var(--s)*.7);height:calc(var(--s)*.7);border-radius:48%;filter:blur(.35px)}
.pptLayer:not(.light-ppt) .particle.crystal{clip-path:polygon(18% 0,80% 8%,100% 51%,69% 100%,4% 78%,0 28%);border-radius:0;filter:drop-shadow(0 1px 1px rgba(0,0,0,.15))}
.pptLayer:not(.light-ppt) .particle.dense{border-radius:24% 68% 39% 49%;filter:blur(.35px) drop-shadow(0 1px 1px rgba(0,0,0,.16))}
.dense-bed{position:absolute;left:6%;right:6%;bottom:0;height:22%;border-radius:48% 51% 16% 16% / 42% 49% 12% 12%;background:var(--pc);opacity:.91;filter:blur(.8px);animation:denseBedSettle 1.3s ease-out both}
@keyframes denseBedSettle{from{opacity:0;transform:translateY(-22px) scaleY(.4)}to{opacity:.91;transform:translateY(0) scaleY(1)}}
/* Gel-like hydroxides: soft suspension and irregular settling, not gas-like circles. */
.gel-sediment{isolation:isolate}
.gel-bed{position:absolute;z-index:2;left:7%;right:7%;bottom:1px;height:24%;background:var(--pc);border-radius:48% 52% 19% 17% / 62% 72% 22% 19%;filter:blur(3px);opacity:.84;transform-origin:center bottom;animation:gelBedGrow 1.7s ease-out both}
.gel-bed:before{content:"";position:absolute;left:2%;right:4%;top:-25%;height:85%;background:var(--pc);border-radius:45% 58% 48% 46%;filter:blur(4px);opacity:.66}
.gel-cloud{position:absolute;z-index:1;left:var(--l);bottom:var(--b);width:var(--w);height:var(--h);background:var(--pc);border-radius:43% 58% 52% 41% / 61% 38% 62% 47%;filter:blur(4px);opacity:.5;animation:gelCloudSettle 1.8s cubic-bezier(.18,.62,.25,1) both;animation-delay:var(--delay)}
@keyframes gelBedGrow{from{transform:scaleY(.18);opacity:0}to{transform:scaleY(1);opacity:.84}}
@keyframes gelCloudSettle{0%{transform:translateY(-57px) scale(1.16);opacity:0}38%{opacity:.55}100%{transform:translateY(0) scale(1);opacity:.50}}
@keyframes gelBedGrowLight{from{transform:scaleY(.18);opacity:0}to{transform:scaleY(1);opacity:1}}
@keyframes gelCloudSettleLight{0%{transform:translateY(-57px) scale(1.16);opacity:0}38%{opacity:.75}100%{transform:translateY(0) scale(1);opacity:.94}}
@keyframes settleLight{from{transform:translateY(-75px) scale(.55);opacity:.1}to{opacity:1}}
@media(prefers-reduced-motion:reduce){.gel-bed,.gel-cloud{animation:none}}
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
/* Pour a visible stream, raise the meniscus, then let surface ripples settle. */
.liq.filling{animation:liquidFill 1s ease-out both;animation-delay:var(--pourAge,0s)}
.pourStream{position:absolute;z-index:8;top:-2px;bottom:var(--toLevel);left:42%;width:7%;min-width:4px;background:var(--pourColor);border:1px solid rgba(97,141,164,.45);border-radius:0 0 50% 50%;animation:liquidStream 1s ease-out both;animation-delay:var(--pourAge,0s);pointer-events:none}
.pourRipple{position:absolute;z-index:9;left:15%;width:70%;height:8px;bottom:var(--toLevel);border:2px solid rgba(89,138,159,.6);border-radius:50%;animation:liquidRipple 1s ease-out both;animation-delay:var(--pourAge,0s);pointer-events:none}
@keyframes liquidFill{from{height:var(--fromLevel)}to{height:var(--toLevel)}}
@keyframes liquidStream{0%{opacity:0;transform:scaleX(.6)}12%,72%{opacity:.85}100%{opacity:0;transform:scaleX(.4)}}
@keyframes liquidRipple{0%{opacity:0;transform:scaleX(.4)}30%{opacity:.8}100%{opacity:0;transform:scaleX(1.1)}}
@media(prefers-reduced-motion:reduce){.liq.filling{animation:none}.pourStream,.pourRipple{display:none}}
.solidBed{position:absolute;left:12%;right:12%;bottom:6%;height:26%;z-index:5;pointer-events:none}
.solidChunk{position:absolute;left:var(--l);bottom:var(--b);width:var(--s);height:calc(var(--s)*.62);background:var(--sc);border-radius:35% 45% 38% 48%;transform:rotate(var(--r));box-shadow:inset 2px 2px 3px rgba(255,255,255,.48),0 1px 2px rgba(0,0,0,.16)}
.solidBed.dissolving-solid{animation:solidConsume 2.5s ease-in-out both;animation-delay:var(--solidAge,0s)}
.solidBed.reactive-metal{left:12%;right:12%;height:29%;bottom:6%}
.solidBed.reactive-metal.dissolving-solid{animation:metalConsume 2.8s ease-in-out both;animation-delay:var(--solidAge,0s)}
@keyframes solidConsume{0%{opacity:1;transform:scale(1)}30%{opacity:1;transform:scale(.91)}100%{opacity:0;transform:translateY(8px) scale(.12)}}
.metalPiece.dissolving-metal{animation:metalConsume 2.8s ease-in-out both;animation-delay:var(--solidAge,0s)}
@keyframes metalConsume{0%{opacity:1;transform:scale(1)}35%{opacity:.95;transform:scale(.86)}100%{opacity:0;transform:translateY(7px) scale(.16)}}
@media(prefers-reduced-motion:reduce){.dense-bed{animation:none}.solidBed.dissolving-solid{animation:none;opacity:.25;transform:scale(.35)}}
.metalReactionBed{position:absolute;z-index:5;left:10%;right:10%;bottom:5%;height:30%;pointer-events:none}
.metalPiece{position:absolute;left:12%;right:12%;bottom:5%;height:34%;border-radius:45% 52% 42% 50%;background:var(--metalColor);box-shadow:inset 4px 4px 7px rgba(255,255,255,.34),inset -3px -3px 6px rgba(0,0,0,.16),0 2px 4px rgba(0,0,0,.18)}
.metalCrystal{position:absolute;left:var(--l);bottom:var(--b);width:var(--s);height:var(--s);background:var(--depositColor);border-radius:28% 58% 36% 60%;transform:rotate(var(--r));box-shadow:inset 1px 1px 2px rgba(255,255,255,.65),0 1px 2px rgba(0,0,0,.28);animation:depositGrow .65s ease-out both}
@keyframes depositGrow{from{transform:rotate(var(--r)) scale(.15);opacity:.1}to{transform:rotate(var(--r)) scale(1);opacity:1}}
.surfaceFizz{position:absolute;z-index:7;left:10%;right:10%;bottom:56%;height:16px;pointer-events:none}
.surfaceFizz i{position:absolute;bottom:0;left:var(--l);width:var(--s);height:var(--s);border-radius:50%;border:1.8px solid rgba(255,255,255,.98);background:rgba(255,255,255,.36);box-shadow:0 0 0 1px rgba(70,90,110,.2);animation:pop 1.15s ease-out infinite;animation-delay:var(--delay)}
.gasPlume{position:absolute;z-index:7;left:18%;right:18%;top:8px;height:44%;pointer-events:none;opacity:.72;filter:blur(4px);background:radial-gradient(ellipse at center,var(--gasColor) 0 25%,rgba(255,255,255,0) 70%);animation:plume 1.8s ease-in-out infinite alternate}
@keyframes rise{0%{transform:translateY(0) translateX(0) scale(.72);opacity:.35}10%{opacity:1}75%{transform:translateY(-92px) translateX(var(--drift)) scale(1.08);opacity:1}100%{transform:translateY(-138px) translateX(calc(var(--drift)*.5)) scale(1.18);opacity:.15}}
@keyframes pop{0%{transform:translateY(0) scale(.7);opacity:.2}55%{opacity:1}100%{transform:translateY(-18px) scale(1.3);opacity:0}}
.gasPlume.cl2{left:7%;right:7%;height:64%;filter:blur(3px);animation-name:chlorinePlume}
@keyframes chlorinePlume{from{transform:translateY(1px) scale(.96);opacity:.7}to{transform:translateY(-4px) scale(1.03);opacity:.95}}
#lesson .lesson-tube-frame .bubbleLayer.cl2 .bubble,.bubbleLayer.cl2 .bubble{border-color:rgba(124,149,32,.85);background:rgba(198,216,87,.28);box-shadow:0 0 0 .5px rgba(103,130,24,.4)}
@keyframes plume{from{transform:translateY(2px) scale(.9);opacity:.28}to{transform:translateY(-6px) scale(1.08);opacity:.7}}
.heatShimmer{position:absolute;z-index:6;left:12%;right:12%;top:11%;height:24%;background:repeating-linear-gradient(90deg,transparent 0 7px,rgba(240,0,135,.08) 8px 9px,transparent 10px 15px);filter:blur(3px);animation:shimmer .9s ease-in-out infinite alternate}
@keyframes shimmer{to{transform:translateY(-4px) skewX(-4deg);opacity:.35}}
.reactionGlow{position:absolute;z-index:4;inset:38% 4px 4px;border-radius:10px 10px 24px 24px;box-shadow:inset 0 0 18px rgba(255,255,255,.6);animation:flash 1s ease-out}
@keyframes flash{0%{background:rgba(255,255,255,.8)}100%{background:transparent}}
.tubeLabel{text-align:center;font-weight:700;margin-top:6px}.tubeSmall{text-align:center;font-size:13px;font-weight:600;line-height:1.35;color:#55464b;min-height:30px}
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
.oge23-head-main{display:block;font-size:12px;font-weight:800;line-height:1.25}
.oge23-head-sub{display:block;margin-top:4px;font-size:10px;font-weight:600;text-transform:none;letter-spacing:0;color:#7f7068}
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
 .oge23-head-main{font-size:10.5px;line-height:1.2}.oge23-head-sub{font-size:8.5px}
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
  .lab-topbar{display:flex!important;flex-direction:column!important;align-items:stretch!important}
  .lab-brand{display:none!important}
  .lab-nav{width:100%!important;justify-content:space-between!important}
  .lab-bench{min-height:410px!important}
  .lab-bench.mobile-result-expanded{min-height:500px!important}
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

/* Lesson pilot: two independent working areas, with the live lab catalogue. */
/* Compact comparison bench: calm selection and readable tubes on a phone. */
.tube-slot{background:transparent!important;box-shadow:none!important}
.tube-slot:before{display:none!important}
.tube.on{outline:2px solid rgba(240,0,135,.56);outline-offset:3px}
@media(max-width:820px){
  .lab-bench,.lab-bench.mobile-result-expanded{min-height:590px!important;background:linear-gradient(180deg,#fffdfb 0%,#f8f5f2 100%)!important}
  .rack-wrap{left:12px!important;right:12px!important;bottom:22px!important}
  .rack-board{display:none!important}
  .rack{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:17px 18px!important;align-items:center!important;padding:0 12px!important}
  .tube-slot,.tube-slot.active-slot{display:flex!important;flex-direction:column;align-items:center;width:100%!important;min-width:0!important;min-height:244px!important;padding:10px 5px 7px!important;border:1px solid #f1e6e0;border-radius:16px;background:rgba(255,255,255,.68)!important}
  .tube-slot .tube,.tube-slot.active-slot .tube{width:90px!important;max-width:90%!important;height:172px!important;border-radius:0 0 25px 25px!important}
  .tube-slot .tubeLabel,.tube-slot.active-slot .tubeLabel{margin-top:8px!important;font-size:12px!important}
  .tube-slot .tubeSmall,.tube-slot.active-slot .tubeSmall{font-size:12px!important;font-weight:600!important;line-height:1.3!important;color:#55464b!important;min-height:31px!important}
  .tube-callout .reaction-card{padding:9px 11px!important;box-shadow:0 6px 17px rgba(65,45,37,.13)!important}
  .tube-callout .reaction-sign{font-size:12px!important;margin-bottom:5px!important}
  .tube-callout .reaction-equation{padding:7px!important;font-size:11px!important}
  .tube-callout .reaction-gas{font-size:10px!important}
  .tube-callout .reaction-status{font-size:10px!important;padding:4px 7px!important}
}

/* Lesson pilot: two independent working areas, with the live lab catalogue. */
/* Keep the lesson focused on materials rather than general app navigation. */
body:has(#lesson.page.on) .lab-title-wrap,body:has(#lesson.page.on) .lab-topbar{display:none}
body:has(#lesson.page.on) .tabs{display:flex;gap:5px;justify-content:flex-start;margin-bottom:5px}
body:has(#lesson.page.on) .tabs button:not([data-page="free"]):not([data-page="lesson"]){display:none}
body:has(#lesson.page.on) .tabs button{padding:7px 12px;font-size:12px}
body:has(#lesson.page.on) .lesson-studio{height:calc(100dvh - 66px);min-height:560px}

#lesson.page{min-width:0}
body:has(#lesson.page.on) .app{max-width:none}
.lesson-studio{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,7fr);gap:10px;height:calc(100dvh - 196px);min-height:550px}
#lesson .lesson-studio{grid-template-columns:var(--lesson-lab-width,30%) 7px minmax(0,1fr);gap:0}
#lessonPanelDivider{cursor:col-resize;touch-action:none;background:#f4d9e6;border:0;border-radius:7px;margin:8px 0;position:relative}
#lessonPanelDivider:after{content:"";position:absolute;top:calc(50% - 19px);left:2px;width:3px;height:38px;border-radius:3px;background:#c44988}
#lessonPanelDivider:focus-visible{outline:2px solid #f00087;outline-offset:2px}
.lesson-lab-pane,.lesson-pdf-pane{min-width:0;min-height:0;display:flex;flex-direction:column;background:#fff;border:1px solid #efd9e3;border-radius:15px;overflow:hidden}
.lesson-pane-head{min-height:49px;padding:9px 12px;display:flex;gap:8px;align-items:center;justify-content:space-between;border-bottom:1px solid #f1e5eb}
.lesson-pane-head h2{font-size:15px;margin:0;font-weight:650}
.lesson-pane-head small{color:#82717b;font-size:11px}
.lesson-lab-body{padding:12px;overflow:auto;flex:1;min-height:0}
.lesson-lab-body label{font-size:11px;color:#756774;display:block;margin:8px 0 3px}
.lesson-search-field{position:relative;margin-bottom:5px}
.lesson-search-field input{display:block;width:100%;min-width:0;border:1px solid #dfd2d9;border-radius:10px;padding:10px 9px;background:#fff;color:#171719;font-size:13px}
.lesson-search-field input:focus{outline:2px solid #f5cbdf;border-color:#f00087}
.lesson-search-suggestions{position:absolute;z-index:200;left:0;right:0;top:100%;max-height:170px;overflow:auto;border:1px solid #ebc9d9;border-radius:10px;background:#fff;box-shadow:0 9px 20px #17171922;padding:4px}
.lesson-search-suggestions[hidden]{display:none!important}
.lesson-search-suggestions button{display:block;width:100%;border:0;border-radius:7px;padding:8px 9px;text-align:left;background:#fff;color:#171719;font-size:12px}
.lesson-search-suggestions button:hover,.lesson-search-suggestions button[aria-selected="true"]{background:#fce7f1}
.lesson-search-suggestions button small{display:block;color:#756774;font-size:10px;margin-top:2px}
.lesson-search-empty{font-size:11px;padding:9px;color:#786976}
.lesson-medium-field[hidden]{display:none!important}
.lesson-medium-field{display:grid;gap:5px;padding:8px;border:1px solid #ead0dd;border-radius:10px;background:#fffafd}
.lesson-medium-field small{font-size:11px;line-height:1.35;color:#786674}
.lesson-lab-body select{width:100%;max-width:100%;border:1px solid #dfd2d9;border-radius:10px;padding:10px 7px;background:#fff;color:#171719;font-size:12px}
.lesson-lab-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:11px 0}
.lesson-lab-actions button,.lesson-pane-head button,.lesson-lesson-tools button,.lesson-lesson-tools label{padding:8px 10px;border-radius:11px;font-weight:550}
#lessonConduct{background:#f00087;color:#fff;border:1px solid #f00087}
#lessonHeat[aria-pressed=true]{background:#fff0f8;color:#bc006a;border-color:#f00087}
.lesson-visual{position:relative;background:#f9f6f8;border:1px solid #efdee6;border-radius:15px;min-height:255px;display:flex;flex-direction:column;align-items:center;justify-content:center;margin:8px 0;overflow:hidden}
.lesson-tube-frame{width:130px;height:238px;padding:10px 20px 0}
.lesson-tube-frame .tube{height:206px;width:90px;margin:auto}
.lesson-tube-modes{display:flex;align-items:center;justify-content:center;gap:5px;flex-wrap:wrap;margin:5px 0 0;font-size:11px;color:#796875}
.lesson-tube-modes button{min-width:33px;padding:6px 9px;border-radius:9px;border:1px solid #ead0dd;background:#fff;color:#6e4b5f}
.lesson-tube-modes button[aria-pressed="true"]{background:#f00087;color:#fff;border-color:#f00087}
.lesson-two-tubes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;width:100%;padding:10px}
.lesson-two-tubes[data-count="1"]{grid-template-columns:minmax(0,1fr);max-width:480px;margin:auto}
.lesson-two-tubes[data-count="3"],.lesson-two-tubes[data-count="4"]{grid-template-columns:repeat(2,minmax(0,1fr))}
.lesson-two-tubes[data-count="3"] .lesson-tube-choice,.lesson-two-tubes[data-count="4"] .lesson-tube-choice{gap:2px;padding:5px 2px 3px!important}
.lesson-tube-choice{min-width:0;display:flex;flex-direction:column;align-items:center;gap:4px;padding:7px 2px 4px!important;border:1px solid #e9d7df;border-radius:13px;background:#fffdfd;color:#574351;font-size:11px;font-weight:600;cursor:pointer}
.lesson-tube-choice[hidden]{display:none!important}
.lesson-tube-choice.on{border-color:#f00087;background:#fff3f9;box-shadow:0 0 0 1px rgba(240,0,135,.15)}
.lesson-tube-choice.on>span:first-child{color:#574351!important}
.lesson-tube-choice .lesson-tube-frame{display:block;width:100%;height:auto;padding:5px 0 10px;container-type:inline-size}
.lesson-tube-choice .lesson-tube-frame .tube{
  --tube-width:min(74px,86%);
  width:var(--tube-width);height:auto;aspect-ratio:74 / 175;margin:auto;
}
@supports(width:1cqi){
  .lesson-tube-choice .lesson-tube-frame .tube{--tube-width:min(86cqi,clamp(74px,32cqi,110px))}
  .lesson-two-tubes:is([data-count="3"],[data-count="4"]) .tube{--tube-width:min(86cqi,clamp(60px,30cqi,96px))}
}
.lesson-tube-choice .lesson-tube-frame .tube.on{outline:0}
.lesson-lab-ink{position:absolute;inset:0;width:100%;height:100%;z-index:4;pointer-events:none}
.lesson-lab-ink.drawing{pointer-events:auto;touch-action:none;cursor:var(--lesson-pencil-cursor)}
.lesson-lab-ink.erasing{cursor:cell}
.lesson-ink-tools{display:flex;flex-wrap:wrap;gap:6px;margin:5px 0 8px}
.lesson-ink-tools button{padding:6px 9px;border:1px solid #e6c5d6;border-radius:10px;font-size:11px;font-weight:550;background:#fffafc}
.lesson-ink-tools button[aria-pressed=true]{background:#f4d9e6;border-color:#d78cb2}
.lesson-observation{font-size:12px;line-height:1.45;padding:8px 0}
.lesson-observation .reaction-card{font-size:12px;padding:10px;border-radius:12px;overflow-wrap:anywhere}
.lesson-observation .reaction-equation{font-size:12px;white-space:normal}
.lesson-observation .reaction-gas{font-size:11px}
.lesson-observation .chain-no-reaction{border:1px solid #e7a7c9;border-left:4px solid #f00087;border-radius:12px;background:#fff5fa;padding:12px;color:#442c3c;font-weight:600}
.lesson-footnote{color:#766874;font-size:11px;line-height:1.45}
.lesson-pdf-pane .lesson-pane-head{display:flex;flex-direction:column;align-items:stretch;gap:7px;padding:9px 12px}
.lesson-pdf-pane .lesson-pane-head{position:relative;gap:3px;padding:5px 10px;min-height:42px}
.lesson-lesson-tools{padding-right:125px}
.lesson-lesson-tools button,.lesson-lesson-tools label,.lesson-toolbar-actions button{padding:5px 8px;font-size:12px}
#lessonToolbarToggle{position:absolute;right:9px;top:5px;border:1px solid #e8cddd;border-radius:15px;padding:6px 10px;background:#f8f5f2;color:#171719;font-size:12px}
.lesson-pdf-pane.lesson-toolbar-collapsed .lesson-pane-head{min-height:34px;border-bottom:0}
.lesson-pdf-pane.lesson-toolbar-collapsed .lesson-lesson-tools,.lesson-pdf-pane.lesson-toolbar-collapsed .lesson-toolbar-actions{display:none!important}
.lesson-pdf-pane.lesson-toolbar-collapsed #lessonToolbarToggle{top:3px}
.lesson-lesson-tools{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.lesson-toolbar-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}
.lesson-toolbar-actions button{padding:8px 10px;border-radius:11px;font-weight:550}
.lesson-lesson-tools .lesson-extra-menu{margin-left:4px}
@media(max-width:760px){.lesson-toolbar-actions{justify-content:flex-start}}

.lesson-file-label{display:inline-flex;align-items:center;cursor:pointer;background:#fff}
.lesson-file-controls{display:flex;align-items:center;flex-shrink:0}
.lesson-file-controls .lesson-file-label{border:1px solid #edd2e0;border-radius:10px;padding:8px 11px;color:#392d36}
#lessonPDFInput{display:none}
#lessonExport{background:#f00087;color:#fff;border:1px solid #f00087}
#lessonToolPen[aria-pressed=true],#lessonToolMarker[aria-pressed=true],#lessonToolEraser[aria-pressed=true],#lessonStraightLine[aria-pressed=true]{border-color:#f00087;background:#fff1f8}
.lesson-paper-space{flex:1;min-height:0;overflow:hidden;display:flex;align-items:center;justify-content:center;padding:12px;background:#f7f4f6;position:relative}
#lessonCanvasWrap{position:relative;flex:none;box-shadow:0 4px 23px #21131f26;background:#fff;touch-action:none}
#lessonPdfCanvas,#lessonInkCanvas{display:block}
#lessonInkCanvas{position:absolute;inset:0;touch-action:none;cursor:var(--lesson-pencil-cursor)}
#lessonInkCanvas.eraser{cursor:cell}
.lesson-board-bar{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:7px 10px;background:#fff9fc;border-bottom:1px solid #f1e5eb;font-size:12px}
.lesson-board-bar[hidden],#lessonBoardSpace[hidden],#lessonPaperSpace[hidden]{display:none!important}
.lesson-board-bar button,.lesson-board-bar label{padding:6px 9px;border:1px solid #e8cddd;border-radius:9px;background:#fff;cursor:pointer;font-size:12px}
.lesson-board-bar button[aria-pressed="true"]{border-color:#f00087;background:#fff1f8}
.lesson-board-bar input[type=file]{display:none}
.lesson-board-bar input[type=range]{width:95px;accent-color:#f00087}
.lesson-board-space{flex:1;min-height:0;overflow:hidden;background:#f3eef1;position:relative;overscroll-behavior:contain}
#lessonBoardCanvas{display:block;background-color:#fffdfa;background-image:linear-gradient(#e8dfe575 1px,transparent 1px),linear-gradient(90deg,#e8dfe575 1px,transparent 1px);background-size:26px 26px;touch-action:none;cursor:crosshair}
#lesson #lessonPresentationFullscreen{width:auto!important;flex:none;white-space:nowrap;display:inline-flex;align-items:center;gap:8px;min-height:44px;border:1px solid #eadce5;border-radius:12px;background:#fff;padding:8px 12px;color:#806579;cursor:pointer}#lessonPresentationExit{display:flex;align-items:center;gap:8px;position:fixed;right:12px;top:10px;z-index:100001;background:#fff;min-height:44px;border:1px solid #ecd8e3;border-radius:12px;padding:8px 14px;color:#171719}#lessonPresentationExit[hidden]{display:none!important}
body.lesson-presentation-fullscreen{overflow:hidden!important}
#lesson .lesson-studio.presentation-fullscreen{position:fixed;inset:0;z-index:99990;width:100vw;height:100dvh;min-height:0;display:block;margin:0;padding:0;background:#f8f5f2}
#lesson .lesson-studio.presentation-fullscreen .lesson-lab-pane,#lesson .lesson-studio.presentation-fullscreen #lessonPanelDivider{display:none!important}
#lesson .lesson-studio.presentation-fullscreen .lesson-pdf-pane{height:100%;width:100%;border-radius:0;border:0}
#lesson .lesson-studio.presentation-fullscreen #lessonPresentationFullscreen{visibility:hidden}
#lesson .lesson-studio.presentation-fullscreen .lesson-pane-head{padding-top:60px}
#lesson .lesson-board-active #lessonPresentationFullscreen{display:none}
body.lesson-board-fullscreen{overflow:hidden!important}
#lesson .lesson-studio.board-fullscreen{position:fixed;inset:0;z-index:99990;width:100vw;height:100dvh;min-height:0;display:block;margin:0;padding:0;background:#f8f5f2}
#lesson .lesson-studio.board-fullscreen .lesson-lab-pane,#lesson .lesson-studio.board-fullscreen #lessonPanelDivider{display:none!important}
#lesson .lesson-studio.board-fullscreen .lesson-pdf-pane{height:100%;width:100%;border-radius:0;border:0}
#lesson .lesson-studio.board-fullscreen .lesson-board-space{height:100%;min-height:0}
 .lesson-color-inline{display:inline-flex;align-items:center;gap:5px;font-size:12px}
 .lesson-color-inline input{width:28px;height:26px;padding:0;border:0;background:transparent}
.lesson-color-presets{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;padding:8px 2px}
.lesson-extra-items .lesson-color-presets button{width:28px;height:28px;justify-self:center;padding:0;border-radius:50%;border:1px solid #b5aeb3;background:var(--swatch);cursor:pointer}
.lesson-extra-items .lesson-color-presets button[aria-pressed=true]{outline:2px solid #C44988;outline-offset:2px}
.lesson-pdf-foot{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-top:1px solid #f2e6ec;gap:8px;color:#786e77;font-size:11px}
.lesson-extra-menu{margin-left:auto;position:relative}
.lesson-extra-menu summary{cursor:pointer;background:#fff;border:1px solid #edd2e0;border-radius:10px;padding:8px 11px;list-style:none}
.lesson-extra-menu[open] .lesson-extra-items{position:absolute;top:100%;right:0;background:#fff;z-index:90;width:235px;padding:12px;box-shadow:0 8px 32px #21131f36;border:1px solid #ecdbe3;border-radius:12px;display:grid;gap:9px}
.lesson-extra-items .lesson-width-label{display:grid;gap:8px;padding:6px 1px 9px}
.lesson-extra-items #lessonPenWidth{width:100%;accent-color:#C44988;cursor:pointer}
.lesson-extra-items label{font-size:11px}
.lesson-extra-items button{width:100%}
.lesson-message{color:#806575;font-size:11px;max-width:100%;overflow-wrap:anywhere}
@media(max-width:760px){.lesson-studio{grid-template-columns:minmax(0,1fr);height:auto;min-height:0}.lesson-lab-pane{min-height:465px}.lesson-pdf-pane{min-height:500px}.lesson-pane-head{flex-wrap:wrap}.lesson-paper-space{min-height:350px}}
@media(max-width:760px){#lesson .lesson-studio{grid-template-columns:minmax(0,1fr)}#lessonPanelDivider{display:none}}
/* Floating Markup-style controls: short two-row pill, with an expanded
   palette still accessible for every colour and independent pen/marker ink. */
#lesson .lesson-pdf-pane{position:relative;isolation:isolate}
#lesson .lesson-pdf-pane .lesson-pane-head{position:static;min-height:37px;padding:4px 9px;flex-direction:row;justify-content:flex-end;align-items:center}
#lesson .lesson-lesson-tools{
 position:absolute;z-index:30;top:43px;left:50%;transform:translateX(-50%);
 width:max-content;max-width:calc(100% - 20px);padding:7px 11px 8px;
 display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:5px 7px;
 background:#28282b;color:#fff;border:1px solid #424247;border-radius:25px;
 box-shadow:0 8px 28px #17171935;
}
#lesson .lesson-quick-colors{order:-1;flex:0 0 100%;display:flex;gap:7px;justify-content:center;align-items:center;padding:1px 0 7px;border-bottom:1px solid #ffffff25}
#lesson .lesson-quick-colors button{width:22px;height:22px;min-width:22px;padding:0;border-radius:50%;border:2px solid #28282b;background:var(--swatch);box-shadow:0 0 0 1px #ffffff24;cursor:pointer}
#lesson .lesson-quick-colors button[aria-pressed="true"]{outline:2px solid #f4d9e6;outline-offset:1px;box-shadow:0 0 0 1px #f00087}
#lesson .lesson-lesson-tools>button,#lesson .lesson-lesson-tools .lesson-file-label,#lesson .lesson-extra-menu summary{
 min-width:30px;min-height:30px;padding:5px 7px;border:0;border-radius:17px;
 background:transparent;color:#f8f5f2;line-height:20px;text-align:center;font-weight:500;
}
#lesson .lesson-lesson-tools>button:hover,#lesson .lesson-lesson-tools .lesson-file-label:hover,#lesson .lesson-extra-menu summary:hover{background:#ffffff20}
#lesson .lesson-lesson-tools #lessonToolPen[aria-pressed="true"],
#lesson .lesson-lesson-tools #lessonToolMarker[aria-pressed="true"],
#lesson .lesson-lesson-tools #lessonToolEraser[aria-pressed="true"],
#lesson .lesson-lesson-tools #lessonStraightLine[aria-pressed="true"]{background:#f4d9e6;color:#171719;border:0}
#lesson .lesson-lesson-tools #lessonPageCounter{font-size:11px;white-space:nowrap;min-width:35px;text-align:center;color:#f8f5f2}
#lesson .lesson-lesson-tools .lesson-file-controls .lesson-file-label{display:inline-flex;align-items:center;justify-content:center;font-size:0}
#lesson .lesson-lesson-tools .lesson-file-controls .lesson-file-label:before{content:"▤";font-size:20px}
#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonStraightLine{font-size:0}
#lesson #lessonToolPen:before{content:"✎";font-size:21px}
#lesson #lessonToolMarker:before{content:"▰";font-size:20px}
#lesson #lessonToolEraser{font-size:13px;display:inline-flex;align-items:center;gap:5px;min-height:44px;padding:6px 10px}
.lesson-eraser-icon{width:20px;height:20px;flex-shrink:0;vertical-align:middle}
#lesson #lessonStraightLine:before{content:"╱";font-size:20px}
#lesson .lesson-extra-menu{margin:0}
#lesson .lesson-extra-menu summary{font-size:0;white-space:nowrap}
#lesson .lesson-extra-menu summary:before{content:"＋";font-size:21px}
#lesson .lesson-extra-menu[open] .lesson-extra-items{left:auto;right:0;top:calc(100% + 9px);color:#171719}
#lesson .lesson-toolbar-actions{flex-wrap:nowrap;gap:4px;margin-right:125px}
#lesson .lesson-toolbar-actions button{padding:5px 7px;font-size:11px}
#lesson #lessonToolbarToggle{z-index:31;top:5px;right:8px;border-radius:18px;padding:5px 9px;font-size:11px}
#lesson .lesson-paper-space{padding-top:108px;transition:padding-top .15s ease}
#lesson .lesson-pdf-pane.lesson-toolbar-collapsed .lesson-pane-head{min-height:35px}
#lesson .lesson-pdf-pane.lesson-toolbar-collapsed .lesson-paper-space{padding-top:12px}
@media(max-width:760px){
 #lesson .lesson-lesson-tools{top:44px;gap:3px 5px;padding:7px 6px;max-width:calc(100% - 12px)}
 #lesson .lesson-quick-colors{gap:5px}
 #lesson .lesson-quick-colors button{width:19px;height:19px;min-width:19px}
 #lesson .lesson-toolbar-actions{margin-right:115px}
 #lesson .lesson-toolbar-actions button{font-size:10px;padding:4px 5px}
}
/* EGE BLIZKO lesson-specific pink theme; free laboratory retains autumn theme. */
#lesson{--lesson-pencil-cursor:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M4 20l4.8-1.3L20 7.5 16.5 4 5.3 15.2z' fill='%23F4D9E6' stroke='%23C44988' stroke-width='1.6' stroke-linejoin='round'/%3E%3Cpath d='M4 20l4.8-1.3-3.5-3.5z' fill='%23C44988'/%3E%3Cpath d='M14.6 5.9l3.5 3.5' stroke='%23C44988' stroke-width='1.3'/%3E%3C/svg%3E") 4 20,auto}
#lesson .lesson-tube-frame .tube.on{
 border-color:#D78CB2;
 box-shadow:inset 5px 0 8px rgba(255,255,255,.75),inset -5px 0 7px rgba(109,122,140,.12),0 0 0 2px rgba(215,140,178,.14),0 5px 12px rgba(117,57,88,.10)
}
/* In a classroom's small tubes the gas should rise and escape, not look like
   a heap of white precipitate sitting in the liquid. */
#lesson .lesson-tube-frame .bubbleLayer{height:86%;overflow:visible}
#lesson .lesson-tube-frame .bubble{width:calc(var(--s)*.46);height:calc(var(--s)*.46);border-width:1.1px;background:rgba(255,255,255,.12);box-shadow:0 0 0 .5px rgba(94,130,149,.3);animation-duration:1.6s}
#lesson .lesson-tube-frame .bubble:nth-child(n+11){display:none}
#lesson .lesson-tube-frame .boilLayer{display:none}
#lesson .lesson-tube-frame .bubbleLayer.strong:before{opacity:.15}
#lesson .lesson-tube-frame .surfaceFizz i:nth-child(n+5){display:none}
#lesson .lesson-observation .reaction-card{
 border-color:#E9A9CB;background:linear-gradient(145deg,#FFF9FC,#F4D9E6);
 box-shadow:0 10px 24px rgba(189,62,126,.12)
}
#lesson .lesson-observation .reaction-status{background:#C44988}
#lesson .lesson-observation .reaction-equation{border-color:rgba(196,73,136,.23)}
.indicator-tools{margin:8px 0}.indicator-panel{display:flex;flex-wrap:wrap;gap:6px;margin:7px 0}
.indicator-panel[hidden]{display:none}.indicator-panel button{border:1px solid #e9a9cb;border-radius:9px;background:#fff9fc;color:#171719;padding:7px 10px;cursor:pointer}
.indicator-panel button[aria-pressed="true"]{border-color:#f00087;background:#f4d9e6;font-weight:650}
#indicatorNote,#lessonIndicatorNote{display:block;color:#72556b;line-height:1.4;margin:5px 0}
@media(max-width:760px){#lesson .lesson-tube-frame .tube.on{box-shadow:inset 4px 0 7px rgba(255,255,255,.75),inset -4px 0 6px rgba(109,122,140,.12),0 0 0 2px rgba(215,140,178,.15),0 5px 12px rgba(117,57,88,.10)!important}}

/* Controls occupy layout space so the board remains clickable on tablets. */
#lesson .lesson-pdf-pane .lesson-pane-head{position:relative;flex-direction:column;align-items:stretch;gap:6px;flex-shrink:0;padding:7px 10px}
#lesson #lessonToolbarToggle{position:static;align-self:flex-end;order:0}
#lesson .lesson-lesson-tools{position:relative;top:auto;left:auto;transform:none;order:1;width:100%;max-width:100%;padding:6px;box-sizing:border-box;background:#F8F5F2;color:#171719;border-color:#E8CDDD;border-radius:14px;box-shadow:none}
#lesson .lesson-quick-colors{border-color:#E8CDDD;flex-wrap:wrap}
#lesson .lesson-quick-colors button{border-color:#fff;box-shadow:0 0 0 1px #cdbfc6}
#lesson .lesson-lesson-tools>button,#lesson .lesson-lesson-tools .lesson-file-label,#lesson .lesson-extra-menu summary,#lesson .lesson-lesson-tools #lessonPageCounter{color:#171719}
#lesson .lesson-lesson-tools>button:hover,#lesson .lesson-lesson-tools .lesson-file-label:hover,#lesson .lesson-extra-menu summary:hover{background:#F4D9E6}
#lesson .lesson-toolbar-actions{order:2;flex-wrap:wrap;margin:0;justify-content:flex-end}
#lesson .lesson-paper-space{padding-top:12px}
#lesson .lesson-board-bar{flex-shrink:0}
#lesson .lesson-board-space{min-height:180px}
#lesson .lesson-board-navigation{display:flex;align-items:center;flex-wrap:wrap;gap:5px;padding:5px;border:1px solid #E8CDDD;border-radius:12px;background:#fff}
#lesson .lesson-board-navigation button,#lesson .lesson-board-bar>button{min-height:40px}
#lesson #lessonBoardDocumentName{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
#lesson #lessonBoardPageCounter{min-width:45px;text-align:center;font-variant-numeric:tabular-nums}
#lesson .lesson-board-bar button:disabled{opacity:.4;cursor:default}
#lesson .lesson-board-bar button[aria-pressed="true"]{background:#F4D9E6;border-color:#C44988}
#lesson .lesson-workspace-tabs{display:flex;flex-wrap:wrap;gap:6px;order:0;align-self:flex-start}
#lesson .lesson-workspace-tabs button{display:inline-flex;align-items:center;gap:7px;min-height:44px;padding:8px 13px;border:1px solid #E8CDDD;border-radius:12px;background:#F8F5F2;color:#171719;font-size:14px;font-weight:600}
#lesson .lesson-workspace-tabs svg{width:22px;height:22px;flex-shrink:0}
#lesson .lesson-workspace-tabs button[aria-pressed="true"]{background:#F4D9E6;border-color:#C44988;box-shadow:inset 0 -3px 0 #C44988}
#lesson .lesson-workspace-tabs button:focus-visible{outline:2px solid #F00087;outline-offset:2px}

/* Comfortable pen/touch targets; no pressure threshold is required for ink. */
#lesson button,#lesson .lesson-file-label,#lesson .lesson-board-bar label,#lesson .lesson-extra-menu summary{touch-action:manipulation;-webkit-tap-highlight-color:transparent;user-select:none}
#lesson .lesson-lesson-tools>button,#lesson .lesson-toolbar-actions button,#lesson .lesson-board-bar button,#lesson .lesson-board-bar label,#lesson .lesson-ink-tools button,#lesson .lesson-extra-menu summary{min-width:44px;min-height:44px;box-sizing:border-box}
#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonStraightLine{font-size:13px;display:inline-flex;align-items:center;gap:5px}
#lesson #lessonToolPen:before,#lesson #lessonToolMarker:before,#lesson #lessonStraightLine:before{content:none}
#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonBoardPen,#lesson #lessonBoardMarker{box-shadow:inset 0 -3px 0 var(--tool-ink,#C44988)}
#lesson .lesson-quick-colors{gap:4px;flex-wrap:wrap}
#lesson .lesson-quick-colors button{width:44px;height:44px;min-width:44px;border:10px solid #F8F5F2;background-clip:padding-box;box-sizing:border-box;box-shadow:none}
#lesson .lesson-quick-colors button[aria-pressed="true"]{outline:2px solid #C44988;outline-offset:-4px}
#lesson .lesson-extra-items .lesson-color-presets{grid-template-columns:repeat(5,44px);gap:2px}
#lesson .lesson-extra-items .lesson-color-presets button{width:44px;height:44px;border:9px solid #fff;background-clip:padding-box;box-sizing:border-box}
#lesson .lesson-extra-menu[open] .lesson-extra-items{width:246px;max-height:65dvh;overflow:auto}
#lesson select{min-height:44px}
.heat-hint{padding:10px 12px;margin:7px 0;border:1px solid #E9A9CB;border-radius:12px;background:#FFF1F8;color:#52233D;font-size:13px;line-height:1.5}
.heat-hint[hidden]{display:none}
#heat.heat-required,#lessonHeat.heat-required{border:2px solid #C44988!important;background:#F4D9E6!important;color:#171719;box-shadow:0 0 0 3px #F4D9E660;font-weight:700}

/* Lesson studio: quiet material row, segmented tools, tactile states. */
#lesson{--lesson-control-bg:#fff;--studio-border:#E9E0E5;--studio-muted:#82717C}
#lesson .lesson-pdf-pane .lesson-pane-head{display:flex;flex-direction:row;align-items:center;flex-wrap:wrap;padding:12px 14px;gap:10px;background:#FFFCFD;border-color:var(--studio-border)}
#lesson .lesson-workspace-tabs{margin:0 auto 0 0;align-self:center;background:#F1EBEF;border:1px solid #EAE1E7;padding:4px;gap:3px;border-radius:14px}
#lesson .lesson-workspace-tabs button{border:1px solid transparent;background:transparent;border-radius:10px;min-height:44px;font-size:13px;padding:8px 13px;box-shadow:none;color:#74646F}
#lesson .lesson-workspace-tabs button[aria-pressed="true"]{background:#fff;color:#9D336B;border-color:#E8D8E1;box-shadow:0 2px 5px #3F223A0A}
#lesson #lessonToolbarToggle{order:0;align-self:center;min-height:44px;border:1px solid var(--studio-border);background:#fff;border-radius:11px;padding:7px 11px;font-size:12px;color:#796772}
#lesson .lesson-lesson-tools{flex:1 0 100%;display:flex;flex-direction:column;align-items:stretch;gap:10px;padding:10px;border:1px solid var(--studio-border);border-radius:16px;background:#fff;box-shadow:0 3px 12px #3F223A05}
#lesson .lesson-document-tools{display:flex;align-items:center;flex-wrap:wrap;gap:5px;padding-bottom:9px;border-bottom:1px solid #F0E9ED}
#lesson .lesson-document-tools>button{width:44px;height:44px;border:1px solid #EAE3E8;border-radius:10px;background:#fff;font-size:18px;color:#76606F}
#lesson .lesson-document-tools select{max-width:165px!important;border:1px solid #EAE3E8;border-radius:10px;background:#FAF8FA;padding:6px;font-size:12px}
#lesson .lesson-document-tools #lessonPageCounter{color:#776370;font-size:12px;font-variant-numeric:tabular-nums;min-width:40px;text-align:center}
#lesson .lesson-lesson-tools .lesson-file-controls label.lesson-file-label{display:inline-flex;align-items:center;gap:7px;min-height:44px;font-size:12px;background:#F8F5F7;border:1px solid #EAE3E8;border-radius:10px;padding:8px 11px;cursor:pointer}
#lesson .lesson-lesson-tools .lesson-file-controls .lesson-file-label:before{content:none}
#lesson .lesson-ink-strip{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
#lesson .lesson-primary-ink{display:flex;align-items:center;flex-wrap:wrap;gap:3px;padding:4px;background:#F6F2F5;border-radius:12px}
#lesson .lesson-primary-ink>button,#lesson .lesson-extra-menu summary{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid transparent;border-radius:9px;min-width:44px;min-height:44px;padding:8px 9px;background:transparent;color:#6E5A67;font-size:12px;font-weight:550;line-height:18px}
#lesson .lesson-primary-ink>button[aria-pressed="true"]{color:#9D336B!important;background:#fff!important;border-color:#E8D2DF!important;box-shadow:0 1px 4px #60344912!important}
#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonBoardPen,#lesson #lessonBoardMarker{position:relative;box-shadow:none}
#lesson #lessonToolPen:after,#lesson #lessonToolMarker:after,#lesson #lessonBoardPen:after,#lesson #lessonBoardMarker:after{content:"";position:absolute;left:14px;right:14px;bottom:3px;height:2px;border-radius:2px;background:var(--tool-ink,#C44988)}
#lesson .lesson-control-icon{width:19px;height:19px;flex-shrink:0;vertical-align:middle}
#lesson .lesson-extra-menu{margin-left:auto;position:relative}
#lesson .lesson-extra-menu summary{font-size:12px;background:#FAF7F9;border-color:#EAE2E7;cursor:pointer}
#lesson .lesson-extra-menu summary:before{content:none}
#lesson .lesson-extra-menu[open] summary{background:#F8EAF2;color:#9D336B;border-color:#DBB7CB}
#lesson .lesson-quick-colors{order:0;flex:0 1 auto;justify-content:flex-start;gap:0;border:0;padding:0;margin:0}
#lesson .lesson-quick-colors button{width:44px;height:44px;border:10px solid #fff;box-shadow:none;transition:outline-color .14s ease,background-color .14s ease}
#lesson .lesson-quick-colors button[aria-pressed="true"]{outline:1.5px solid #C44988;outline-offset:-5px}
#lesson .lesson-toolbar-actions{order:2;flex:1 0 100%;margin:0;gap:5px;justify-content:flex-end}
#lesson .lesson-toolbar-actions button{display:inline-flex;align-items:center;gap:6px;min-height:44px;border:1px solid transparent;background:transparent;color:#927784;border-radius:10px;font-size:11px}
#lesson .lesson-toolbar-actions #lessonExport{margin-left:4px;color:#983568;background:#F7E5EF;border:1px solid #EED0E0;font-weight:650;font-size:12px;padding:8px 12px}
#lesson .lesson-board-bar{padding:10px 12px;gap:5px;border-color:var(--studio-border);background:#FFFCFD}
#lesson .lesson-board-bar>button,#lesson .lesson-board-bar>label{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:44px;padding:8px 9px;border-color:#E8DFE5;background:#fff;border-radius:10px;font-size:12px;color:#715E6B}
#lesson .lesson-board-bar>button[aria-pressed="true"]{background:#F8EAF2;color:#963367;border-color:#DDB8CC;box-shadow:0 0 0 2px #F8EAF2}
#lesson .lesson-board-navigation{border-radius:12px;border-color:#EAE1E7;background:#F8F5F7;gap:3px;padding:3px}
#lesson .lesson-board-navigation button{border:0;background:transparent;min-width:44px;min-height:44px;font-size:12px}
#lesson #lessonBoardSaveProject{background:#F7E5EF;color:#983568;border-color:#EED0E0}
#lesson .lesson-board-bar>small{width:100%;color:#9B8793;line-height:1.5;font-size:11px}
#lesson .lesson-pane-head button,#lesson .lesson-board-bar button,#lesson .lesson-lab-actions button,#lesson .lesson-ink-tools button,#lesson .lesson-tube-modes button{transition:background-color .14s ease,border-color .14s ease,box-shadow .14s ease}
#lesson button:not(:disabled):not([data-ink]):hover,#lesson .lesson-file-label:hover,#lesson .lesson-extra-menu summary:hover{background-color:#FAEBF3;box-shadow:0 0 0 2px #F4D9E655}
#lesson button:not(:disabled):not([data-ink]):active{background-color:#F1D8E5;box-shadow:inset 0 1px 3px #8B3E651A}
#lesson button:focus-visible,#lesson summary:focus-visible,#lesson .lesson-file-label:focus-within{outline:2px solid #C44988;outline-offset:3px}
#lesson .lesson-tube-choice>span:first-child{position:relative;z-index:6;min-height:44px;display:flex;align-items:center;justify-content:center;align-self:stretch;background:inherit;border-radius:8px}
#lesson .lesson-board-active .lesson-document-tools{display:none}
@media(max-width:1100px){#lesson #lessonUndo span{display:none}#lesson #lessonUndo{padding:8px;min-width:44px}#lesson .lesson-primary-ink{flex:1 0 100%;justify-content:flex-start}#lesson .lesson-ink-strip{gap:6px}#lesson .lesson-quick-colors{flex:1 1 auto}#lesson .lesson-extra-menu{margin-left:0}}
#lesson .lesson-quick-colors button[data-ink="#ffffff"]{box-shadow:inset 0 0 0 1px #CAB9C5}
@media(max-width:600px){#lesson .lesson-pdf-pane .lesson-pane-head{padding:8px;gap:7px}#lesson .lesson-workspace-tabs button{padding:7px 9px;font-size:12px}#lesson .lesson-primary-ink>button{padding:7px}#lesson .lesson-primary-ink{gap:1px}}
@media(prefers-reduced-motion:reduce){#lesson button{transition:none!important}}


/* Compact presentation controls: release vertical space for the PDF. */
#lesson .lesson-pdf-pane .lesson-pane-head{padding:8px 10px;gap:6px}
#lesson .lesson-workspace-tabs{padding:3px;gap:2px;border-radius:11px}
#lesson .lesson-workspace-tabs button{min-height:32px;padding:5px 9px;font-size:11px;border-radius:8px}
#lesson .lesson-workspace-tabs svg{width:16px;height:16px}
#lesson #lessonToolbarToggle{min-height:32px;padding:4px 8px;font-size:10px;border-radius:8px}
#lesson .lesson-lesson-tools{gap:6px;padding:6px;border-radius:12px}
#lesson .lesson-document-tools{gap:4px;padding-bottom:6px}
#lesson .lesson-document-tools>button{width:32px;height:32px;min-width:32px;min-height:32px;font-size:12px;border-radius:8px;padding:4px 6px}
#lesson .lesson-document-tools #lessonPageCounter{min-width:30px;font-size:10px}
#lesson .lesson-lesson-tools .lesson-file-controls label.lesson-file-label{min-height:32px;padding:5px 8px;font-size:10px;gap:5px;border-radius:8px}
#lesson #lessonPresentationFullscreen{min-width:32px;min-height:32px;padding:4px 8px;font-size:11px}
#lesson .lesson-ink-strip{gap:6px}
#lesson .lesson-primary-ink{padding:3px;gap:2px;border-radius:9px}
#lesson .lesson-primary-ink>button,#lesson .lesson-extra-menu summary{min-width:32px;min-height:32px;padding:4px 6px;font-size:10px;gap:4px;line-height:16px;border-radius:7px}
#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonStraightLine,#lesson #lessonToolEraser{min-height:32px;font-size:10px;padding:4px 6px}
#lesson .lesson-control-icon{width:15px;height:15px}
#lesson .lesson-quick-colors button{width:32px;height:32px;min-width:32px;border-width:7px}
#lesson .lesson-toolbar-actions{gap:4px}
#lesson .lesson-toolbar-actions button{min-width:32px;min-height:32px;padding:4px 6px;font-size:10px;border-radius:8px}
#lesson .lesson-toolbar-actions #lessonExport{font-size:10px;padding:5px 8px}
@media(max-width:1100px){#lesson #lessonUndo{min-width:32px;padding:4px 6px}}
/* One continuous material/ink row; only the controls scroll on narrow panes. */
#lesson .lesson-lesson-tools{flex:1 1 100%;min-width:0;max-width:100%;box-sizing:border-box;flex-direction:row;flex-wrap:nowrap;align-items:center;justify-content:flex-start;gap:8px;overflow-x:auto;overflow-y:visible}
#lesson .lesson-document-tools{flex:none;flex-wrap:nowrap;padding:0 8px 0 0;border-bottom:0;border-right:1px solid #F0E9ED;white-space:nowrap}
#lesson .lesson-ink-strip{flex:1 0 auto;flex-wrap:nowrap;gap:6px}
#lesson .lesson-primary-ink{flex:none;flex-wrap:nowrap}
#lesson .lesson-quick-colors{flex:none;flex-wrap:nowrap}
#lesson .lesson-extra-menu{flex:none;margin-left:auto}
#lesson .lesson-extra-menu[open] .lesson-extra-items{position:fixed;top:var(--lesson-settings-top,120px);right:var(--lesson-settings-right,12px);left:auto;max-height:65dvh;z-index:100010}
#lesson .lesson-studio.presentation-fullscreen #lessonPresentationFullscreen{display:none}
/* Finger controls keep their touch area on actual touch-first devices. */
@media(pointer:coarse){
 #lesson .lesson-workspace-tabs button,#lesson #lessonToolbarToggle,#lesson .lesson-document-tools>button,#lesson #lessonPresentationFullscreen,#lesson .lesson-primary-ink>button,#lesson .lesson-extra-menu summary,#lesson #lessonToolPen,#lesson #lessonToolMarker,#lesson #lessonStraightLine,#lesson #lessonToolEraser,#lesson .lesson-toolbar-actions button,#lesson .lesson-lesson-tools .lesson-file-controls label.lesson-file-label{min-width:44px;min-height:44px}
 #lesson .lesson-quick-colors button{width:44px;height:44px;min-width:44px;border-width:11px}
}


#lesson .lesson-board-active .lesson-primary-ink,#lesson .lesson-board-active .lesson-toolbar-actions{display:none}
#lesson .lesson-board-active .lesson-ink-strip{gap:8px}
#lesson .lesson-board-active .lesson-lesson-tools{padding:7px 10px}
#lesson .lesson-board-more{position:relative;margin-left:auto}
#lesson .lesson-board-more summary{display:flex;align-items:center;justify-content:center;gap:6px;min-height:44px;padding:8px 12px;box-sizing:border-box;border:1px solid #E8DFE5;background:#fff;border-radius:10px;list-style:none;cursor:pointer;color:#715E6B;font-size:12px;font-weight:550}
#lesson .lesson-board-more[open] summary{background:#F8EAF2;border-color:#DDB8CC;color:#963367}
#lesson .lesson-board-more-items{display:none}
#lesson .lesson-board-more[open] .lesson-board-more-items{position:absolute;right:0;top:calc(100% + 8px);z-index:80;display:grid;gap:7px;min-width:250px;width:min(320px,70vw);max-height:min(55dvh,360px);overflow-y:auto;padding:12px;border:1px solid #E8DFE5;border-radius:14px;background:#fff;box-shadow:0 12px 36px #4F244D17}
#lesson .lesson-board-more-items>label,#lesson .lesson-board-more-items>button{display:flex;align-items:center;gap:7px;min-height:44px;padding:8px 10px;font-size:12px;border:1px solid #E8DFE5;border-radius:9px;background:#FAF8FA;box-sizing:border-box}
#lesson .lesson-board-more-items select{width:100%;font-size:12px;border:1px solid #E8DFE5;border-radius:9px}
#lesson .lesson-board-more-items label:has(input[type=range]){display:grid;gap:8px}
#lesson .lesson-board-more-items input[type=range]{width:100%}
#lesson .lesson-board-more-items input[type=file]{display:none}
#lesson .lesson-board-more summary:hover{background:#FAEBF3;box-shadow:0 0 0 2px #F4D9E655}

</style></head><body><div class="app">
<div class="lab-topbar">
  <div class="lab-brand">ЕГЭ БЛИЗКО</div>
  <div class="lab-nav">
    <button id="labBackHistory" type="button">← Назад</button>
    <a href="/lab-solubility">🧪 Таблица растворимости</a>
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
<button data-page="lesson">✍ Урок</button>
</div>

<section id="lesson" class="page">
<div id="lessonPilotBar" class="lesson-pilot-bar" hidden>
 <span><b>Тестовая версия</b> · Доска: локальная копия + «Сохранить проект»</span>
 <span id="lessonBoardSaveState" role="status">Доска: проверяем локальную копию</span>
 <button id="lessonBoardRecover" type="button" hidden>Восстановить доску</button>
 <button id="lessonBoardStartNew" type="button" hidden>Начать без восстановления</button>
 <span id="lessonPilotSaveState" role="status">Пометки PDF: только в этом браузере</span>
 <button id="lessonPilotHelp" type="button">Как начать</button>
 <button id="lessonPilotReport" type="button">Сообщить о проблеме</button>
</div>
<dialog id="lessonPilotDialog" class="lesson-pilot-dialog" aria-labelledby="lessonPilotTitle">
 <h2 id="lessonPilotTitle">Перед первым уроком</h2>
 <div id="lessonPilotGuide">
  <p>Откройте PDF во вкладке «Презентация». Стрелки перелистывают слайды, «На весь экран» увеличивает рабочую область. Esc возвращает обычный вид.</p>
  <p>Выберите ручку, маркер или ластик. Цвет и толщина ручки и маркера запоминаются отдельно. В «Настройках» можно включить «Красивое письмо».</p>
  <p>Во вкладке «Доска» можно размещать изображения и PDF. Для перемещения выберите руку; масштаб меняется кнопками или жестом на трекпаде.</p>
  <p><b>Перед закрытием:</b> скачайте «Сохранить проект» для редактируемой доски и «Сохранить PDF» для презентации с пометками. Оригинальный PDF нужно хранить отдельно. Локальные пометки не являются облачной копией и могут исчезнуть при очистке браузера. Доска автоматически сохраняется локально: после повторного открытия нажмите «Восстановить доску». Дождитесь статуса сохранения перед закрытием. Локальная копия не заменяет скачанный проект.</p>
  <p>В лаборатории выберите реагенты и нажмите «Провести». Если нужен нагрев, появится подсказка. Отсутствие пары в базе не означает, что реакция химически невозможна.</p>
 </div>
 <div id="lessonPilotFeedback" hidden>
  <p>Опишите: что нажали → что ожидали → что получилось.</p>
  <label for="lessonPilotMessage">Описание проблемы</label>
  <textarea id="lessonPilotMessage" rows="5" maxlength="4000" placeholder="Например: после перехода на следующий слайд…"></textarea>
  <p>Кнопка скачает файл для передачи Марии. В нём будут ваше описание, сборка, браузер, размер окна, реагенты и условия. PDF, изображения и рукописные записи не включаются. Автоматической отправки нет.</p>
  <a id="lessonPilotTelegram" href="https://t.me/masedova" target="_blank" rel="noopener noreferrer" style="display:inline-block;padding:10px 14px;margin:0 8px 8px 0;border-radius:10px;background:#f00087;color:#fff;text-decoration:none;font-weight:600">Написать Марии в Telegram</a>
  <button id="lessonPilotDownload" type="button">Скачать сообщение</button>
  <p>Скачанный файл можно прикрепить в чате Telegram. Сообщение и файл автоматически не отправляются.</p>
 </div>
 <button id="lessonPilotClose" type="button">Закрыть</button>
</dialog>
<div class="lesson-studio" aria-label="Урок с интерактивной лабораторией">
<button id="lessonPresentationExit" type="button" hidden><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3H3v6M15 3h6v6M3 15v6h6M21 15v6h-6"/></svg><span>Вернуть лабораторию</span></button>
  <aside class="lesson-lab-pane">
    <div class="lesson-pane-head"><h2>🧪 Опыт</h2><small>30% экрана</small></div>
    <div class="lesson-lab-body">
      <div class="lesson-search-field">
        <label for="lessonReagentA">Первое вещество</label>
        <input id="lessonReagentA" type="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lessonSuggestionsA" placeholder="KMnO4 или перманганат калия" autocomplete="off" autocapitalize="off" spellcheck="false">
        <div id="lessonSuggestionsA" class="lesson-search-suggestions" role="listbox" hidden></div>
      </div>
      <div class="lesson-search-field">
        <label for="lessonReagentB">Добавить реактив</label>
        <input id="lessonReagentB" type="search" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lessonSuggestionsB" placeholder="K2Cr2O7, KI или название" autocomplete="off" autocapitalize="off" spellcheck="false">
        <div id="lessonSuggestionsB" class="lesson-search-suggestions" role="listbox" hidden></div>
      </div>
      <div id="lessonMediumField" class="lesson-medium-field" hidden>
        <label for="lessonMedium">Среда реакции</label>
        <select id="lessonMedium">
          <option value="">Выбери среду...</option>
          <option value="acid">Кислая</option>
          <option value="neutral">Нейтральная</option>
          <option value="weak_alkaline">Слабощелочная</option>
          <option value="alkaline">Сильнощелочная</option>
        </select>
        <small id="lessonMediumHint">Продукты ОВР зависят от среды.</small>
      </div>
      <div class="lesson-lab-actions">
        <button id="lessonConduct" type="button">▶ Провести</button>
         <button id="lessonExcess" type="button" aria-pressed="false">＋ Избыток щёлочи</button>
        <button id="lessonHeat" type="button" aria-pressed="false">🔥 Нагрев</button>
        <button id="lessonReset" type="button" title="Очистить только выбранную пробирку">↺ Очистить пробирку</button>
      </div>
      <div id="lessonHeatHint" class="heat-hint" role="status" hidden></div>
      <div class="indicator-tools"><button type="button" id="lessonIndicatorToggle" aria-expanded="false">🧪 Индикаторы</button><div id="lessonIndicatorPanel" class="indicator-panel" hidden></div><small id="lessonIndicatorNote"></small></div>
      <div class="lesson-tube-modes" aria-label="Количество пробирок">Пробирок:
        <button type="button" data-lesson-count="1" aria-pressed="false">1</button>
        <button type="button" data-lesson-count="2" aria-pressed="true">2</button>
        <button type="button" data-lesson-count="3" aria-pressed="false">3</button>
        <button type="button" data-lesson-count="4" aria-pressed="false">4</button>
      </div>
      <div class="lesson-visual" aria-label="Независимые пробирки для опытов">
        <div class="lesson-two-tubes" id="lessonTubeGrid" data-count="2">
          <button type="button" class="lesson-tube-choice on" data-lesson-tube="0" aria-pressed="true"><span>Пробирка 1</span><span id="lessonTube1" class="lesson-tube-frame"></span></button>
          <button type="button" class="lesson-tube-choice" data-lesson-tube="1" aria-pressed="false"><span>Пробирка 2</span><span id="lessonTube2" class="lesson-tube-frame"></span></button>
          <button type="button" class="lesson-tube-choice" data-lesson-tube="2" aria-pressed="false" hidden><span>Пробирка 3</span><span id="lessonTube3" class="lesson-tube-frame"></span></button>
          <button type="button" class="lesson-tube-choice" data-lesson-tube="3" aria-pressed="false" hidden><span>Пробирка 4</span><span id="lessonTube4" class="lesson-tube-frame"></span></button>
        </div>
        <canvas id="lessonLabInk" class="lesson-lab-ink" aria-label="Рукописные пометки рядом с пробиркой"></canvas>
      </div>
      <div class="lesson-ink-tools" aria-label="Пометки на лабораторном опыте">
        <button id="lessonLabPen" type="button" aria-pressed="false">✎ Писать у пробирки</button>
        <button id="lessonLabEraser" type="button" aria-pressed="false">⌫ Ластик</button>
        <button id="lessonLabView" type="button" aria-pressed="true">✓ Готово</button>
        <button id="lessonLabClear" type="button">Очистить записи</button>
      </div>
      <div id="lessonReaction" class="lesson-observation" aria-live="polite">Выбери два вещества и нажми «Провести». PDF останется открытым справа.</div>
      <div id="lessonChainHistory" class="lesson-observation" hidden></div>
      <div class="lesson-footnote">Опыты и признаки берутся из действующей химической базы. Если реакции в ней пока нет, результат не выдумываем.</div>
    </div>
  </aside>
  <div id="lessonPanelDivider" role="separator" tabindex="0" aria-label="Изменить ширину лаборатории и презентации" aria-orientation="vertical" aria-valuemin="20" aria-valuemax="65" aria-valuenow="30"></div>
  <section class="lesson-pdf-pane" aria-label="Рабочая тетрадь преподавателя">
    <div class="lesson-pane-head">
      <div class="lesson-workspace-tabs" role="group" aria-label="Рабочая область урока">
        <button id="lessonPresentationTab" type="button" aria-pressed="true" title="Открыть презентацию PDF и записи на слайдах"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="3" width="18" height="13" rx="2"/><path d="M12 16v5m-5 0h10M7 7h10M7 11h6"/></svg> Презентация</button>
        <button id="lessonBoardToggle" type="button" aria-pressed="false" title="Открыть бесконечную доску"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/></svg> Доска</button>
      </div>
      <button id="lessonToolbarToggle" type="button" aria-expanded="true" title="Свернуть или открыть инструменты">Скрыть инструменты</button>
      <div class="lesson-lesson-tools">
      <div class="lesson-document-tools" role="group" aria-label="Презентация и страницы">
      <div class="lesson-file-controls">
        <label for="lessonPDFInput" class="lesson-file-label" title="Открыть свой PDF"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H5v18h14V8l-5-5ZM14 3v5h5M8 12h8M8 16h6"/></svg><span>Открыть PDF</span></label>
        <input id="lessonPDFInput" type="file" accept="application/pdf,.pdf">
      </div>
        
        <button id="lessonPrevious" type="button" title="Предыдущая страница"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>
        <span id="lessonPageCounter">1 / 1</span>
        <button id="lessonNext" type="button" title="Следующая страница"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button>
      <button id="lessonPresentationFullscreen" type="button" aria-label="Презентация на весь экран" aria-pressed="false" title="Скрыть пробирки и развернуть презентацию; выход — Esc"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3H3v6M15 3h6v6M3 15v6h6M21 15v6h-6"/></svg><span>На весь экран</span></button>
      </div>
      <div class="lesson-ink-strip">
      <div class="lesson-primary-ink" role="group" aria-label="Инструмент письма">
        
        <button id="lessonToolPen" type="button" aria-pressed="true"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 20 4.5-1L20 7.5 16.5 4 5 15.5 4 20Zm10-13 3.5 3.5M5 15.5 8.5 19"/></svg><span>Ручка</span></button>
         <button id="lessonToolMarker" type="button" aria-pressed="false"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 14 8-10 7 6-8 9-7-5Zm3 3-4 3h7M10 8l7 6"/></svg><span>Маркер</span></button>
        <button id="lessonStraightLine" type="button" aria-pressed="false" title="Прямая линия выбранной ручкой или выделителем"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 19 14-14"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/></svg><span>Линия</span></button>
        <button id="lessonToolEraser" type="button" aria-label="Ластик" title="Ластик — стереть штрих" aria-pressed="false"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 14 9-10a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3L12 22H8l-4-4a3 3 0 0 1 0-4Zm5-5 8 8M12 22h10"/></svg><span>Ластик</span></button>
      <button type="button" id="lessonUndo" title="Отменить последний штрих"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6-5 5 5 5M4 11h10a6 6 0 0 1 6 6"/></svg><span>Отменить</span></button>
      </div>
      <div id="lessonQuickColors" class="lesson-quick-colors" role="group" aria-label="Быстрый выбор цвета ручки или выделителя"></div>
      <details class="lesson-extra-menu">
        <summary aria-label="Цвет, толщина и настройки письма"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="var(--lesson-control-bg,#fff)"/><circle cx="15" cy="17" r="3" fill="var(--lesson-control-bg,#fff)"/></svg><span>Настройки</span></summary>
        <div class="lesson-extra-items">
          <b style="font-size:12px;font-weight:600">Цвета</b>
          <input id="lessonPenColor" type="color" value="#f00087" hidden>
          <div class="lesson-color-presets" id="lessonColorPresets" aria-label="Цвета ручки"></div>
          <label class="lesson-width-label">Толщина <input id="lessonPenWidth" type="range" min="1" max="10" value="3"></label>
          
          <label class="lesson-width-label" title="Стабилизировать ручку во время письма и сглаживать штрих после отрыва пера; без замены букв и формул"><input id="lessonBeautify" type="checkbox" checked> Красивое письмо</label>
          <small>Для новых штрихов ручки · без замены букв</small>
          <button type="button" id="lessonExportNotes">↓ Резервная копия записей</button>
          <label for="lessonImportNotes" class="lesson-file-label">↑ Загрузить записи</label>
          <input id="lessonImportNotes" type="file" accept=".json,application/json" style="display:none">
        </div>
      </details>
      </div>
      </div>
      <div class="lesson-toolbar-actions">
        <button id="lessonClearPage" type="button" title="Удалить пометки только с текущего слайда"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/></svg><span>Очистить страницу</span></button>
        <button id="lessonClearAll" type="button" title="Удалить пометки со всех слайдов после подтверждения"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/></svg><span>Очистить всё</span></button>
        <button id="lessonExport" type="button"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></svg><span>Сохранить PDF</span></button>

      </div>
    </div>
    <div id="lessonBoardBar" class="lesson-board-bar" hidden>
      <button id="lessonBoardPen" type="button" aria-pressed="true"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 20 4.5-1L20 7.5 16.5 4 5 15.5 4 20Zm10-13 3.5 3.5M5 15.5 8.5 19"/></svg><span>Ручка</span></button>
      <button id="lessonBoardMarker" type="button" aria-pressed="false"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 14 8-10 7 6-8 9-7-5Zm3 3-4 3h7M10 8l7 6"/></svg><span>Маркер</span></button>
      <button id="lessonBoardEraser" type="button" aria-pressed="false" title="Стереть штрих на доске"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 14 9-10a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3L12 22H8l-4-4a3 3 0 0 1 0-4Zm5-5 8 8M12 22h10"/></svg><span>Ластик</span></button>
      <button id="lessonBoardLine" type="button" aria-pressed="false" title="Прямая линия"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="m5 19 14-14"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/></svg><span>Линия</span></button>
      <button id="lessonBoardPan" type="button" aria-pressed="false"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 12V6a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v8-6a2 2 0 0 1 4 0v10c0 4-3 6-7 6h-1c-2 0-3-1-4-3l-4-6c-1-2 1-4 3-2l1 1Z"/></svg><span>Двигать доску</span></button>
      <div class="lesson-board-navigation" role="group" aria-label="Масштаб и обзор доски">
        <button id="lessonBoardZoomOut" type="button" aria-label="Уменьшить масштаб доски"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/></svg></button>
        <button id="lessonBoardZoom" type="button" title="Вернуть масштаб 100%">100%</button>
        <button id="lessonBoardZoomIn" type="button" aria-label="Увеличить масштаб доски"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
        <button id="lessonBoardFit" type="button">Показать всё</button>
        <button id="lessonBoardDocument" type="button">К документу</button>
        <button id="lessonBoardHome" type="button" title="Вернуться к началу координат"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7"/></svg></button>
      </div>
      <div class="lesson-board-navigation" role="group" aria-label="Страницы PDF на доске">
        <span id="lessonBoardDocumentName"></span>
        <button id="lessonBoardPrevious" type="button" aria-label="Предыдущая страница на доске"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>
        <span id="lessonBoardPageCounter" aria-live="polite">1 / 1</span>
        <button id="lessonBoardNext" type="button" aria-label="Следующая страница на доске"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button>
      </div>
      <button id="lessonBoardMove" type="button" aria-pressed="false"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v18M3 12h18M8 7l4-4 4 4M8 17l4 4 4-4M7 8l-4 4 4 4M17 8l4 4-4 4"/></svg><span>Выбрать объект</span></button>
      <button id="lessonBoardUndo" type="button"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6-5 5 5 5M4 11h10a6 6 0 0 1 6 6"/></svg><span>Отменить</span></button>
      <button id="lessonBoardFullscreen" type="button" aria-pressed="false" title="Развернуть доску на весь экран или вернуться к лаборатории">⛶ На весь экран</button>
      <button id="lessonBoardSaveProject" type="button"><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></svg><span>Сохранить проект</span></button>
      <details id="lessonBoardMore" class="lesson-board-more">
        <summary><svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span>Материалы</span></summary>
        <div class="lesson-board-more-items">      <select id="lessonBoardPages" aria-label="Лист доски" title="Выбрать лист доски"></select>
      <button id="lessonBoardAddPage" type="button">＋ Лист</button>
      <button id="lessonBoardRenamePage" type="button">Переименовать</button>
      <label for="lessonBoardImageInput">＋ Изображение</label><input id="lessonBoardImageInput" type="file" accept="image/png,image/jpeg,image/webp">
      <label for="lessonBoardPDFInput">＋ PDF на доску</label><input id="lessonBoardPDFInput" type="file" accept="application/pdf,.pdf">
      <label title="Меняет размер выбранной картинки. Для увеличения PDF используй кнопки масштаба.">Размер картинки <input id="lessonBoardImageSize" type="range" min="100" max="1300" value="480" aria-label="Ширина выбранного изображения"></label>
      <label for="lessonBoardOpenProject">↑ Открыть проект</label><input id="lessonBoardOpenProject" type="file" accept=".json,application/json">
      <button id="lessonBoardExport" type="button">↓ Доска в PDF</button>
</div>
      </details>
      <small>Масштаб: + / − или два пальца. Один палец пишет; «Перемещать доску» двигает обзор. PDF листается стрелками и закреплён под записями.</small>
    </div>
    <div id="lessonPaperSpace" class="lesson-paper-space">
      <div id="lessonCanvasWrap"><canvas id="lessonPdfCanvas"></canvas><canvas id="lessonInkCanvas" aria-label="Писать стилусом по странице"></canvas></div>
    </div>
    <div id="lessonBoardSpace" class="lesson-board-space" hidden><canvas id="lessonBoardCanvas" width="2400" height="1600" aria-label="Свободная доска для записи и изображений"></canvas></div>
    <div class="lesson-pdf-foot">
      <span id="lessonFileName">Загрузи свой PDF или пиши на пустой доске.</span>
      <span id="lessonStatus" class="lesson-message" role="status">Пометки сохраняются только в браузере до выгрузки PDF.</span>
    </div>
  </section>
</div>
</section>

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
    <div class="selected-card"><b>Выбрана пробирка <span id="selectedTubeLabel">1</span></b><span>Добавляй реактивы последовательно; при необходимости выбери избыток.</span></div>
    <div id="tubeMediumField" class="lesson-medium-field" hidden>
      <label for="tubeMedium">Среда реакции</label>
      <select id="tubeMedium">
        <option value="">Выбери среду...</option>
        <option value="acid">Кислая</option>
        <option value="neutral">Нейтральная</option>
        <option value="weak_alkaline">Слабощелочная</option>
        <option value="alkaline">Сильнощелочная</option>
      </select>
      <small>Для некоторых ОВР результат определяется средой и дополнительными реагентами из уравнения.</small>
    </div>
    <div class="control-stack">
      <button id="indicatorToggle" type="button" aria-expanded="false">🧪 Индикаторы</button>
      <div id="indicatorPanel" class="indicator-panel" hidden></div>
      <small id="indicatorNote"></small>
      <button id="excess">➕ Последний реактив в избытке</button>
      <button id="heat" aria-pressed="false">🔥 Нагрев</button>
      <div id="heatHint" class="heat-hint" role="status" hidden></div>
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
let tubes=[[],[],[],[]], tubeHeat=[false,false,false,false], tubeExcess=["","","",""], tubeDissolving=[false,false,false,false], tubeMedium=["","","",""], tubeIndicators=["","","",""], unknownOrder=[], unknownSelected=0, toolSelected="", attempts=0, exam=null, locked=false;
const INDICATORS=Object.freeze({litmus:{name:"Лакмус",acid:"#e64b64",neutral:"#8152a9",alkaline:"#3866ce"},methylorange:{name:"Метилоранж",acid:"#dc3b37",neutral:"#f4c83f",alkaline:"#f4c83f"},phenolphthalein:{name:"Фенолфталеин",acid:"#f8fbff",neutral:"#f8fbff",alkaline:"#ed3d98"}});
const INDICATOR_ACIDS=new Set(["hcl","h2so4","hno3","hbr","hi","hf"]);
const INDICATOR_ALKALIS=new Set(["naoh","koh","lioh","baoh2","caoh2"]);
function indicatorMedium(ids,explicit=""){
 if(explicit==="acid")return "acid";
 if(explicit==="alkaline"||explicit==="weak_alkaline")return "alkaline";
 if(explicit==="neutral")return "neutral";
 // With two or more reagents the current engine does not track quantities/pH.
 // Never invent a pH from an equation or the last reagent added.
 if(ids.length!==1)return "";
 if(INDICATOR_ACIDS.has(ids[0]))return "acid";
 if(INDICATOR_ALKALIS.has(ids[0]))return "alkaline";
 return "";
}
function indicatorPanelHTML(selected){
 return Object.entries(INDICATORS).map(([id,v])=>'<button type="button" data-indicator="'+id+'" aria-pressed="'+(selected===id)+'">'+v.name+'</button>').join("");
}
function indicatorNoteText(indicator,ids,medium){
 if(!indicator)return "";
 if(!ids.length)return "Сначала добавь раствор в пробирку.";
 return medium?INDICATORS[indicator].name+": "+({acid:"кислая",neutral:"нейтральная",alkaline:"щелочная"}[medium])+" среда.":
  "Индикатор добавлен. pH этой смеси пока не рассчитывается: окраску не предсказываем.";
}
// Chain mode keeps the products actually available after each transformation.
// Each tube has independent history and never guesses a reaction not in the catalogue.
let tubeChain=[null,null,null,null];
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
function chainProductDetails(rx){
 const equation=String(rx&&rx.eq||"");
 const rhs=equation.split(/→|⇄|⟶/).pop()||"";
 if(!rhs||rhs===equation)return {ids:[],untracked:[]};
 const compact=s=>normalizeReagentSearch(s).replace(/[↓↑]/g,"");
 const ids=[],untracked=[];
 rhs.split(/\s+\+\s+/).forEach(piece=>{
  // Gas leaves an open tube and cannot be reused in this qualitative chain.
  if(/↑|\(g\)/i.test(piece))return;
  const formula=piece.replace(/^\s*\d+\s*/,"").replace(/[↓↑]/g,"").replace(/\s*\((?:aq|s|l|g)\)\s*$/i,"").trim();
  const normalized=compact(formula);
  const found=[...reagentMap.entries()].find(([,r])=>compact(r[0])===normalized);
  if(found&&!/газ/i.test(String(found[1][3]||""))){
   if(!ids.includes(found[0]))ids.push(found[0]);
  }else if(formula&&!untracked.includes(formula)){
   untracked.push(formula);
  }
 });
 return {ids,untracked};
}
function chainProductIds(rx){return chainProductDetails(rx).ids}
function chainUntrackedNotice(step){
 return step.untracked&&step.untracked.length?
  '<div class="chain-no-reaction">Некоторые продукты этого этапа пока нельзя использовать в следующей реакции: '+step.untracked.map(task6Esc).join(", ")+'.</div>':'';
}
function chainStepLabel(count){
 const lastTwo=count%100,last=count%10;
 return count+" "+(lastTwo>=11&&lastTwo<=14?"этапов":last===1?"этап":last>=2&&last<=4?"этапа":"этапов");
}
function chainAvailable(i){
 const chain=tubeChain[i];
 return chain?chain.available.slice():tubes[i].slice();
}
function chainCandidates(i,newId){
 return chainAvailable(i).filter(id=>id!==newId&&!tubeHasMedium([id,newId]))
  .map(id=>({id,rx:findReaction(id,newId,tubeHeat[i])}))
  .filter(item=>item.rx&&item.rx.t!=="z"&&(!item.rx.heat||tubeHeat[i]));
}
function chainCompleteStep(i,newId,selected){
 const chain=tubeChain[i];
 const candidate=chainCandidates(i,newId).find(item=>item.id===selected);
 if(!candidate)return false;
 const details=chainProductDetails(candidate.rx),products=details.ids;
 // Never invent an unavailable product as a future reagent.
 if(!products.length)return false;
 const next=chain.available.filter(id=>id!==selected&&id!==newId);
 chain.available=[...new Set([...next,...products])];
 chain.steps.push({reagent:newId,reactant:selected,reaction:candidate.rx,available:chain.available.slice(),untracked:details.untracked});
 tubes[i].push(newId);
 document.getElementById("result").textContent="Этап "+chain.steps.length+" проведён. Можно долить следующий реактив.";
 renderTubes();
 return true;
}
// Unified source of gas colours and smells. All gases in the laboratory catalogue
// must have an entry here; tests enforce coverage when reactions are added.
const GAS_REFERENCE=Object.freeze({
 "H₂":{color:"бесцветный",smell:"без запаха",plume:"rgba(255,255,255,.18)"},
 "CO₂":{color:"бесцветный",smell:"без запаха",plume:"rgba(255,255,255,.18)"},
 "NO":{color:"бесцветный",smell:"без запаха",plume:"rgba(255,255,255,.18)",note:"На воздухе окисляется до бурого NO₂."},
 "NO₂":{color:"бурый",smell:"резкий раздражающий",plume:"rgba(196,88,22,.90)"},
 "SO₂":{color:"бесцветный",smell:"резкий удушливый",plume:"rgba(255,255,255,.18)"},
 "H₂S":{color:"бесцветный",smell:"тухлых яиц",plume:"rgba(255,255,255,.18)"},
 "NH₃":{color:"бесцветный",smell:"резкий характерный",plume:"rgba(255,255,255,.18)"},
 "Cl₂":{color:"жёлто-зелёный",smell:"резкий удушливый",plume:"rgba(166,191,40,.82)"}
});
function gasObservationHTML(x){
 if(!x||!x.gas)return "";
 const info=GAS_REFERENCE[x.gas];
 if(!info)return '<div class="reaction-gas"><b>Газ '+x.gas+':</b> свойства требуют проверки.</div>';
 const note=info.note?' '+info.note:'';
 return '<div class="reaction-gas"><b>Газ '+x.gas+':</b> цвет — '+info.color+'; запах — '+info.smell+'.'+note+'<span class="gas-safety">Запах указан справочно. Не вдыхайте выделяющиеся газы.</span></div>';
}
function redoxRolesHTML(x){
 if(!x?.oxidizer||!x.reducer)return "";
 const balance=(x.electron_balance||[]).map(line=>'<div>'+task6Esc(line)+'</div>').join("");
 return '<div class="reaction-note reaction-redox"><b>Окислитель:</b> '+task6Esc(x.oxidizer)+'<br><b>Восстановитель:</b> '+task6Esc(x.reducer)+'<details><summary>Электронный баланс</summary>'+balance+'</details></div>';
}
function syncHeatHint(buttonId,hintId,reaction,heated,manualStart=false){
 const button=document.getElementById(buttonId),hint=document.getElementById(hintId);
 const needed=!!(reaction&&reaction.t!=="z"&&reaction.heat&&!heated);
 button.classList.toggle("heat-required",needed);button.setAttribute("aria-pressed",String(!!heated));
 button.textContent=needed?"🔥 Нагрев — нужен":heated?"🔥 Нагрев включён":"🔥 Нагрев";
 if(needed){
  button.setAttribute("aria-describedby",hintId);
  const text="Эта реакция есть в базе — нужен нагрев. Нажми кнопку «🔥 Нагрев»."+(manualStart?" Если опыт ещё не запущен, затем нажми «Провести».":"");
  const message=text+(reaction.condition?" Условия: "+reaction.condition+".":"");
  if(hint.textContent!==message)hint.textContent=message;
 }else{button.removeAttribute("aria-describedby");if(hint.textContent)hint.textContent="";}
 hint.hidden=!needed;
}
function reactionResultHTML(x,heated=false){
 if(!x)return '<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">Нет данных</span></div><div class="reaction-sign">Этот опыт пока не добавлен в базу.</div></div>';
 if(x.heat&&!heated)return '<div class="reaction-card"><div class="reaction-head"><span class="reaction-status">🔥 Нужен нагрев</span></div><div class="reaction-sign">Реакция есть в базе. Нажми кнопку «🔥 Нагрев», чтобы провести её в нужных условиях.</div><div class="reaction-equation">'+x.eq+'</div>'+(x.condition?'<div class="reaction-note">Условие: '+task6Esc(x.condition)+'</div>':'')+redoxRolesHTML(x)+'</div>';
 const noVisible=x.t==="n"&&!oxideHydration(x), noReaction=x.t==="z";
 const icon=x.t==="p"?"⬇️":x.t==="g"?"🫧":x.t==="c"?"🎨":x.t==="x"?"✨":noReaction?"⛔":"✓";
 const title=noReaction?"Реакция не идёт":"Реакция протекает";
 let sign=noReaction?x.sign:(noVisible?"Без видимого признака":x.sign);
 if(oxideSulfateTurbidity(x))sign="Твёрдый CaO расходуется; раствор мутнеет из-за образования малорастворимого CaSO₄";
 if(oxideHydration(x)==="clear")sign="Растворение твёрдого основного оксида с образованием щёлочи";
 if(oxideHydration(x)==="cloudy")sign="Твёрдый CaO расходуется; образуется малорастворимый Ca(OH)₂, смесь мутнеет";
 // One reaction can have two simultaneous observable signs. Do not create
 // a duplicate equation merely because two sources describe different signs.
 if(!noReaction&&/MgCO₃\s*\+\s*H₂SO₄/.test(String(x.eq||""))&&x.gas==="CO₂"&&!/раствор|исчеза/.test(String(sign).toLowerCase())){
  sign=String(sign||"Выделение CO₂")+"; постепенное исчезновение твёрдого MgCO₃";
 }
 const condition=x.condition?'<div class="reaction-note">Условие: '+x.condition+'</div>':'';
 const stages=x.stages?'<div class="reaction-note"><b>1. Осадок</b><div class="reaction-equation">'+x.stages.first+'</div><b>2. Растворение в избытке</b><div class="reaction-equation">'+x.stages.second+'</div><b>Суммарно</b></div>':'';
 const note=noReaction?'<div class="reaction-note">Смесь остаётся без химического превращения в указанных условиях.</div>':(noVisible?'<div class="reaction-note">Реакция есть, но визуального эффекта в пробирке нет.</div>':'');
 return '<div class="reaction-card '+((noVisible||noReaction)?'no-visible':'')+'"><div class="reaction-head"><span class="reaction-status">'+icon+' '+title+'</span></div><div class="reaction-sign">'+(noReaction?'Почему: ':'Признак: ')+sign+'</div>'+stages+'<div class="reaction-equation">'+x.eq+'</div>'+condition+redoxRolesHTML(x)+gasObservationHTML(x)+note+'</div>';
}
// CaO is consumed by sulfuric acid while fine CaSO4 creates a cloudy
// suspension. Avoid rendering a pile of macroscopic white precipitate.
function oxideSulfateTurbidity(x){
 const eq=String(x&&x.eq||"").replace(/\s+/g,"");
 const sides=eq.split(/→|⟶/);
 return sides.length===2&&sides[0].includes("CaO")&&sides[0].includes("H₂SO₄")&&sides[1].includes("CaSO₄");
}
function oxideHydration(x){
 const eq=String(x&&x.eq||"").replace(/\s+/g,"");
 const sides=eq.split(/→|⟶/);
 if(sides.length!==2||!sides[0].includes("H₂O"))return "";
 if(sides[0].includes("Na₂O")&&sides[1].includes("NaOH"))return "clear";
 if(sides[0].includes("K₂O")&&sides[1].includes("KOH"))return "clear";
 if(sides[0].includes("CaO")&&sides[1].includes("Ca(OH)₂"))return "cloudy";
 return "";
}
// Products of reactions determine precipitate texture; never infer it solely
// from colour (white solids may be gelatinous, fine or crystalline).
const PRECIPITATE_STYLES=Object.freeze({
 "Cu(OH)₂":"gel",
 "Fe(OH)₂":"gel",
 "Fe(OH)₃":"gel",
 "Al(OH)₃":"gel",
 "H₂SiO₃":"gel",
 "BaSO₄":"fine",
 "ZnS":"fine",
 "BaCO₃":"fine",
 "CaCO₃":"fine",
 "AgCl":"floc",
 "PbI₂":"crystal",
 "AgI":"crystal",
 "AgBr":"crystal",
 "BaCrO₄":"crystal",
 "CuS":"dense",
 "PbS":"dense",
 "FeS":"dense",
 "Ag₂S":"dense",
 "Ag₂O":"dense",
 "MnO₂":"dense",
 "CuO":"dense"
});
function pptTexture(x){
 if(!x||!x.ppt)return "";
 const products=String(x.eq||"").split("→").pop();
 for(const [formula,texture] of Object.entries(PRECIPITATE_STYLES)){
  const pos=products.indexOf(formula);
  if(pos<0)continue;
  const before=products[pos-1]||"",after=products[pos+formula.length]||"";
  if(!/[A-Za-z₀-₉]/.test(before)&&!/[A-Za-z₀-₉]/.test(after))return texture;
 }
 const sign=String(x.sign||"").toLowerCase();
 if(sign.includes("студенист")||sign.includes("желеобразн"))return "gel";
 if(sign.includes("творожист")||sign.includes("хлопьевидн"))return "floc";
 if(sign.includes("кристалл"))return "crystal";
 if(sign.includes("плотн"))return "dense";
 return "fine";
}
function pptIsBright(color){
 const s=String(color||"").trim();
 const m=/^#([0-9a-f]{6})$/i.exec(s);
 if(!m)return false;
 const r=parseInt(m[1].slice(0,2),16),g=parseInt(m[1].slice(2,4),16),b=parseInt(m[1].slice(4,6),16);
 return (.2126*r+.7152*g+.0722*b)>165;
}
function precipitateHTML(x){
 if(!x||!x.ppt)return "";
 if(oxideSulfateTurbidity(x)||oxideHydration(x)==="cloudy")return "";
 const cls=pptTexture(x),parts=[],light=/^#(?:fff|ffffff|f8fbff)$/i.test(String(x.ppt));
 const bgClass=pptIsBright(x.ppt)?' bright-ppt':'';
 if(cls==="gel"){
  // Soft, connected clouds settle into an irregular sediment layer.
  for(let n=0;n<(light?20:13);n++){
   const l=(5+(n*29)%74), b=(8+(n*13)%34), w=(19+(n%4)*9), h=(9+(n%3)*7);
   parts.push('<i class="gel-cloud" style="--l:'+l+'%;--b:'+b+'%;--w:'+w+'px;--h:'+h+'px;--delay:'+(n%6)*.09+'s;--pc:'+x.ppt+'"></i>');
  }
  return '<div class="pptLayer gel-sediment'+(light?' light-ppt':'')+bgClass+'"><i class="gel-bed" style="--pc:'+x.ppt+'"></i>'+parts.join("")+'</div>';
 }
 const count=light&&cls==="fine"?145:light&&cls==="floc"?58:light&&cls==="crystal"?30:cls==="fine"?44:cls==="dense"?38:cls==="crystal"?19:24;
 for(let n=0;n<count;n++){
  const l=(5+(n*37)%88),b=(2+(n*17)%(light&&cls==="floc"?50:30));
  const s=light&&cls==="fine"?2+(n%3):light&&cls==="floc"?5+(n%5)*2:cls==="fine"?2+(n%3)*2:cls==="dense"?4+(n%4)*2:cls==="crystal"?7+(n%4)*3:7+(n%5)*3;
  const r=((n*31)%90-45)+"deg";
  parts.push('<i class="particle '+cls+'" style="--l:'+l+'%;--b:'+b+'%;--s:'+s+'px;--r:'+r+';--pc:'+x.ppt+'"></i>');
 }
 // Ferric sulfide redox can produce both dark FeS and elemental sulfur.
 // Keep the black FeS dominant while giving yellow elemental sulfur
 // visible, distinct grains in front of the black sediment.
 if(x.ppt2&&cls==="dense"){
  for(let n=0;n<26;n++){
   const l=8+(n*43)%82,b=7+(n*11)%31,s=5+(n%4),r=((n*19)%70-35)+"deg";
   parts.push('<i class="particle fine secondary-ppt" style="--l:'+l+'%;--b:'+b+'%;--s:'+s+'px;--r:'+r+';--pc:'+x.ppt2+'"></i>');
  }
 }
 return '<div class="pptLayer'+(cls==="dense"?' dense-sediment':'')+(light?' light-ppt':'')+bgClass+'">'+(cls==="dense"?'<i class="dense-bed" style="--pc:'+x.ppt+'"></i>':'')+parts.join("")+'</div>';
}
function bubblesHTML(x,v=[]){
 if(!x||!x.gas)return "";
 const parts=[],fizz=[],boil=[];
 // Carbonates reacting as solid pieces fizz at their surface instead of
 // looking like a vigorously boiling homogeneous solution.
 const solidFizz=x.gas==="CO₂"&&v.some(id=>String((reagent(id)||[])[3]||"").includes("тв."))&&solidReactionMode(v,x)==="dissolving_solid";
 const strong=["CO₂","SO₂","H₂S","NO₂"].includes(x.gas)&&!solidFizz;
 const count=solidFizz?22:(strong?42:30);
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
 const gasInfo=GAS_REFERENCE[x.gas];
 const gasColor=gasInfo?gasInfo.plume:'rgba(255,255,255,.18)';
 const gasClass=x.gas==="NO₂"?" no2":x.gas==="Cl₂"?" cl2":"";
 return (strong?'<div class="boilLayer'+gasClass+'">'+boil.join("")+'</div>':'')+'<div class="bubbleLayer '+(strong?'strong':'')+gasClass+'">'+parts.join("")+'</div><div class="surfaceFizz'+gasClass+'">'+fizz.join("")+'</div><div class="gasPlume'+gasClass+'" style="--gasColor:'+gasColor+'"></div>';
}
// Determine whether the chemical record supports visible consumption of a
// solid; a missing/non-reactive/heating-required reaction must not dissolve it.
function solidReactionMode(v,x){
 if(!x||x.t==="z")return "";
 const solids=v.filter(id=>String((reagent(id)||[])[3]||"").includes("тв."));
 if(!solids.length)return "";
 if(solids.some(id=>(reagent(id)||[])[1]==="Металлы"))return "reactive_metal";
 const sign=String(x.sign||"").toLowerCase();
 if(oxideHydration(x))return "dissolving_solid";
 if(/разлагается|разложени/.test(sign))return "decomposing_solid";
 if(/растворяется|растворяются|растворени|исчезает|исчезают/.test(sign))return "dissolving_solid";
 // A solid reactant is consumed if it occurs on the left of a confirmed
 // equation but is absent from the products. Do not rely on Russian prose.
 const eq=String(x.eq||""),parts=eq.split(/→|⟶/);
 if(parts.length===2&&solids.some(id=>{
   const formula=String((reagent(id)||[])[0]||"");
   const species=side=>side.split(/\s+\+\s+/).map(s=>s.replace(/^\s*\d+\s*/,"").replace(/[↓↑]/g,"").trim());
   return formula&&species(parts[0]).includes(formula)&&!species(parts[1]).includes(formula);
 }))return "dissolving_solid";
 return "";
}
function solidReagentHTML(v,x,hasMetalDeposit=false){
 if(!v.length||hasMetalDeposit)return "";
 const solids=v.filter(id=>String((reagent(id)||[])[3]||"").includes("тв."));
 if(!solids.length)return "";
 const id=solids[solids.length-1],r=reagent(id),parts=[];
 const mode=solidReactionMode(v,x),consuming=!!mode;
 if(r[1]==="Металлы"){
  return '<div class="solidBed reactive-metal'+(consuming?' dissolving-solid':'')+'"><i class="metalPiece" style="--metalColor:'+r[2]+'"></i></div>';
 }
 for(let n=0;n<18;n++){
  parts.push('<i class="solidChunk" style="--l:'+(3+(n*29)%82)+'%;--b:'+(1+(n*13)%18)+'%;--s:'+(8+(n%5)*3)+'px;--r:'+(((n*31)%80)-40)+'deg;--sc:'+r[2]+'"></i>');
 }
 return '<div class="solidBed'+(consuming?' dissolving-solid':'')+'">'+parts.join("")+'</div>';
}
function metalDepositHTML(v,x){
 if(!x||!x.ppt)return "";
 const metalId=v.find(id=>String((reagent(id)||[])[1]||"")==="Металлы");
 if(!metalId)return "";
 const m=reagent(metalId),crystals=[];
 for(let n=0;n<22;n++){
   crystals.push('<i class="metalCrystal" style="--l:'+(12+(n*31)%70)+'%;--b:'+(8+(n*17)%30)+'%;--s:'+(4+(n%5)*3)+'px;--r:'+(((n*37)%100)-50)+'deg;--depositColor:'+x.ppt+'"></i>');
 }
 return '<div class="metalReactionBed"><i class="metalPiece dissolving-metal" style="--metalColor:'+m[2]+'"></i>'+crystals.join("")+'</div>';
}
function tubeIsLiquid(id){
 const phase=String((reagent(id)||[])[3]||"");return !!phase&&!phase.includes("тв.")&&!phase.includes("газ");
}
function tubeLiquidLevel(portions){return portions>0?Math.min(84,36+(portions-1)*18):0;}
// Per-tube event clocks survive re-renders and switching workbenches. Negative
// CSS delays resume a physical transition instead of restarting it.
function tubeMotionFor(state,history,reaction,sources=history){
 const now=Date.now(),previous=state.history||[];
 if(history.length<previous.length||(previous.length&&history[0]!==previous[0])){
  for(const key of Object.keys(state))delete state[key];
 }
 const amount=Math.max(state.level||0,tubeLiquidLevel(history.filter(tubeIsLiquid).length+(state.extraPours||0)));
 if(amount>(state.level||0)){
  state.from=state.level||0;state.pourAt=now;state.pourColor=reagent(history.filter(tubeIsLiquid).at(-1))[2];
 }
 state.level=amount;state.history=history.slice();
 const key=reaction&&reaction.t!=="z"?reaction.eq+"|"+history.join(","):"";
 if(key&&key!==state.reactionKey){state.reactionKey=key;state.solidAt=now;state.solidSources=sources.slice();}
 return {level:state.level,from:state.from||0,pourColor:state.pourColor||"#d8eaf4",pourAge:state.pourAt?(now-state.pourAt)/1000:10,
  solidAge:state.solidAt?(now-state.solidAt)/1000:10,solidSources:reaction?state.solidSources:null};
}
function tubeHTML(v,i,active,heated,excess="",overrideReaction=undefined,indicator="",indicatorExplicit="",motion=null){
 // Lesson studio supplies its own medium/stage result; never read the main lab tube state.
 const chosen=overrideReaction===undefined ?
   (v.length===2?(tubeDissolving[i]?reactionExpected(v[0],v[1]):findReaction(v[0],v[1],heated,excess)):null) : overrideReaction;
 const x=chosen&&chosen.heat&&!heated?null:chosen;
 const base=v.length?reagent(v[v.length-1])[2]:"#f8fbff";
 // Keep a colorless solution optically clear when a white precipitate forms.
 // The contrast comes from particle edges and the bench backing, not dyed liquid.
 const rawSol=x&&/→[^\n]*CuCl₂/.test(String(x.eq||""))&&!x.ppt?"#bde6df":x?x.sol:base;
 const medium=indicator?indicatorMedium(v,indicatorExplicit):"";
 const indicatorColor=medium&&indicator?INDICATORS[indicator][medium]:"";
 const sol=indicatorColor|| (x&&x.ppt&&pptIsBright(x.ppt)&&/^#(?:fff(?:fff)?|f8fbff|f7fafc|f5faff)$/i.test(String(rawSol))
  ?'rgba(181,198,207,.22)':rawSol);
 const hasLiquid=v.some(id=>{
   const st=String((reagent(id)||[])[3]||"");
   return !st.includes("тв.")&&!st.includes("газ");
 });
 // Each subsequent pour raises the visual level; the tube has a fixed capacity.
 const liquidHeight=motion?motion.level:(hasLiquid?tubeLiquidLevel(v.filter(tubeIsLiquid).length):0);
 const solidInput=motion?.solidSources||v;
 const hasMetalDeposit=!!(x&&x.ppt&&solidInput.some(id=>String((reagent(id)||[])[1]||"")==="Металлы"));
 const solids=solidReagentHTML(solidInput,x,hasMetalDeposit);
 const deposit=hasMetalDeposit?metalDepositHTML(solidInput,x):"";
 const reactionVisual=x&&x.t!=="z"?((hasMetalDeposit?"":precipitateHTML(x))+bubblesHTML(x,v)+deposit+'<i class="reactionGlow"></i>'):"";
 const shimmer=(heated&&v.length)?'<i class="heatShimmer"></i>':"";
 const pouring=!!(motion&&motion.pourAge<1&&motion.level>motion.from);
 const timing=motion?' style="--pourAge:-'+motion.pourAge+'s;--solidAge:-'+motion.solidAge+'s;--fromLevel:'+motion.from+'%;--toLevel:'+liquidHeight+'%;--pourColor:'+motion.pourColor+'"':'';
 const stream=pouring?'<i class="pourStream" aria-hidden="true"></i><i class="pourRipple" aria-hidden="true"></i>':'';
 return '<div class="tube '+(active?'on':'')+'"'+timing+'><i class="liq'+(pouring?' filling':'')+((oxideSulfateTurbidity(x)||oxideHydration(x)==="cloudy")?' oxide-turbidity':'')+'" style="height:'+liquidHeight+'%;background:'+sol+'"></i>'+stream+solids+reactionVisual+shimmer+'</div>';
}
function tubeHasMedium(v){
 if(v.length!==2)return false;
 if(v.includes("hcl")&&v.some(id=>["kmno4","k2mno4"].includes(id)))return false;
 return (v.some(id=>["kmno4","k2mno4","na2mno4"].includes(id))||(data.medium_reactions||[]).some(r=>
   (r.a===v[0]&&r.b===v[1])||(r.a===v[1]&&r.b===v[0])));
}
function tubeReaction(i){
 const v=tubes[i];if(v.length!==2)return null;
 if(!tubeHasMedium(v))return reactionExpected(v[0],v[1],tubeExcess[i]);
 const medium=tubeMedium[i];
 if(!medium)return null;
 const exact=(data.medium_reactions||[]).find(r=>r.medium===medium &&
   ((r.a===v[0]&&r.b===v[1])||(r.a===v[1]&&r.b===v[0])));
 if(exact)return exact;
 if(medium==="alkaline"&&v.includes("croh3")&&v.includes("koh"))
   return reactionExpected(v[0],v[1]);
 return null;
}
function syncTubeMedium(){
 const field=document.getElementById("tubeMediumField");
 if(!field)return;
 const visible=tubeHasMedium(tubes[selectedTube]);
 field.hidden=!visible;
 document.getElementById("tubeMedium").value=visible?tubeMedium[selectedTube]:"";
}
// Preserve the actual liquid/precipitate nodes when only another workbench changes.
const tubeVisualCache=new WeakMap();
function renderTubeVisual(host,key,create,active){
 if(tubeVisualCache.get(host)!==key){host.innerHTML=create();tubeVisualCache.set(host,key);}
 host.querySelector(".tube")?.classList.toggle("on",active);
}
const mainTubeMotion=[{},{},{},{}];
function renderTubes(){
 const box=document.getElementById("tubes");
 tubes.forEach((v,i)=>{
  let wrap=box.children[i];
  if(!wrap){
   wrap=document.createElement("div");wrap.className="tube-slot";
   wrap.innerHTML='<div class="tube-callout-host"></div><div class="tube-visual-host"></div><div class="tubeLabel">'+(i+1)+'</div><div class="tube-label-host"></div>';
   wrap.onclick=()=>{selectedTube=i;syncTubePicker();renderTubes()};box.appendChild(wrap);
  }
  wrap.classList.toggle("active-slot",i===selectedTube);
  const chain=tubeChain[i],hasChain=!!(chain&&chain.steps.length>1);
  const hasMedium=!hasChain&&tubeHasMedium(v);
  const x=hasChain?chain.steps[chain.steps.length-1].reaction:(v.length===2?tubeReaction(i):null);
  const visibleReaction=x&&x.heat&&!tubeHeat[i]?null:x;
  let callout="";
  if(i===selectedTube&&v.length>=2){
    const cls=i===0?" edge-left":i===3?" edge-right":"";
    const content=x?reactionResultHTML(x,tubeHeat[i]):
      hasMedium&&tubeMedium[i]?
      '<div class="reaction-card no-visible">Для этой среды нет подтверждённой реакции. Результат не моделируем.</div>':
      hasMedium?'<div class="reaction-card no-visible">Выбери среду реакции справа.</div>':
      reactionResultHTML(x,tubeHeat[i]);
    const history=hasChain?'<details class="chain-history"><summary>Цепочка: '+chainStepLabel(chain.steps.length)+'</summary>'+chain.steps.map((step,n)=>'<div class="reaction-equation">'+(n+1)+'. '+step.reaction.eq+'</div>'+chainUntrackedNotice(step)).join("")+'<small>Цепочка качественная: количества реагентов не рассчитываются.</small></details>':'';
    callout='<div class="tube-callout'+cls+'">'+content+history+'</div>';
  }
  const excessLabel=tubeExcess[i]?'<div class="tubeSmall">избыток: '+reagent(tubeExcess[i])[0]+'</div>':'';
  const calloutHost=wrap.querySelector(".tube-callout-host");
  if(calloutHost.innerHTML!==callout)calloutHost.innerHTML=callout;
  const key=JSON.stringify([v,tubeHeat[i],tubeExcess[i],visibleReaction,tubeIndicators[i],tubeMedium[i],mainTubeMotion[i].extraPours||0]);
  renderTubeVisual(wrap.querySelector(".tube-visual-host"),key,
   ()=>tubeHTML(v,i,i===selectedTube,tubeHeat[i],tubeExcess[i],visibleReaction,tubeIndicators[i],tubeMedium[i],tubeMotionFor(mainTubeMotion[i],v,visibleReaction,hasChain?[chain.steps.at(-1).reactant,chain.steps.at(-1).reagent]:v)),i===selectedTube);
  const label='<div class="tubeSmall">'+(v.map(q=>reagent(q)[0]).join(" + ")||"пусто")+'</div>'+excessLabel;
  const labelHost=wrap.querySelector(".tube-label-host");if(labelHost.innerHTML!==label)labelHost.innerHTML=label;
 });
 syncTubeMedium();
 const selected=tubes[selectedTube];
 const heatReaction=selected.length===2?tubeReaction(selectedTube):null;
 syncHeatHint("heat","heatHint",heatReaction,tubeHeat[selectedTube]);
 syncIndicatorControls();
 positionMobileReactionCallout();
}
function syncIndicatorControls(){
 const panel=document.getElementById("indicatorPanel");if(!panel)return;
 panel.innerHTML=indicatorPanelHTML(tubeIndicators[selectedTube]);
 panel.querySelectorAll("[data-indicator]").forEach(btn=>btn.onclick=()=>{
  tubeIndicators[selectedTube]=btn.dataset.indicator;renderTubes();
 });
 document.getElementById("indicatorNote").textContent=indicatorNoteText(tubeIndicators[selectedTube],tubes[selectedTube],indicatorMedium(tubes[selectedTube],tubeMedium[selectedTube]));
}
document.getElementById("indicatorToggle").onclick=()=>{
 const panel=document.getElementById("indicatorPanel");panel.hidden=!panel.hidden;
 document.getElementById("indicatorToggle").setAttribute("aria-expanded",String(!panel.hidden));
};
function positionMobileReactionCallout(){
 if(window.innerWidth>820)return;
 requestAnimationFrame(()=>{
  const callout=document.querySelector(".tube-slot.active-slot .tube-callout");
  const tube=document.querySelector(".tube-slot.active-slot .tube");
  const bench=document.querySelector(".lab-bench");
  if(!callout||!tube){
   if(bench)bench.classList.remove("mobile-result-expanded");
   return;
  }
  if(bench)bench.classList.add("mobile-result-expanded");
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
 if(tubes[selectedTube].length>=2){
  const index=selectedTube,v=tubes[index];
  if(!tubeChain[index]){
   const first=tubeReaction(index);
   if(!first||first.t==="z"||(first.heat&&!tubeHeat[index])){
    document.getElementById("result").textContent="Сначала заверши предыдущую реакцию и выбери необходимые условия.";return;
   }
   const details=chainProductDetails(first),products=details.ids;
   if(!products.length){
    document.getElementById("result").textContent="Продукты предыдущей реакции не распознаны. Продолжить цепочку автоматически нельзя.";return;
   }
   tubeChain[index]={available:products,steps:[{reagent:v[1],reactant:v[0],reaction:first,available:products.slice(),untracked:details.untracked}]};
  }
  const matches=chainCandidates(index,id);
  if(!matches.length){
   const available=chainAvailable(index).filter(candidate=>candidate!==id);
   const needsMedium=available.some(candidate=>tubeHasMedium([candidate,id]));
   const needsHeat=available.some(candidate=>{
    const rx=findReaction(candidate,id,true);
    return rx&&rx.t!=="z"&&rx.heat&&!tubeHeat[index];
   });
   document.getElementById("result").textContent=needsMedium?
    "Следующий этап требует выбора среды реакции. Автоматическое продолжение такой цепочки пока недоступно.":
    needsHeat?"Для следующего этапа сначала включи нагрев 🔥 и добавь реактив снова.":
    "Для добавленного реактива нет подтверждённой реакции с текущими продуктами. Цепочка не изменена.";
   if(needsHeat){
    const pending=available.map(candidate=>findReaction(candidate,id,true)).find(rx=>rx&&rx.t!=="z"&&rx.heat);
    syncHeatHint("heat","heatHint",pending,false);
    document.getElementById("heatHint").textContent+=" После нагрева добавь выбранный реактив ещё раз.";
   }
   return;
  }
  if(matches.length===1){
   if(!chainCompleteStep(index,id,matches[0].id))document.getElementById("result").textContent="Не удалось определить продукты. Этап не добавлен.";
   return;
  }
  const result=document.getElementById("result");result.replaceChildren();
  const intro=document.createElement("p");intro.textContent="В смеси несколько возможных реагентов. Выбери, с каким продолжить цепочку:";result.appendChild(intro);
  matches.forEach(({id:reactant,rx})=>{
   const btn=document.createElement("button");btn.type="button";btn.textContent=reagent(reactant)[0]+" — "+rx.eq;
   btn.onclick=()=>{if(!chainCompleteStep(index,id,reactant))result.textContent="Не удалось определить продукты. Этап не добавлен."};
   result.appendChild(btn);
  });
  return;
 }
 tubeHeat[selectedTube]=false;tubeExcess[selectedTube]="";tubeDissolving[selectedTube]=false;tubeMedium[selectedTube]="";
 tubes[selectedTube].push(id);
 if(tubes[selectedTube].length===2){
  const needsMedium=tubeHasMedium(tubes[selectedTube]);
  const x=needsMedium?null:tubeReaction(selectedTube);
  document.getElementById("result").textContent=needsMedium?"Выбери среду реакции справа.":
      x?(x.heat?"Нужен нагрев 🔥":"Карточка реакции показана над пробиркой ↑"):
      "Этот опыт пока не добавлен в базу";
  if(x&&!x.heat)api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()});
 }
 renderTubes();
}
document.getElementById("tubeMedium").onchange=()=>{
 tubeMedium[selectedTube]=document.getElementById("tubeMedium").value;
 tubeHeat[selectedTube]=false;
 const v=tubes[selectedTube],rx=tubeReaction(selectedTube);
 document.getElementById("result").textContent=!tubeMedium[selectedTube]?"Выбери среду реакции.":
   rx?(rx.heat?"Нужен нагрев 🔥":"Карточка реакции показана над пробиркой ↑"):
   "Для выбранной среды нет подтверждённой реакции.";
 if(rx&&!rx.heat)api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()});
 renderTubes();
};
document.getElementById("excess").onclick=()=>{
 const v=tubes[selectedTube];
 if(v.length!==2){document.getElementById("result").textContent="Сначала добавь два реактива.";return}
 if(tubeHasMedium(v)){document.getElementById("result").textContent="Выбор среды и избытка для этой ОВР задаётся полем «Среда».";return}
 const alkali=v.find(id=>id==="naoh"||id==="koh");
 tubeExcess[selectedTube]=alkali&&reactionVariants(v[0],v[1]).some(x=>x.excess===alkali)?alkali:v[v.length-1];
 const index=selectedTube;
 if(tubeIsLiquid(tubeExcess[index]))mainTubeMotion[index].extraPours=(mainTubeMotion[index].extraPours||0)+1;
 const x=reactionExpected(v[0],v[1],tubeExcess[index]);
 tubeDissolving[index]=!!(x&&x.stages);
 document.getElementById("result").innerHTML=x&&x.excess?"Показываю реакцию при избытке "+reagent(tubeExcess[selectedTube])[0]+".":"Для этой пары отдельный результат избытка пока не требуется.";
 renderTubes();
 if(x&&x.stages)setTimeout(()=>{if(tubeExcess[index]===x.excess){tubeDissolving[index]=false;renderTubes()}},1100);
};
document.getElementById("heat").onclick=()=>{
 let v=tubes[selectedTube];tubeHeat[selectedTube]=true;
 let x=v.length===2?(tubeHasMedium(v)?tubeReaction(selectedTube):
     findReaction(v[0],v[1],true,tubeExcess[selectedTube])):null;
 if(x){document.getElementById("result").innerHTML="Карточка реакции показана над пробиркой ↑";api({action:"event",type:"experiment"}).then(j=>{data.stats=j.stats;renderStats()})}
 else if(v.length===2){document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🔥 Нагрев</span></div><div class="reaction-sign">При нагревании видимого изменения нет.</div></div>'}
 renderTubes();
};
document.getElementById("clear").onclick=()=>{tubes[selectedTube]=[];tubeChain[selectedTube]=null;tubeHeat[selectedTube]=false;tubeExcess[selectedTube]="";tubeDissolving[selectedTube]=false;tubeMedium[selectedTube]="";tubeIndicators[selectedTube]="";document.getElementById("result").innerHTML='<div class="reaction-card no-visible"><div class="reaction-head"><span class="reaction-status">🧽 Готово</span></div><div class="reaction-sign">Пробирка очищена.</div></div>';renderTubes()};

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
 const b=task.bottles[index],k=oge23Knowledge(b.id);
 const formula=b.formula||k.formula||b.id;
 const name=b.name||k.name||"";
 return '<span class="oge23-head-main">СКЛЯНКА №'+(index+1)+' — '+formula+'</span>'+
   '<span class="oge23-head-sub">'+name+'</span>';
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

// Teacher's live lesson studio. Both panels stay interactive at the same time.
// PDF input, ink notes and downloads remain entirely local to the browser.
let lessonReady=false,lessonStarted=false,lessonHeated=false,lessonExcess="",lessonDissolving=false,lessonIndicator="";
let lessonChain=null,lessonMotion={};
let lessonLabInkTool="view",lessonLabInkStrokes=[],lessonLabInkDrawing=null;
let lessonTubeStates=[null,null,null,null];
const lessonModeStates={};
let lessonActiveTube=0,lessonVisibleTubeCount=2;
function lessonEmptyTube(){
 return {reagents:{a:"",b:""},chain:null,started:false,heated:false,
  excess:"",dissolving:false,medium:"",indicator:"",ink:[],motion:{}};
}
function lessonCaptureTube(){
 return {reagents:{...lessonSelectedReagents},chain:lessonChain,started:lessonStarted,
  heated:lessonHeated,excess:lessonExcess,dissolving:lessonDissolving,
  medium:document.getElementById("lessonMedium").value,indicator:lessonIndicator,ink:lessonLabInkStrokes,motion:lessonMotion};
}
function lessonApplyTube(state){
 lessonSelectedReagents={...state.reagents};lessonChain=state.chain;lessonMotion=state.motion||{};
 lessonStarted=state.started;lessonHeated=state.heated;
 lessonExcess=state.excess;lessonDissolving=state.dissolving;
 lessonIndicator=state.indicator||"";
 lessonLabInkStrokes=state.ink;lessonLabInkDrawing=null;
 for(const slot of ["a","b"]){
  const el=document.getElementById(slot==="a"?"lessonReagentA":"lessonReagentB");
  el.value=lessonSelectedReagents[slot]?(reagent(lessonSelectedReagents[slot])||[])[0]||"":"";
 }
 lessonCloseSuggestions("a");lessonCloseSuggestions("b");
 lessonUpdateMedium();document.getElementById("lessonMedium").value=state.medium;
 document.getElementById("lessonHeat").setAttribute("aria-pressed",String(lessonHeated));
 document.getElementById("lessonExcess").setAttribute("aria-pressed",String(!!lessonExcess));
 lessonSyncIndicators();
}
function lessonPreviewTube(state,index){
 const pair=state.reagents||{a:"",b:""};let ids=pair.a?[pair.a]:[];
 let result=null;
 if(state.chain&&state.chain.steps.length){
  // Display the current mixture, not all reagents used in past stages.
  // During the brief dissolution animation keep the initial precipitate.
  ids=state.dissolving?state.chain.ids:state.chain.available.slice();
  result=state.dissolving?findReaction(pair.a,pair.b,state.heated):state.chain.steps[state.chain.steps.length-1].reaction;
  if(state.chain.noReactionNotice)result={...result,gas:""};
 }else if(state.started&&pair.a&&pair.b){
  ids=[pair.a,pair.b];
  result=state.dissolving?findReaction(pair.a,pair.b,state.heated):
   lessonSelectedReaction(pair.a,pair.b,state.heated,state.medium||"",state.excess);
 }
 const effective=result&&result.heat&&!state.heated?null:result;
 const last=state.chain?.steps.at(-1);
 const history=state.chain?state.chain.ids:(state.started&&pair.b?[pair.a,pair.b].filter(Boolean):[pair.a].filter(Boolean));
 const sources=last?[last.reactant,last.reagent]:history;
 const motion=tubeMotionFor(state.motion||(state.motion={}),history,effective,sources);
 return tubeHTML(ids,0,index===lessonActiveTube,state.heated,state.excess,result,state.indicator||"",state.medium||"",motion);
}
function lessonSyncIndicators(){
 const panel=document.getElementById("lessonIndicatorPanel");if(!panel)return;
 panel.innerHTML=indicatorPanelHTML(lessonIndicator);
 panel.querySelectorAll("[data-indicator]").forEach(btn=>btn.onclick=()=>{
  lessonIndicator=btn.dataset.indicator;lessonRenderTubePair();lessonSyncIndicators();
 });
 const ids=lessonSelectedReagents.a?[lessonSelectedReagents.a]:[];
 if(lessonStarted&&lessonSelectedReagents.b)ids.push(lessonSelectedReagents.b);
 document.getElementById("lessonIndicatorNote").textContent=indicatorNoteText(lessonIndicator,ids,indicatorMedium(ids,document.getElementById("lessonMedium").value));
}
document.getElementById("lessonIndicatorToggle").onclick=()=>{
 const panel=document.getElementById("lessonIndicatorPanel");panel.hidden=!panel.hidden;
 document.getElementById("lessonIndicatorToggle").setAttribute("aria-expanded",String(!panel.hidden));
};
function lessonRenderTubePair(){
 const active=lessonCaptureTube();
 document.getElementById("lessonTubeGrid").dataset.count=String(lessonVisibleTubeCount);
 for(let i=0;i<4;i++){
  const state=i===lessonActiveTube?active:lessonTubeStates[i];
  const key=JSON.stringify([state.reagents,state.chain,state.started,state.heated,state.excess,state.dissolving,state.medium,state.indicator,state.motion?.extraPours||0]);
  renderTubeVisual(document.getElementById("lessonTube"+(i+1)),key,()=>lessonPreviewTube(state,i),i===lessonActiveTube);
 }
 document.querySelectorAll("[data-lesson-tube]").forEach(btn=>{
  const on=Number(btn.dataset.lessonTube)===lessonActiveTube;
  btn.hidden=Number(btn.dataset.lessonTube)>=lessonVisibleTubeCount;
  btn.classList.toggle("on",on);btn.setAttribute("aria-pressed",String(on));
 });
 document.querySelectorAll("[data-lesson-count]").forEach(btn=>{
  btn.setAttribute("aria-pressed",String(Number(btn.dataset.lessonCount)===lessonVisibleTubeCount));
 });
}
function lessonSelectTube(index){
 lessonLabInkMode("view");
 if(index<0||index>=lessonVisibleTubeCount)return;
 if(index===lessonActiveTube)return;
 lessonTubeStates[lessonActiveTube]=lessonCaptureTube();
 lessonActiveTube=index;
 lessonApplyTube(lessonTubeStates[index]);
 lessonRenderExperiment();lessonLabInkRender();
}
function lessonSetTubeCount(count){
 if(!Number.isInteger(count)||count<1||count>4)return;
 if(count===lessonVisibleTubeCount)return;
 // Each count is a separate workbench. Its experiments remain available when
 // returning to that count but never leak into any other tube-count mode.
 lessonTubeStates[lessonActiveTube]=lessonCaptureTube();
 lessonModeStates[lessonVisibleTubeCount]={tubes:lessonTubeStates,active:lessonActiveTube};
 const target=lessonModeStates[count]||{
  tubes:Array.from({length:4},()=>lessonEmptyTube()),active:0
 };
 lessonTubeStates=target.tubes;
 lessonVisibleTubeCount=count;
 lessonActiveTube=Math.min(target.active,count-1);
 lessonApplyTube(lessonTubeStates[lessonActiveTube]);
 lessonRenderExperiment();
 lessonLabInkRender();
}
function lessonClearActiveTube(){
 // One tube is emptied without resetting the neighbouring experiments or PDF.
 lessonSelectedReagents={a:"",b:""};lessonChain=null;
 lessonIndicator="";
 lessonStarted=false;lessonHeated=false;lessonExcess="";lessonDissolving=false;
 lessonApplyTube({...lessonCaptureTube(),reagents:{a:"",b:""},chain:null,
  started:false,heated:false,excess:"",dissolving:false,medium:"",motion:{}});
 lessonTubeStates[lessonActiveTube]=lessonCaptureTube();
 lessonRenderExperiment();
}
let lessonPdfDocument=null,lessonPdfOriginalBytes=null,lessonPdfName="",lessonPdfKey="ege-lesson-blank";
let lessonPage=1,lessonPageCount=1,lessonTool="pen",lessonDrawing=null,lessonLineMode=false;
let lessonPenColorValue="#f00087",lessonMarkerColorValue="#ffce00";
let lessonPenWidthValue=3,lessonMarkerWidthValue=3,lessonLastInkTool="pen",lessonBeautify=true;
let lessonNotes={},lessonPageSize={},lessonRendering=0;
const lessonLibraries={};
// Quadratic interpolation removes sharp corners caused by discrete tablet
// pointer samples. The same geometry is used for canvas and PDF export.
function lessonSmoothPoints(points){
 if(!Array.isArray(points)||points.length<3)return points||[];
 // Light spatial averaging removes remaining fine pen jitter without changing
 // stroke endpoints, then quadratic interpolation rounds visible corners.
 const clean=points.map((p,i)=>{
  if(i===0||i===points.length-1)return p;
  const a=points[i-1],b=points[i+1];
  return {x:a.x*.2+p.x*.6+b.x*.2,y:a.y*.2+p.y*.6+b.y*.2};
 });
 const out=[clean[0]],mid=(a,b)=>({x:(a.x+b.x)/2,y:(a.y+b.y)/2});
 for(let i=1;i<points.length-1;i++){
  const start=i===1?clean[0]:mid(clean[i-1],clean[i]);
  const control=clean[i],end=mid(clean[i],clean[i+1]);
  for(let step=1;step<=8;step++){
   const t=step/8,u=1-t;
   out.push({x:u*u*start.x+2*u*t*control.x+t*t*end.x,
             y:u*u*start.y+2*u*t*control.y+t*t*end.y});
  }
 }
 out.push(clean[clean.length-1]);
 return out;
}
// New ink follows the stabilized samples instead of averaging them a second
// time. Centripetal interpolation avoids sharp joins without cutting loops.
function lessonStrokePoints(stroke,sx=1,sy=1){
 const points=stroke.points||[];
 // Roll back interpolating pen curves: they amplify tablet micro-jitter.
 // Keep the new marker path, but restore the previous pen geometry.
 if(stroke.renderVersion!==2||!(stroke.opacity<1))return lessonSmoothPoints(points);
 if(points.length<3||stroke.straight)return points;
 const clean=[];
 for(const p of points){const last=clean.at(-1);if(!last||Math.hypot(p.x*sx-last.x,p.y*sy-last.y)>1e-6)clean.push({x:p.x*sx,y:p.y*sy});}
 if(clean.length<3)return points;
 const out=[clean[0]],blend=(a,b,ta,tb,t)=>({x:((tb-t)*a.x+(t-ta)*b.x)/(tb-ta),y:((tb-t)*a.y+(t-ta)*b.y)/(tb-ta)});
 for(let i=0;i<clean.length-1;i++){
  const b=clean[i],c=clean[i+1];
  const a=clean[i-1]||{x:2*b.x-c.x,y:2*b.y-c.y};
  const d=clean[i+2]||{x:2*c.x-b.x,y:2*c.y-b.y};
  const span=(u,v)=>Math.max(1e-4,Math.sqrt(Math.hypot(u.x-v.x,u.y-v.y)));
  const t0=0,t1=span(a,b),t2=t1+span(b,c),t3=t2+span(c,d);
  for(let step=1;step<=8;step++){
   const t=t1+(t2-t1)*step/8;
   const a1=blend(a,b,t0,t1,t),a2=blend(b,c,t1,t2,t),a3=blend(c,d,t2,t3,t);
   out.push(blend(blend(a1,a2,t0,t2,t),blend(a2,a3,t1,t3,t),t1,t2,t));
  }
 }
 return out.map(p=>({x:p.x/sx,y:p.y/sy}));
}
// Finish-only spatial smoothing: resampling by arc length makes the result
// independent of tablet event frequency. No delayed cursor or text recognition.
function lessonFinishStroke(stroke,sx=1,sy=1){
 if(!lessonBeautify||!stroke||stroke.straight||stroke.opacity<1||stroke.points.length<4)return;
 const raw=stroke.points.map(p=>({x:p.x*sx,y:p.y*sy}));
 const lengths=[0];for(let i=1;i<raw.length;i++)lengths.push(lengths[i-1]+Math.hypot(raw[i].x-raw[i-1].x,raw[i].y-raw[i-1].y));
 const total=lengths[lengths.length-1];if(total<4)return;
 const step=Math.max(.75,total/12000),samples=[raw[0]];let index=1;
 for(let d=step;d<total;d+=step){
  while(index<raw.length-1&&lengths[index]<d)index++;
  const a=raw[index-1],b=raw[index],t=(d-lengths[index-1])/Math.max(1e-9,lengths[index]-lengths[index-1]);
  samples.push({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t});
 }
 samples.push(raw[raw.length-1]);
 const radius=Math.min(8,Math.ceil(4/step));
 const out=samples.map((p,i)=>{
  if(i===0||i===samples.length-1)return p;
  let x=0,y=0,weight=0;
  for(let j=Math.max(0,i-radius);j<=Math.min(samples.length-1,i+radius);j++){
   const w=Math.exp(-.5*((j-i)*step/1.8)**2);x+=samples[j].x*w;y+=samples[j].y*w;weight+=w;
  }
  x/=weight;y/=weight;
  // Keep loops, subscripts, arrow tips and intentional corners close to input.
  const delta=Math.hypot(x-p.x,y-p.y),limit=1.8,k=delta>limit?limit/delta:1;
  return {x:p.x+(x-p.x)*k,y:p.y+(y-p.y)*k};
 });
 stroke.points=out.map(p=>({x:p.x/sx,y:p.y/sy}));
}
// Keep transient input state outside saved strokes/projects.
const lessonStrokeFilters=new WeakMap();
function lessonAddStrokeSamples(stroke,event,converter,canvas){
 const samples=typeof event.getCoalescedEvents==="function"?event.getCoalescedEvents():[];
 const sx=canvas.clientWidth||1,sy=canvas.clientHeight||1;
 for(const sample of [...samples,event]){
  let point=converter(sample);
  const last=stroke.points[stroke.points.length-1];
  if(!last){stroke.points.push(point);continue;}
  const marker=stroke.opacity<1;
  if((lessonBeautify||marker)&&!stroke.straight){
   const raw={x:point.x*sx,y:point.y*sy},time=Number(sample.timeStamp);
   let state=lessonStrokeFilters.get(stroke);
   if(!state)state={raw:{x:last.x*sx,y:last.y*sy},filtered:{x:last.x*sx,y:last.y*sy},time:time-8};
   // Ignore duplicate coalesced/main events. Adapt to speed in screen pixels,
   // keeping fine slow strokes calm without dragging fast movements behind.
   const distance=Math.hypot(raw.x-state.raw.x,raw.y-state.raw.y);
   if(distance<.001&&event.type!=="pointerup")continue;
   const dt=Number.isFinite(time)&&Number.isFinite(state.time)?Math.max(.001,Math.min(.04,(time-state.time)/1000)):.008;
   const speed=distance/dt,cutoff=marker?3+.025*speed:6+.055*speed,alpha=1-Math.exp(-2*Math.PI*cutoff*dt);
   let filtered={x:state.filtered.x+alpha*(raw.x-state.filtered.x),y:state.filtered.y+alpha*(raw.y-state.filtered.y)};
   const lag=Math.hypot(raw.x-filtered.x,raw.y-filtered.y),limit=marker?3:1.5;
   if(lag>limit){filtered.x=raw.x+(filtered.x-raw.x)*limit/lag;filtered.y=raw.y+(filtered.y-raw.y)*limit/lag;}
   // Finish exactly at the pen lift; small indices and stroke ends stay intact.
   if(event.type==="pointerup"&&sample===event)filtered=raw;
   lessonStrokeFilters.set(stroke,{raw,filtered,time});
   point={x:filtered.x/sx,y:filtered.y/sy};
  }
  if(Math.hypot((point.x-last.x)*sx,(point.y-last.y)*sy)>=.15||(event.type==="pointerup"&&(point.x!==last.x||point.y!==last.y)))stroke.points.push(point);
 }
}
// The pen may deliver hundreds of coalesced samples per second. Paint at most
// once per display frame; never rebuild the whole page for every pointer event.
let lessonPdfInkFrame=0,lessonLabInkFrame=0;
function lessonSchedulePdfInk(){
 if(lessonPdfInkFrame)return;
 lessonPdfInkFrame=requestAnimationFrame(()=>{lessonPdfInkFrame=0;lessonRedrawInk();});
}
function lessonScheduleLabInk(){
 if(lessonLabInkFrame)return;
 lessonLabInkFrame=requestAnimationFrame(()=>{lessonLabInkFrame=0;lessonLabInkRender();});
}
function lessonLabInkRender(){
 const canvas=document.getElementById("lessonLabInk");if(!canvas)return;
 const area=canvas.parentElement,rect=area.getBoundingClientRect();
 const scale=Math.min(window.devicePixelRatio||1,2);
 const w=Math.max(1,Math.round(rect.width*scale)),h=Math.max(1,Math.round(rect.height*scale));
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 const ctx=canvas.getContext("2d");ctx.clearRect(0,0,w,h);
 for(const stroke of lessonLabInkStrokes){
  if(!stroke.points.length)continue;
  ctx.strokeStyle=ctx.fillStyle=stroke.color||"#C44988";
  ctx.lineWidth=(stroke.width||2.6)*scale;ctx.lineJoin="round";ctx.lineCap="round";
  ctx.beginPath();lessonStrokePoints(stroke,w,h).forEach((p,i)=>{
   if(i===0)ctx.moveTo(p.x*w,p.y*h);else ctx.lineTo(p.x*w,p.y*h);
  });
  if(stroke.points.length===1){const p=stroke.points[0];ctx.arc(p.x*w,p.y*h,1.5*scale,0,2*Math.PI);ctx.fill();}
  else ctx.stroke();
 }
}
function lessonLabInkPoint(e){
 const rect=document.getElementById("lessonLabInk").getBoundingClientRect();
 return {x:Math.max(0,Math.min(1,(e.clientX-rect.left)/Math.max(1,rect.width))),
         y:Math.max(0,Math.min(1,(e.clientY-rect.top)/Math.max(1,rect.height)))};
}
function lessonLabInkMode(mode){
 lessonLabInkTool=mode;
 const canvas=document.getElementById("lessonLabInk");
 canvas.classList.toggle("drawing",mode!=="view");
 canvas.classList.toggle("erasing",mode==="erase");
 [["lessonLabPen","pen"],["lessonLabEraser","erase"],["lessonLabView","view"]].forEach(([id,value])=>
  document.getElementById(id).setAttribute("aria-pressed",String(mode===value)));
}
function lessonLabInkSetup(){
 const canvas=document.getElementById("lessonLabInk");
 document.getElementById("lessonLabPen").onclick=()=>lessonLabInkMode("pen");
 document.getElementById("lessonLabEraser").onclick=()=>lessonLabInkMode("erase");
 document.getElementById("lessonLabView").onclick=()=>lessonLabInkMode("view");
 document.getElementById("lessonLabClear").onclick=()=>{lessonLabInkStrokes=[];lessonLabInkRender();};
 const erase=p=>{
  for(let i=lessonLabInkStrokes.length-1;i>=0;i--){
   if(lessonLabInkStrokes[i].points.some(q=>Math.hypot((q.x-p.x)*canvas.clientWidth,(q.y-p.y)*canvas.clientHeight)<14)){
    lessonLabInkStrokes.splice(i,1);lessonLabInkRender();break;
   }
  }
 };
 canvas.addEventListener("pointerdown",e=>{
  if(lessonLabInkTool==="view")return;
  e.preventDefault();canvas.setPointerCapture(e.pointerId);
  const point=lessonLabInkPoint(e);
  if(lessonLabInkTool==="erase"){erase(point);return;}
  lessonLabInkDrawing={renderVersion:2,color:document.getElementById("lessonPenColor").value,
   width:Number(document.getElementById("lessonPenWidth").value)||3,points:[point]};
  lessonLabInkStrokes.push(lessonLabInkDrawing);lessonLabInkRender();
 });
 canvas.addEventListener("pointermove",e=>{
  if(!(e.buttons&1))return;
  const point=lessonLabInkPoint(e);
  if(lessonLabInkTool==="erase"){erase(point);return;}
  if(!lessonLabInkDrawing)return;
  lessonAddStrokeSamples(lessonLabInkDrawing,e,lessonLabInkPoint,canvas);lessonScheduleLabInk();
 });
 for(const name of ["pointerup","pointercancel","lostpointercapture"])
  canvas.addEventListener(name,event=>{if(event.type==="pointerup"&&lessonLabInkDrawing){lessonAddStrokeSamples(lessonLabInkDrawing,event,lessonLabInkPoint,canvas);lessonFinishStroke(lessonLabInkDrawing,canvas.clientWidth,canvas.clientHeight);lessonScheduleLabInk();}lessonLabInkDrawing=null;});
 if(typeof ResizeObserver!=="undefined")new ResizeObserver(lessonLabInkRender).observe(canvas.parentElement);
 lessonLabInkRender();
}
function lessonStatus(message){
 const el=document.getElementById("lessonStatus");if(el)el.textContent=message;
}
function lessonLibrary(src,globalName){
 if(window[globalName])return Promise.resolve(window[globalName]);
 if(lessonLibraries[globalName])return lessonLibraries[globalName];
 lessonLibraries[globalName]=new Promise((resolve,reject)=>{
  const node=document.createElement("script");
  node.src=src;node.crossOrigin="anonymous";node.async=true;
  node.onload=()=>window[globalName]?resolve(window[globalName]):reject(new Error("library_missing"));
  node.onerror=()=>reject(new Error("library_download_failed"));
  document.head.appendChild(node);
 });
 return lessonLibraries[globalName];
}
function lessonSaveLocal(){
 try{
  localStorage.setItem(lessonPdfKey,JSON.stringify({version:1,notes:lessonNotes}));
  const state=document.getElementById("lessonPilotSaveState");if(state)state.textContent="Пометки PDF сохранены в этом браузере";
 }catch(err){
  const state=document.getElementById("lessonPilotSaveState");if(state)state.textContent="Пометки PDF не сохранены — скачайте копию";
  lessonStatus("Автосохранение недоступно — сохрани PDF или резервную копию записей.");
 }
}
function lessonRestoreLocal(){
 try{
  const raw=localStorage.getItem(lessonPdfKey);
  const parsed=raw?JSON.parse(raw):null;
  lessonNotes=parsed&&parsed.version===1&&parsed.notes&&typeof parsed.notes==="object"?parsed.notes:{};
 }catch(err){lessonNotes={};}
}
function lessonCurrentStrokes(){
 const key=String(lessonPage);
 if(!Array.isArray(lessonNotes[key]))lessonNotes[key]=[];
 return lessonNotes[key];
}
function lessonGetPoint(event){
 const box=document.getElementById("lessonInkCanvas").getBoundingClientRect();
 return {x:Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),
         y:Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))};
}
function lessonRedrawInk(){
 const canvas=document.getElementById("lessonInkCanvas");
 const ctx=canvas.getContext("2d");
 ctx.clearRect(0,0,canvas.width,canvas.height);
 const rect=canvas.getBoundingClientRect();
 const ratio=canvas.width/Math.max(1,rect.width);
 for(const stroke of lessonCurrentStrokes()){
  if(!stroke||!Array.isArray(stroke.points)||!stroke.points.length)continue;
  ctx.lineCap="round";ctx.lineJoin="round";
  ctx.globalAlpha=Math.max(.1,Math.min(1,Number(stroke.opacity??1)));
   ctx.strokeStyle=stroke.color||"#f00087";
  ctx.fillStyle=stroke.color||"#f00087";
  ctx.lineWidth=Math.max(1,Number(stroke.width)||3)*ratio;
  ctx.beginPath();
  for(const [i,p] of lessonStrokePoints(stroke,canvas.width,canvas.height).entries()){
   const px=p.x*canvas.width,py=p.y*canvas.height;
   if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
  }
  if(stroke.points.length===1){
   const p=stroke.points[0];ctx.beginPath();
   ctx.arc(p.x*canvas.width,p.y*canvas.height,ctx.lineWidth/2,0,Math.PI*2);ctx.fill();
  }else ctx.stroke();
 }
 ctx.globalAlpha=1;
}
function lessonEraseAt(point){
 const arr=lessonCurrentStrokes();
 for(let i=arr.length-1;i>=0;i--){
  if(arr[i].points&&arr[i].points.some(p=>Math.hypot(p.x-point.x,p.y-point.y)<.026)){
   arr.splice(i,1);lessonRedrawInk();lessonSaveLocal();return;
  }
 }
}
function lessonSaveInkTools(){
 try{localStorage.setItem("ege-lesson-ink-tools",JSON.stringify({pen:lessonPenColorValue,marker:lessonMarkerColorValue,penWidth:lessonPenWidthValue,markerWidth:lessonMarkerWidthValue,beautify:lessonBeautify}));}catch(err){}
}
function lessonRestoreInkTools(){
 try{
  const saved=JSON.parse(localStorage.getItem("ege-lesson-ink-tools")||"{}");
  if(/^#[0-9a-f]{6}$/i.test(saved.pen))lessonPenColorValue=saved.pen;
  if(/^#[0-9a-f]{6}$/i.test(saved.marker))lessonMarkerColorValue=saved.marker;
  if(typeof saved.beautify==="boolean")lessonBeautify=saved.beautify;
  if(Number.isFinite(saved.penWidth)&&saved.penWidth>=1&&saved.penWidth<=10)lessonPenWidthValue=saved.penWidth;
  if(Number.isFinite(saved.markerWidth)&&saved.markerWidth>=1&&saved.markerWidth<=10)lessonMarkerWidthValue=saved.markerWidth;
 }catch(err){}
 document.getElementById("lessonPenColor").value=lessonPenColorValue;
 document.getElementById("lessonPenWidth").value=lessonPenWidthValue;
 document.getElementById("lessonBeautify").checked=lessonBeautify;
}
function lessonSyncInkTools(){
 const color=lessonTool==="marker"?lessonMarkerColorValue:lessonPenColorValue;
 document.getElementById("lessonPenColor").value=color;
 document.querySelectorAll("#lessonColorPresets button,#lessonQuickColors button").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.ink===color)));
 for(const [id,tool] of [["lessonToolPen","pen"],["lessonToolMarker","marker"],["lessonToolEraser","erase"]])document.getElementById(id).setAttribute("aria-pressed",String(lessonTool===tool&&(tool==="erase"||!lessonLineMode)));
 for(const id of ["lessonToolPen","lessonBoardPen"])document.getElementById(id).style.setProperty("--tool-ink",lessonPenColorValue);
 for(const id of ["lessonToolMarker","lessonBoardMarker"])document.getElementById(id).style.setProperty("--tool-ink",lessonMarkerColorValue);
 document.getElementById("lessonInkCanvas").classList.toggle("eraser",lessonTool==="erase");
 if(lessonBoardMode)lessonBoardSetTool("pen");
}
function lessonSetTool(which){
 const width=document.getElementById("lessonPenWidth");
 if(lessonTool==="pen")lessonPenWidthValue=Number(width.value);
 if(lessonTool==="marker")lessonMarkerWidthValue=Number(width.value);
 lessonTool=which;document.querySelector("#lesson .lesson-extra-menu").open=false;lessonLineMode=false;document.getElementById("lessonStraightLine").setAttribute("aria-pressed","false");
 if(which==="pen"||which==="marker"){
  lessonLastInkTool=which;width.value=which==="pen"?lessonPenWidthValue:lessonMarkerWidthValue;
 }
 lessonSyncInkTools();lessonSaveInkTools();
}
function lessonSetLineMode(enabled){
 lessonLineMode=enabled;
 document.getElementById("lessonStraightLine").setAttribute("aria-pressed",String(enabled));
 lessonSyncInkTools();
}
function lessonSetCanvasDimensions(width,height){
 const paper=document.getElementById("lessonPdfCanvas"),ink=document.getElementById("lessonInkCanvas");
 const wrap=document.getElementById("lessonCanvasWrap");
 const pixelRatio=Math.min(window.devicePixelRatio||1,2);
 wrap.style.width=width+"px";wrap.style.height=height+"px";
 paper.style.width=ink.style.width=width+"px";
 paper.style.height=ink.style.height=height+"px";
 paper.width=ink.width=Math.max(1,Math.round(width*pixelRatio));
 paper.height=ink.height=Math.max(1,Math.round(height*pixelRatio));
 return pixelRatio;
}
async function lessonRenderPage(){
 const ticket=++lessonRendering;
 const space=document.getElementById("lessonPaperSpace");
 const canvas=document.getElementById("lessonPdfCanvas");
 const baseWidth=Math.max(120,space.clientWidth-24);
 const baseHeight=Math.max(160,space.clientHeight-24);
 let page=null,logicalWidth=960,logicalHeight=540;
 if(lessonPdfDocument){
  try{
   page=await lessonPdfDocument.getPage(lessonPage);
   if(ticket!==lessonRendering)return;
   const viewport=page.getViewport({scale:1});
   logicalWidth=viewport.width;logicalHeight=viewport.height;
  }catch(err){lessonStatus("Не удалось прочитать страницу PDF.");return;}
 }
 lessonPageSize[String(lessonPage)]={width:logicalWidth,height:logicalHeight};
 const scale=Math.min(baseWidth/logicalWidth,baseHeight/logicalHeight);
 const width=Math.max(1,Math.round(scale*logicalWidth));
 const height=Math.max(1,Math.round(scale*logicalHeight));
 const pixelRatio=lessonSetCanvasDimensions(width,height);
 const ctx=canvas.getContext("2d");
 if(page){
  try{
   const viewport=page.getViewport({scale:scale*pixelRatio});
   await page.render({canvasContext:ctx,viewport}).promise;
  }catch(err){lessonStatus("Не удалось отобразить страницу PDF.");return;}
 }else{
  ctx.fillStyle="#ffffff";ctx.fillRect(0,0,canvas.width,canvas.height);
 }
 if(ticket!==lessonRendering)return;
 document.getElementById("lessonPageCounter").textContent=lessonPage+" / "+lessonPageCount;
 document.getElementById("lessonPrevious").disabled=lessonPage<=1;
 document.getElementById("lessonNext").disabled=lessonPage>=lessonPageCount;
 lessonRedrawInk();
}
async function lessonOpenPDF(file){
 if(!file)return;
 if(file.size>25*1024*1024){lessonStatus("PDF больше 25 МБ — выбери файл меньшего размера.");return;}
 lessonStatus("Открываю PDF...");
 try{
  const reader=await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs");
  reader.GlobalWorkerOptions.workerSrc="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";
  const buffer=await file.arrayBuffer();
  const documentPDF=await reader.getDocument({data:new Uint8Array(buffer.slice(0)),isEvalSupported:false}).promise;
  lessonPdfDocument=documentPDF;
  lessonPdfOriginalBytes=buffer;
  lessonPdfName=file.name;
  lessonPdfKey="ege-lab-lesson-notes-v1:"+file.name+":"+file.size+":"+file.lastModified;
  lessonPage=1;lessonPageCount=documentPDF.numPages;
  lessonRestoreLocal();
  await lessonRenderPage();
  document.getElementById("lessonFileName").textContent=file.name;
  lessonStatus("PDF и рукописные записи работают одновременно с опытом.");
 }catch(err){
  lessonStatus("Не удалось открыть PDF. Проверь интернет и формат файла.");
 }
}
function lessonColorToPDF(hex){
 const c=String(hex||"#f00087").replace("#","");
 const v=/^[0-9a-f]{6}$/i.test(c)?c:"f00087";
 return [parseInt(v.slice(0,2),16)/255,parseInt(v.slice(2,4),16)/255,parseInt(v.slice(4,6),16)/255];
}
function lessonDownload(bytes,name,type){
 const blob=new Blob([bytes],{type:type});
 const url=URL.createObjectURL(blob);
 const link=document.createElement("a");link.href=url;link.download=name;
 document.body.appendChild(link);link.click();link.remove();
 // Edge may still be opening the downloaded PDF when the click returns.
 setTimeout(()=>URL.revokeObjectURL(url),60000);
}
let lessonPdfExportBusy=false;
const lessonPdfExportCache={document:null,pages:new Map(),bytes:0};
async function lessonExportPDF(){
 if(lessonPdfExportBusy)return;
 lessonPdfExportBusy=true;
 const exportButton=document.getElementById("lessonExport"),label=exportButton.querySelector("span");
 exportButton.disabled=true;exportButton.setAttribute("aria-busy","true");label.textContent="Сохраняю PDF…";
 lessonStatus("Собираю PDF с твоими записями...");
 try{
  // Paint acknowledgement before loading libraries or assembling a long lesson.
  await new Promise(resolve=>{requestAnimationFrame(()=>requestAnimationFrame(resolve));setTimeout(resolve,100);});
  const notes=structuredClone(lessonNotes),sizes=structuredClone(lessonPageSize);
  const sourceDocument=lessonPdfDocument,sourceBytes=lessonPdfOriginalBytes,sourceName=lessonPdfName;
  if(lessonPdfExportCache.document!==sourceDocument){lessonPdfExportCache.document=sourceDocument;lessonPdfExportCache.pages.clear();lessonPdfExportCache.bytes=0;}
  const lib=await lessonLibrary("https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js","PDFLib");
  // Render each imported page with the same PDF.js engine used in the lesson.
  // Copying pdf-lib page objects from imperfect classroom PDFs can silently
  // discard their content, even if the exported PDF has valid cross-references.
  const pdf=await lib.PDFDocument.create();
  if(sourceBytes){
   if(!sourceDocument)throw new Error("pdf-not-open");
   for(let index=1;index<=sourceDocument.numPages;index++){
    label.textContent="PDF: "+index+" / "+sourceDocument.numPages;
    let cached=lessonPdfExportCache.pages.get(index);
    if(!cached){
     const sourcePage=await sourceDocument.getPage(index),base=sourcePage.getViewport({scale:1}),viewport=sourcePage.getViewport({scale:2});
     const canvas=document.createElement("canvas");canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
     try{
      const context=canvas.getContext("2d",{alpha:false});context.fillStyle="#ffffff";context.fillRect(0,0,canvas.width,canvas.height);
      await sourcePage.render({canvasContext:context,viewport}).promise;
      const jpeg=await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error("pdf-page-image-failed")),"image/jpeg",.94));
      cached={width:base.width,height:base.height,bytes:new Uint8Array(await jpeg.arrayBuffer())};
     }finally{canvas.width=canvas.height=0;}
     const limit=24*1024*1024;
     if(cached.bytes.byteLength<=limit){
      while(lessonPdfExportCache.bytes+cached.bytes.byteLength>limit&&lessonPdfExportCache.pages.size){const first=lessonPdfExportCache.pages.keys().next().value;lessonPdfExportCache.bytes-=lessonPdfExportCache.pages.get(first).bytes.byteLength;lessonPdfExportCache.pages.delete(first);}
      lessonPdfExportCache.pages.set(index,cached);lessonPdfExportCache.bytes+=cached.bytes.byteLength;
     }
    }
    const embedded=await pdf.embedJpg(cached.bytes);
    const sheet=pdf.addPage([cached.width,cached.height]);sheet.drawImage(embedded,{x:0,y:0,width:cached.width,height:cached.height});
   }
  }else pdf.addPage([960,540]);
  const pages=pdf.getPages();
  for(let i=0;i<pages.length;i++){
   const sheet=pages[i],w=sheet.getWidth(),h=sheet.getHeight();
   const arr=notes[String(i+1)]||[];
   const logical=(sizes[String(i+1)]||{width:w,height:h}).width;
   for(const stroke of arr){
    const pts=lessonStrokePoints(stroke,w,h);
    const rgb=lessonColorToPDF(stroke.color);
    const color=lib.rgb(rgb[0],rgb[1],rgb[2]);
    const thickness=Math.max(.6,Number(stroke.width||3)*w/Math.max(1,logical));
    if(pts.length>1){
     const path=pts.map((p,k)=>(k?"L":"M")+(p.x*w)+" "+(p.y*h)).join(" ");
     sheet.pushOperators(lib.setLineJoin(lib.LineJoinStyle.Round));
     sheet.drawSvgPath(path,{x:0,y:h,borderColor:color,borderWidth:thickness,
      borderLineCap:lib.LineCapStyle.Round,borderOpacity:Math.max(.1,Math.min(1,Number(stroke.opacity??1)))});
    }
    if(pts.length===1)sheet.drawCircle({
     x:pts[0].x*w,y:(1-pts[0].y)*h,size:thickness/2,color:color,opacity:Math.max(.1,Math.min(1,Number(stroke.opacity??1)))
    });
   }
  }
  label.textContent="Собираю файл…";
  const bytes=await pdf.save();
  const header=new TextDecoder("latin1").decode(bytes.slice(0,8));
  const trailer=new TextDecoder("latin1").decode(bytes.slice(-1024));
  if(!header.startsWith("%PDF-")||!trailer.includes("%%EOF"))throw new Error("invalid-pdf-output");
  const title=(sourceName||"Урок").replace(/\.pdf$/i,"")+"_с_записями.pdf";
  lessonDownload(bytes,title,"application/pdf");
  lessonStatus("PDF подготовлен — скачивание началось.");
 }catch(err){
  lessonStatus("Не удалось сохранить PDF. Проверь подключение и попробуй ещё раз.");
 }finally{lessonPdfExportBusy=false;exportButton.disabled=false;exportButton.removeAttribute("aria-busy");label.textContent="Сохранить PDF";}
}
// Medium-specific redox from the authoritative catalogue, never a guessed product.
// The same source powers the 30/70 offline preview and the live lesson.
// Live PDF lesson: same keyboard-first search as the offline prototype.
// Store catalogue IDs separately: visible input is a formula/name, not an ID.
let lessonSelectedReagents={a:"",b:""};
let lessonSuggested={a:[],b:[]};
let lessonSuggestionIndex={a:-1,b:-1};
function lessonNormalizeFormula(text){
 return String(text||"").normalize("NFKC").toLocaleLowerCase("ru")
   .replace(/[\s\u00a0.,·\-–—()[\]{}]/g,"");
}
const lessonReagentAliases={mno2:["оксид марганца 4","оксид марганца (4)","диоксид марганца"]};
function lessonSearchMatches(raw){
 const q=lessonNormalizeFormula(raw);
 if(!q)return [];
 return Object.entries(data.reagents).filter(([id,r])=>
    lessonNormalizeFormula(id).includes(q)||
    lessonNormalizeFormula(r[0]).includes(q)||
    lessonNormalizeFormula(r[1]||"").includes(q)||
    lessonNormalizeFormula(r[4]||"").includes(q)||
    lessonNormalizeFormula((lessonReagentAliases[id]||[]).join(" ")).includes(q)
 ).sort((a,b)=>{
    const exact=x=>lessonNormalizeFormula(x[0])===q||lessonNormalizeFormula(x[1][0])===q?0:1;
    return exact(a)-exact(b)||
      String(a[1][0]).localeCompare(String(b[1][0]),"ru");
 }).slice(0,8);
}
function lessonCloseSuggestions(slot){
 const label=slot==="a"?"A":"B";
 const box=document.getElementById("lessonSuggestions"+label);
 const input=document.getElementById("lessonReagent"+label);
 box.hidden=true;
 input.setAttribute("aria-expanded","false");
 input.removeAttribute("aria-activedescendant");
 lessonSuggestionIndex[slot]=-1;
}
function lessonSetReagent(slot,id){
 if(!data.reagents[id])return;
 if(slot==="a"){lessonChain=null;lessonMotion={};}
 lessonSelectedReagents[slot]=id;
 document.getElementById(slot==="a"?"lessonReagentA":"lessonReagentB").value=data.reagents[id][0];
 lessonCloseSuggestions(slot);
 if(!lessonChain)lessonStarted=false;
 lessonExcess="";lessonDissolving=false;
 document.getElementById("lessonExcess").setAttribute("aria-pressed","false");
 document.getElementById("lessonMedium").value="";
 lessonUpdateMedium();
 lessonRenderExperiment();
}
function lessonHighlightSuggestion(slot,index){
 const label=slot==="a"?"A":"B";
 const box=document.getElementById("lessonSuggestions"+label);
 const input=document.getElementById("lessonReagent"+label);
 const buttons=[...box.querySelectorAll('[role="option"]')];
 if(!buttons.length)return;
 const next=(index+buttons.length)%buttons.length;
 lessonSuggestionIndex[slot]=next;
 buttons.forEach((b,i)=>b.setAttribute("aria-selected",String(i===next)));
 input.setAttribute("aria-activedescendant",buttons[next].id);
 buttons[next].scrollIntoView({block:"nearest"});
}
function lessonShowSuggestions(slot,raw){
 const label=slot==="a"?"A":"B";
 const box=document.getElementById("lessonSuggestions"+label);
 const input=document.getElementById("lessonReagent"+label);
 const found=lessonSearchMatches(raw);
 lessonSuggested[slot]=found;
 lessonSuggestionIndex[slot]=-1;
 box.replaceChildren();
 if(!raw.trim()){lessonCloseSuggestions(slot);return;}
 if(!found.length){
   const empty=document.createElement("div");empty.className="lesson-search-empty";
   empty.textContent="Вещество не найдено в каталоге";box.appendChild(empty);
 }else{
   found.forEach(([id,entry],i)=>{
     const button=document.createElement("button");
     button.type="button";button.id="lessonOption"+label+i;
     button.setAttribute("role","option");button.setAttribute("aria-selected","false");
     const formula=document.createElement("span");formula.textContent=entry[0];
     const note=document.createElement("small");note.textContent=entry[4]||entry[1]||"";
     button.append(formula,note);
     button.addEventListener("pointerdown",event=>event.preventDefault());
     button.onclick=()=>lessonSetReagent(slot,id);
     box.appendChild(button);
   });
 }
 box.hidden=false;input.setAttribute("aria-expanded","true");
 input.removeAttribute("aria-activedescendant");
}
function lessonHasMedium(a,b){
 if([a,b].includes("hcl")&&[a,b].some(id=>["kmno4","k2mno4"].includes(id)))return false;
 if(!a||!b)return [a,b].some(id=>["kmno4","k2mno4","na2mno4"].includes(id));
 if([a,b].some(id=>["kmno4","k2mno4","na2mno4"].includes(id)))return true;
 return (data.medium_reactions||[]).some(x=>
   (x.a===a&&x.b===b)||(x.a===b&&x.b===a));
}
function lessonUpdateMedium(){
 const a=lessonSelectedReagents.a;
 const b=lessonSelectedReagents.b;
 const field=document.getElementById("lessonMediumField");
 const active=lessonChain&&b?
  lessonChain.available.some(id=>lessonHasMedium(id,b)):lessonHasMedium(a,b);
 field.hidden=!active;
 const select=document.getElementById("lessonMedium");
 if(!active){select.value="";return;}
 const title=(a==="kmno4"||b==="kmno4")?"KMnO₄":
   (a==="k2mno4"||b==="k2mno4")?"K₂MnO₄":
   (a==="na2mno4"||b==="na2mno4")?"Na₂MnO₄":
   (a==="k2cr2o7"||b==="k2cr2o7")?"K₂Cr₂O₇":
   (a==="k2cro4"||b==="k2cro4")?"K₂CrO₄":"выбранного вещества";
 field.querySelector("label").textContent="Среда реакции с "+title;
 document.getElementById("lessonMediumHint").textContent=
   "Укажи среду и дополнительные вещества по уравнению; они не добавляются автоматически.";
}
function lessonSelectedReaction(a,b,heated,medium=document.getElementById("lessonMedium").value,excess=lessonExcess){
 if(!a||!b)return null;
 if(lessonHasMedium(a,b)){
  if(!medium)return null;
  const exact=(data.medium_reactions||[]).find(x=>x.medium===medium &&
      ((x.a===a&&x.b===b)||(x.a===b&&x.b===a)));
  if(exact)return exact;
  if(medium==="alkaline" && ((a==="croh3"&&b==="koh")||(b==="croh3"&&a==="koh")))
      return findReaction(a,b,heated);
  return null;
 }
 const available=findReaction(a,b,heated,excess);
 if(available)return available;
 const pending=reactionExpected(a,b,excess);
 // A known heating requirement is not a missing catalogue entry. Execution
 // still checks heat before building the chain or showing a visual reaction.
 return pending?.heat?pending:null;
}
function lessonPopulateReagents(){
 for(const [slot,label] of [["a","A"],["b","B"]]){
  const input=document.getElementById("lessonReagent"+label);
  input.oninput=()=>{
   // Never reuse the old selected reagent when a different formula is typed.
   lessonSelectedReagents[slot]="";
   if(slot==="a")lessonChain=null;
   if(!lessonChain)lessonStarted=false;
   lessonExcess="";lessonDissolving=false;
   document.getElementById("lessonExcess").setAttribute("aria-pressed","false");
   document.getElementById("lessonMedium").value="";
   lessonUpdateMedium();
   lessonRenderExperiment();
   lessonShowSuggestions(slot,input.value);
  };
  input.onfocus=()=>{input.select();if(input.value.trim())lessonShowSuggestions(slot,input.value);};
  input.onkeydown=event=>{
   if(event.key==="Escape"){lessonCloseSuggestions(slot);return;}
   if(event.key==="ArrowDown"||event.key==="ArrowUp"){
    event.preventDefault();
    if(document.getElementById("lessonSuggestions"+label).hidden)lessonShowSuggestions(slot,input.value);
    const num=lessonSuggestionIndex[slot];
    lessonHighlightSuggestion(slot,event.key==="ArrowDown"?num+1:num-1);
   }
   if(event.key==="Enter"){
    event.preventDefault();
    const n=lessonSuggestionIndex[slot];
    const found=lessonSuggested[slot][n>=0?n:0];
    if(found)lessonSetReagent(slot,found[0]);
    else lessonCloseSuggestions(slot);
   }
  };
 }
 document.addEventListener("pointerdown",event=>{
  if(!event.target.closest(".lesson-search-field")){
    lessonCloseSuggestions("a");lessonCloseSuggestions("b");
  }
 });
 if(data.reagents.kmno4)lessonSetReagent("a","kmno4");
 if(data.reagents.na2so3)lessonSetReagent("b","na2so3");
 lessonUpdateMedium();
 lessonRenderExperiment();
}
function lessonSyncHeatHint(){
 let pending=null;
 if(!lessonHeated){
  const {a,b}=lessonSelectedReagents,medium=document.getElementById("lessonMedium").value;
  const choices=(lessonChain?lessonChain.available:[a]).filter(id=>id&&b&&id!==b)
   .map(id=>lessonSelectedReaction(id,b,lessonHeated,medium,lessonExcess)).filter(rx=>rx&&rx.t!=="z");
  // Do not require heating when a valid room-temperature pathway exists.
  if(!choices.some(rx=>!rx.heat))pending=choices.find(rx=>rx.heat)||null;
 }
 syncHeatHint("lessonHeat","lessonHeatHint",pending,lessonHeated,true);
}
function lessonRenderExperiment(){
 lessonSyncIndicators();lessonSyncHeatHint();
 const a=lessonSelectedReagents.a;
 const b=lessonSelectedReagents.b;
 const history=document.getElementById("lessonChainHistory");
 if(lessonChain){
  const last=lessonChain.steps[lessonChain.steps.length-1].reaction;
  // Gas escaped from this open tube; once a new reagent is tested it must
  // not keep bubbling as if the previous reaction were still underway.
  const visual=lessonChain.noReactionNotice?{...last,gas:""}:last;
  lessonRenderTubePair();
  const info=document.getElementById("lessonReaction");
  info.innerHTML=lessonChain.noReactionNotice?
   '<div class="chain-no-reaction">⛔ Нет подтверждённой реакции с оставшимися веществами. Предыдущие продукты сохраняются; выделившийся газ не участвует в следующем этапе.</div>':
   reactionResultHTML(last,true);
  history.hidden=false;
  history.innerHTML='<details class="chain-history" open><summary>Цепочка: '+chainStepLabel(lessonChain.steps.length)+'</summary>'+lessonChain.steps.map((step,n)=>'<div class="reaction-equation">'+(n+1)+'. '+task6Esc(step.reaction.eq)+'</div>'+chainUntrackedNotice(step)).join('')+'<small>Цепочка качественная: количества реагентов не рассчитываются.</small></details>';
  return;
 }
 history.hidden=true;
 const mediumSelect=document.getElementById("lessonMedium");
 const mediumRequired=lessonHasMedium(a,b);
 const x=lessonStarted&&a&&b?lessonSelectedReaction(a,b,lessonHeated):null;
 const visualReaction=x&&x.heat&&!lessonHeated?null:x;
 const v=lessonStarted&&visualReaction?[a,b]:(a?[a]:[]);
 const lessonVisual=lessonDissolving?findReaction(a,b,lessonHeated):visualReaction;
 lessonRenderTubePair();
 const info=document.getElementById("lessonReaction");
 if(!a||!b){info.textContent="Выбери оба реактива.";return;}
 if(mediumRequired&&!mediumSelect.value){info.textContent="Выбери среду реакции, затем нажми «Провести».";return;}
 if(!lessonStarted){info.textContent="Готово к опыту. Веди запись реакции справа и нажми «Провести».";return;}
 if(x){
  info.innerHTML=reactionResultHTML(x,lessonHeated);
 }else{
  info.textContent="Для этой пары и выбранной среды нет подтверждённой реакции. Продукт не выдумываем.";
 }
}
function lessonConductStep(){
 const {a,b}=lessonSelectedReagents;
 const info=document.getElementById("lessonReaction");
 if(!a&&!lessonChain){info.textContent="Выбери первый реактив.";return;}
 if(!b){info.textContent="Выбери следующий реактив.";return;}
 if(!lessonChain){
  lessonStarted=true;
  const rx=lessonSelectedReaction(a,b,lessonHeated);
  if(rx&&rx.t!=="z"&&(!rx.heat||lessonHeated)){
   const details=chainProductDetails(rx),products=details.ids;
   if(products.length)lessonChain={available:products,ids:[a,b],steps:[{reaction:rx,reactant:a,reagent:b,untracked:details.untracked}]};
  }
  lessonRenderExperiment();
  return;
 }
 if(!b){info.textContent="Выбери следующий реактив.";return;}
 const medium=document.getElementById("lessonMedium").value;
 const options=lessonChain.available.filter(id=>id!==b).map(id=>{
  const requiresMedium=lessonHasMedium(id,b);
  const rx=lessonSelectedReaction(id,b,lessonHeated,medium,lessonExcess);
  return {id,rx,requiresMedium};
 });
 // Several products can coexist. A medium-dependent possibility must not
 // block a different, already-confirmed reaction that needs no medium.
 const readyWithoutMedium=options.some(x=>!x.requiresMedium&&x.rx&&x.rx.t!=="z");
 if(!medium&&!readyWithoutMedium&&options.some(x=>x.requiresMedium)){
  info.textContent="Выбери среду реакции перед продолжением опыта.";return;
 }
 const pendingHeat=options.some(x=>x.rx&&x.rx.t!=="z"&&x.rx.heat&&!lessonHeated);
 const matches=options.filter(x=>x.rx&&x.rx.t!=="z"&&(!x.rx.heat||lessonHeated));
 if(!matches.length){
  if(pendingHeat){info.textContent="Для следующего этапа нужен нагрев 🔥";return;}
  if(tubeIsLiquid(b))lessonMotion.extraPours=(lessonMotion.extraPours||0)+1;
  lessonChain.noReactionNotice=true;lessonRenderExperiment();return;
 }
 const advance=choice=>{
  const details=chainProductDetails(choice.rx),products=details.ids;
  if(!products.length){info.textContent="Продукты этой реакции пока не распознаны.";return;}
  const rest=lessonChain.available.filter(id=>id!==choice.id&&id!==b);
  lessonChain.available=[...new Set([...rest,...products])];
  lessonChain.ids.push(b);
  lessonChain.steps.push({reaction:choice.rx,reactant:choice.id,reagent:b,untracked:details.untracked});
  lessonChain.noReactionNotice=false;
  lessonSelectedReagents.b="";
  document.getElementById("lessonReagentB").value="";
  lessonRenderExperiment();
 };
 if(matches.length===1){advance(matches[0]);return;}
 info.replaceChildren();
 const intro=document.createElement("p");intro.textContent="В смеси несколько возможных продуктов. Выбери, какой реагирует дальше:";info.appendChild(intro);
 matches.forEach(choice=>{
  const button=document.createElement("button");button.type="button";
  button.textContent=reagent(choice.id)[0]+" — "+choice.rx.eq;
  button.onclick=()=>advance(choice);
  info.appendChild(button);
 });
}
// Independent, scrollable lesson board. Presentation pages and their notes
// stay untouched when switching modes; export deliberately uses the board's
// own canvas and never replaces the imported source PDF.
let lessonBoardMode=false,lessonBoardTool="pen",lessonBoardItems=[],lessonBoardStrokes=[];
let lessonBoardSelection=null,lessonBoardPointer=null,lessonBoardUndoStack=[];
let lessonBoardView={x:0,y:0,zoom:1};
let lessonBoardFrame=0,lessonBoardFitMode=null;
function lessonBoardScheduleDraw(){if(!lessonBoardFrame)lessonBoardFrame=requestAnimationFrame(()=>{lessonBoardFrame=0;lessonBoardDraw();});}
let lessonBoardPageIndex=0,lessonBoardPages=[{name:"Лист 1",items:[],strokes:[]}];
function lessonBoardStoreCurrent(){
 lessonBoardPages[lessonBoardPageIndex].view={...lessonBoardView};
 lessonBoardPages[lessonBoardPageIndex].items=lessonBoardItems;
 lessonBoardPages[lessonBoardPageIndex].strokes=lessonBoardStrokes;
}
function lessonBoardRefreshPages(){
 const select=document.getElementById("lessonBoardPages");
 select.replaceChildren();
 lessonBoardPages.forEach((page,index)=>{
  const option=document.createElement("option");option.value=String(index);option.textContent=page.name;
  select.appendChild(option);
 });
 select.value=String(lessonBoardPageIndex);
 lessonBoardRefreshNavigation();
}
function lessonBoardSwitchPage(index){
 if(!Number.isInteger(index)||index<0||index>=lessonBoardPages.length)return;
 lessonBoardFitMode=null;lessonBoardStoreCurrent();lessonBoardPageIndex=index;
 lessonBoardItems=lessonBoardPages[index].items;
 lessonBoardStrokes=lessonBoardPages[index].strokes;
 lessonBoardView={x:0,y:0,zoom:1,...lessonBoardPages[index].view};
 lessonBoardUndoStack=[];lessonBoardSelection=null;lessonBoardPointer=null;
 lessonBoardRefreshPages();lessonBoardDraw();
 if(!lessonBoardPages[index].view&&lessonBoardItems.length)lessonBoardFit("document");
 lessonStatus("Открыт лист «"+lessonBoardPages[index].name+"». Другие листы сохранены.");
}
function lessonBoardImageData(image){
 if(!image?.complete||!image.naturalWidth)throw Error("image-not-ready");
 const max=2200,scale=Math.min(1,max/Math.max(image.naturalWidth,image.naturalHeight));
 const canvas=document.createElement("canvas");
 canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));
 canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));
 canvas.getContext("2d").drawImage(image,0,0,canvas.width,canvas.height);
 return canvas.toDataURL("image/png");
}
function lessonBoardLoadImage(data){
 if(typeof data!=="string"||!/^data:image\/(png|jpeg|webp);base64,/i.test(data))throw Error("image-format");
 return new Promise((resolve,reject)=>{
  const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(Error("image-load"));image.src=data;
 });
}
async function lessonBoardImportPDF(file){
 if(!file)return;
 if(file.size>25*1024*1024){lessonStatus("PDF больше 25 МБ — выбери файл поменьше.");return;}
 let pdf=null;
 try{
  lessonStatus("Подготавливаю слайды PDF для свободной доски...");
  const reader=await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs");
  reader.GlobalWorkerOptions.workerSrc="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";
  pdf=await reader.getDocument({data:new Uint8Array(await file.arrayBuffer()),isEvalSupported:false}).promise;
  if(pdf.numPages>20||lessonBoardPages.length+pdf.numPages>40){
   lessonStatus("Можно добавить не более 20 слайдов за раз и максимум 40 листов на доску.");return;
  }
  // Render everything before modifying the current project, so a bad PDF
  // cannot leave the user's board half-imported.
  const newPages=[],documentId="pdf-"+Date.now()+"-"+Math.random().toString(36).slice(2);
  for(let index=1;index<=pdf.numPages;index++){
   const page=await pdf.getPage(index),natural=page.getViewport({scale:1});
   const viewport=page.getViewport({scale:Math.min(2,1650/natural.width,1350/natural.height)});
   const bitmap=document.createElement("canvas");
   bitmap.width=Math.ceil(viewport.width);bitmap.height=Math.ceil(viewport.height);
   const ctx=bitmap.getContext("2d",{alpha:false});ctx.fillStyle="#fff";ctx.fillRect(0,0,bitmap.width,bitmap.height);
   await page.render({canvasContext:ctx,viewport}).promise;
   const image=await lessonBoardLoadImage(bitmap.toDataURL("image/jpeg",.94));
   const w=Math.min(1700,image.naturalWidth),h=w*image.naturalHeight/image.naturalWidth;
   newPages.push({name:file.name.replace(/\.pdf$/i,"").slice(0,44)+" · "+index,
    document:{id:documentId,title:file.name.slice(0,80),page:index,total:pdf.numPages},
    items:[{image,x:Math.round((2400-w)/2),y:Math.max(35,Math.round((1600-h)/2)),w,h,locked:true}],strokes:[]});
   bitmap.width=bitmap.height=0;
  }
  lessonBoardStoreCurrent();
  const first=lessonBoardPages.length;lessonBoardPages.push(...newPages);
  lessonBoardSwitchPage(first);
  lessonBoardSetTool("pen");
  lessonStatus("PDF открыт на доске. Листай стрелками рядом с номером страницы; увеличивай кнопками ＋ / − или двумя пальцами.");
 }catch(err){lessonStatus("Не удалось вставить PDF на доску. Проверь формат файла и соединение.");}
 finally{try{await pdf?.destroy();}catch(err){}}
}
function lessonBoardValidNumber(value,min,max){
 return typeof value==="number"&&Number.isFinite(value)&&value>=min&&value<=max;
}
function lessonBoardSerializeProject(){
 lessonBoardStoreCurrent();
 const pages=lessonBoardPages.map(page=>({name:page.name,view:page.view,document:page.document,
  strokes:page.strokes.map(stroke=>({...((stroke.renderVersion===2)?{renderVersion:2}:{}),color:stroke.color,width:stroke.width,opacity:stroke.opacity,points:stroke.points.map(p=>({x:p.x,y:p.y}))})),
  items:page.items.map(item=>({x:item.x,y:item.y,w:item.w,h:item.h,locked:item.locked===true,image:lessonBoardImageData(item.image)}))}));
 return JSON.stringify({format:"ege-blizko-board",version:2,width:2400,height:1600,activePage:lessonBoardPageIndex,pages});
}
async function lessonBoardSaveProject(){
 try{
  const content=lessonBoardSerializeProject();
  lessonDownload(content,"ЕГЭ_БЛИЗКО_проект_доски.json","application/json");
  lessonStatus("Проект скачан: его можно снова открыть и редактировать. PDF сохраняется отдельно.");
 }catch(err){lessonStatus("Не удалось сохранить проект. Проверь загруженные изображения.");}
}
async function lessonBoardOpenProject(file){
 if(!file)return;
 if(file.size>55*1024*1024){lessonStatus("Проект больше 55 МБ — файл не загружен.");return;}
 try{
  const data=JSON.parse(await file.text());
  if(data.format!=="ege-blizko-board"||![1,2].includes(data.version)||data.width!==2400||data.height!==1600||
     !Array.isArray(data.pages)||data.pages.length<1||data.pages.length>40)throw Error("bad-format");
  const pages=[];let imageCount=0,pointCount=0;
  for(const page of data.pages){
   if(typeof page.name!=="string"||page.name.length>65||!Array.isArray(page.items)||!Array.isArray(page.strokes)||
      page.items.length>100||page.strokes.length>5000)throw Error("bad-page");
   const items=[];
   for(const item of page.items){
    if(++imageCount>200||!lessonBoardValidNumber(item.x,-10000000,10000000)||!lessonBoardValidNumber(item.y,-10000000,10000000)||
       !lessonBoardValidNumber(item.w,1,2400)||!lessonBoardValidNumber(item.h,1,2400))throw Error("bad-image");
    items.push({x:item.x,y:item.y,w:item.w,h:item.h,locked:item.locked===true,image:await lessonBoardLoadImage(item.image)});
   }
   const strokes=page.strokes.map(stroke=>{
    if(!/^#[0-9a-f]{6}$/i.test(stroke.color)||!lessonBoardValidNumber(stroke.width,.1,100)||
       !lessonBoardValidNumber(stroke.opacity,0,1)||!Array.isArray(stroke.points)||stroke.points.length>30000)throw Error("bad-stroke");
    pointCount+=stroke.points.length;if(pointCount>500000)throw Error("too-many-points");
    const points=stroke.points.map(p=>{
     if(!lessonBoardValidNumber(p.x,-10000000,10000000)||!lessonBoardValidNumber(p.y,-10000000,10000000))throw Error("bad-point");
     return {x:p.x,y:p.y};
    });
    return {...((stroke.renderVersion===2)?{renderVersion:2}:{}),color:stroke.color,width:stroke.width,opacity:stroke.opacity,points};
   });
   const view=page.view||{x:0,y:0,zoom:1};
   if(!lessonBoardValidNumber(view.x,-10000000,10000000)||!lessonBoardValidNumber(view.y,-10000000,10000000)||!lessonBoardValidNumber(view.zoom,.1,4))throw Error("bad-view");
   const doc=page.document;
   if(doc&&(typeof doc.id!=="string"||doc.id.length>128||typeof doc.title!=="string"||doc.title.length>80||!Number.isInteger(doc.page)||!Number.isInteger(doc.total)||doc.page<1||doc.page>doc.total||doc.total>20))throw Error("bad-document");
   pages.push({name:page.name||"Без названия",items,strokes,view,document:doc?{id:doc.id,title:doc.title,page:doc.page,total:doc.total}:undefined});
  }
  // Only replace the current board after the entire file has been validated.
  lessonBoardPages=pages;lessonBoardPageIndex=0;lessonBoardItems=pages[0].items;lessonBoardStrokes=pages[0].strokes;
  lessonBoardView={...pages[0].view};
  lessonBoardSelection=null;lessonBoardUndoStack=[];lessonBoardPointer=null;
  lessonBoardSwitchPage(Number.isInteger(data.activePage)?Math.min(pages.length-1,Math.max(0,data.activePage)):0);
  lessonStatus("Проект открыт. Все листы, изображения и записи снова доступны для редактирования.");
  return true;
 }catch(err){lessonStatus("Не удалось открыть проект: файл повреждён или не подходит к этой доске. Текущая работа сохранена.");}
}
function lessonBoardSnapshot(){
 lessonBoardUndoStack.push({items:lessonBoardItems.map(x=>({...x})),strokes:lessonBoardStrokes.map(x=>({...x,points:x.points.map(p=>({...p}))}))});
 if(lessonBoardUndoStack.length>35)lessonBoardUndoStack.shift();
}
// Scene coordinates are independent of viewport pixels; panning never allocates
// an enormous bitmap. Only the visible area is rendered, including negative space.
function lessonBoardPaint(ctx,width,height,view,selection=true,scene={items:lessonBoardItems,strokes:lessonBoardStrokes},pixelRatio=1){
 ctx.save();ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);ctx.globalAlpha=1;
 ctx.fillStyle="#fffdfa";ctx.fillRect(0,0,width,height);
 ctx.translate(-view.x*view.zoom,-view.y*view.zoom);ctx.scale(view.zoom,view.zoom);
 ctx.strokeStyle="#e9dfe5";ctx.lineWidth=1/view.zoom;
 const right=view.x+width/view.zoom,bottom=view.y+height/view.zoom;
 const grid=26*Math.max(1,Math.ceil(8/(26*view.zoom)));
 for(let x=Math.floor(view.x/grid)*grid;x<right;x+=grid){ctx.beginPath();ctx.moveTo(x,view.y);ctx.lineTo(x,bottom);ctx.stroke();}
 for(let y=Math.floor(view.y/grid)*grid;y<bottom;y+=grid){ctx.beginPath();ctx.moveTo(view.x,y);ctx.lineTo(right,y);ctx.stroke();}
 for(const item of scene.items){
  if(item.image?.complete&&item.image.naturalWidth)ctx.drawImage(item.image,item.x,item.y,item.w,item.h);
  if(selection&&item===lessonBoardSelection&&lessonBoardTool==="move"){
   ctx.strokeStyle="#f00087";ctx.lineWidth=2/view.zoom;ctx.strokeRect(item.x,item.y,item.w,item.h);
  }
 }
 for(const stroke of scene.strokes)lessonBoardPaintStroke(ctx,stroke);
 ctx.restore();
}
function lessonBoardPaintStroke(ctx,stroke){
  const pts=lessonStrokePoints(stroke);if(!pts.length)return;
  ctx.beginPath();ctx.lineWidth=stroke.width;ctx.lineCap="round";ctx.lineJoin="round";
  ctx.strokeStyle=stroke.color;ctx.globalAlpha=stroke.opacity;
  ctx.moveTo(pts[0].x,pts[0].y);
  for(const p of pts.slice(1))ctx.lineTo(p.x,p.y);
  if(pts.length===1)ctx.lineTo(pts[0].x+.01,pts[0].y+.01);
  ctx.stroke();ctx.globalAlpha=1;
}
let lessonBoardInkCache=null;
function lessonBoardDraw(){
 lessonBoardQueueRecovery();
 const canvas=document.getElementById("lessonBoardCanvas"),space=document.getElementById("lessonBoardSpace");
 if(space.hidden)return;
 const width=Math.max(1,space.clientWidth),height=Math.max(1,space.clientHeight);
 const pixelRatio=Math.min(window.devicePixelRatio||1,2);
 const backingWidth=Math.round(width*pixelRatio),backingHeight=Math.round(height*pixelRatio);
 if(canvas.width!==backingWidth)canvas.width=backingWidth;if(canvas.height!==backingHeight)canvas.height=backingHeight;
 canvas.style.width=width+"px";canvas.style.height=height+"px";
 const ctx=canvas.getContext("2d"),active=lessonBoardPointer?.kind==="draw"?lessonBoardPointer.stroke:null;
 if(active){
  const key=[width,height,pixelRatio,lessonBoardView.x,lessonBoardView.y,lessonBoardView.zoom].join(":");
  if(!lessonBoardInkCache||lessonBoardInkCache.stroke!==active||lessonBoardInkCache.key!==key){
   const bitmap=document.createElement("canvas");bitmap.width=backingWidth;bitmap.height=backingHeight;
   lessonBoardPaint(bitmap.getContext("2d"),width,height,lessonBoardView,false,{items:lessonBoardItems,strokes:lessonBoardStrokes.filter(stroke=>stroke!==active)},pixelRatio);
   lessonBoardInkCache={bitmap,stroke:active,key};
  }
  ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(lessonBoardInkCache.bitmap,0,0);
  ctx.save();ctx.setTransform(pixelRatio,0,0,pixelRatio,0,0);ctx.translate(-lessonBoardView.x*lessonBoardView.zoom,-lessonBoardView.y*lessonBoardView.zoom);ctx.scale(lessonBoardView.zoom,lessonBoardView.zoom);
  lessonBoardPaintStroke(ctx,active);ctx.restore();
 }else{
  lessonBoardInkCache=null;lessonBoardPaint(ctx,width,height,lessonBoardView,true,undefined,pixelRatio);
 }
 document.getElementById("lessonBoardZoom").textContent=Math.round(lessonBoardView.zoom*100)+"%";
 lessonBoardRefreshNavigation();
}
function lessonBoardPageGroup(){
 const doc=lessonBoardPages[lessonBoardPageIndex].document;
 return lessonBoardPages.map((page,index)=>({page,index})).filter(entry=>!doc||entry.page.document?.id===doc.id).map(entry=>entry.index);
}
function lessonBoardRefreshNavigation(){
 const group=lessonBoardPageGroup(),position=group.indexOf(lessonBoardPageIndex);
 document.getElementById("lessonBoardPageCounter").textContent=(position+1)+" / "+group.length;
 document.getElementById("lessonBoardDocumentName").textContent=lessonBoardPages[lessonBoardPageIndex].document?.title||"Листы доски";
 document.getElementById("lessonBoardPrevious").disabled=position<=0;
 document.getElementById("lessonBoardNext").disabled=position>=group.length-1;
 document.getElementById("lessonBoardDocument").disabled=!lessonBoardItems.length;
}
function lessonBoardTurnPage(direction){
 const group=lessonBoardPageGroup(),position=group.indexOf(lessonBoardPageIndex);
 if(group[position+direction]!==undefined)lessonBoardSwitchPage(group[position+direction]);
}
function lessonBoardZoomTo(zoom,anchor=null,screen=null){
 lessonBoardFitMode=null;
 const space=document.getElementById("lessonBoardSpace");
 screen=screen||{x:space.clientWidth/2,y:space.clientHeight/2};
 anchor=anchor||{x:lessonBoardView.x+screen.x/lessonBoardView.zoom,y:lessonBoardView.y+screen.y/lessonBoardView.zoom};
 zoom=Math.max(.1,Math.min(4,zoom));
 lessonBoardView={x:anchor.x-screen.x/zoom,y:anchor.y-screen.y/zoom,zoom};lessonBoardDraw();
}
function lessonBoardFit(kind){
 const space=document.getElementById("lessonBoardSpace");
 const items=kind==="document"?[lessonBoardSelection||lessonBoardItems.find(item=>item.locked)||lessonBoardItems[0]].filter(Boolean):lessonBoardItems;
 const bounds=[];
 for(const item of items)bounds.push({x:item.x,y:item.y},{x:item.x+item.w,y:item.y+item.h});
 if(kind!=="document")for(const stroke of lessonBoardStrokes)for(const point of stroke.points)bounds.push({x:point.x-stroke.width,y:point.y-stroke.width},{x:point.x+stroke.width,y:point.y+stroke.width});
 if(!bounds.length){lessonBoardView={x:0,y:0,zoom:1};lessonBoardDraw();return;}
 let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
 for(const point of bounds){left=Math.min(left,point.x);top=Math.min(top,point.y);right=Math.max(right,point.x);bottom=Math.max(bottom,point.y);}
 const zoom=Math.min((Math.max(1,space.clientWidth-48))/Math.max(1,right-left),(Math.max(1,space.clientHeight-48))/Math.max(1,bottom-top));
 lessonBoardZoomTo(zoom,{x:(left+right)/2,y:(top+bottom)/2});lessonBoardFitMode=kind;
}
function lessonBoardPoint(event){
 const rect=document.getElementById("lessonBoardCanvas").getBoundingClientRect();
 return {x:lessonBoardView.x+(event.clientX-rect.left)/lessonBoardView.zoom,
         y:lessonBoardView.y+(event.clientY-rect.top)/lessonBoardView.zoom};
}
function lessonBoardErase(point){
 const radius=14/lessonBoardView.zoom;
 lessonBoardStrokes=lessonBoardStrokes.filter(stroke=>!stroke.points.some((p,i,pts)=>{
  const a=pts[Math.max(0,i-1)],dx=p.x-a.x,dy=p.y-a.y;
  const t=Math.max(0,Math.min(1,((point.x-a.x)*dx+(point.y-a.y)*dy)/(dx*dx+dy*dy||1)));
  return Math.hypot(point.x-a.x-t*dx,point.y-a.y-t*dy)<=radius+stroke.width/2;
 }));
}
function lessonBoardSetTool(tool){
 lessonBoardTool=tool;
 if(tool!=="pen"){document.querySelector("#lesson .lesson-extra-menu").open=false;lessonLineMode=false;document.getElementById("lessonStraightLine").setAttribute("aria-pressed","false");}
 document.getElementById("lessonBoardLine").setAttribute("aria-pressed",String(tool==="pen"&&lessonLineMode));
 document.getElementById("lessonBoardMarker").setAttribute("aria-pressed",String(tool==="pen"&&lessonTool==="marker"&&!lessonLineMode));
 document.getElementById("lessonBoardPan").setAttribute("aria-pressed",String(tool==="pan"));
 document.getElementById("lessonBoardPen").setAttribute("aria-pressed",String(tool==="pen"&&lessonTool==="pen"&&!lessonLineMode));
 document.getElementById("lessonBoardEraser").setAttribute("aria-pressed",String(tool==="pen"&&lessonTool==="erase"));
 document.getElementById("lessonBoardMove").setAttribute("aria-pressed",String(tool==="move"));
 document.getElementById("lessonBoardCanvas").style.cursor=(tool==="move"||tool==="pan")?"grab":"crosshair";
 lessonBoardDraw();
}
function lessonBoardToggle(target){
 const next=typeof target==="boolean"?target:!lessonBoardMode;
 if(next===lessonBoardMode)return;
 lessonPresentationSetFullscreen(false);
 lessonBoardMode=next;
 if(!lessonBoardMode)lessonBoardSetFullscreen(false);
 document.getElementById("lessonPaperSpace").hidden=lessonBoardMode;
 document.getElementById("lessonBoardSpace").hidden=!lessonBoardMode;
 document.getElementById("lessonBoardBar").hidden=!lessonBoardMode;
 document.querySelector("#lesson .lesson-pdf-pane").classList.toggle("lesson-board-active",lessonBoardMode);
 document.getElementById("lessonBoardToggle").setAttribute("aria-pressed",String(lessonBoardMode));
 document.getElementById("lessonPresentationTab").setAttribute("aria-pressed",String(!lessonBoardMode));
 if(lessonBoardMode)lessonSyncInkTools();else lessonRenderPage();
 lessonStatus(lessonBoardMode?"Свободная доска открыта. Презентация и записи сохранены отдельно.":"Презентация с прежними пометками открыта.");
}
function lessonPresentationSetFullscreen(enabled){
 const studio=document.querySelector("#lesson .lesson-studio");if(!studio)return;
 const active=!!enabled&&!lessonBoardMode;
 studio.classList.toggle("presentation-fullscreen",active);
 document.body.classList.toggle("lesson-presentation-fullscreen",active);
 const button=document.getElementById("lessonPresentationFullscreen");
 document.getElementById("lessonPresentationExit").hidden=!active;
 button.setAttribute("aria-pressed",String(active));
 button.querySelector("span").textContent=active?"Вернуть лабораторию":"На весь экран";
 lessonRenderPage();
}
function lessonBoardSetFullscreen(enabled){
 const studio=document.querySelector("#lesson .lesson-studio");
 if(!studio)return;
 const fullscreen=!!enabled&&lessonBoardMode;
 studio.classList.toggle("board-fullscreen",fullscreen);
 document.body.classList.toggle("lesson-board-fullscreen",fullscreen);
 const button=document.getElementById("lessonBoardFullscreen");
 button.setAttribute("aria-pressed",String(fullscreen));
 button.innerHTML='<svg class="lesson-control-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3H3v6M15 3h6v6M3 15v6h6M21 15v6h-6"/></svg>'+"<span>"+(fullscreen?"Вернуть лабораторию":"На весь экран")+"</span>";
 lessonBoardDraw();
}
let lessonBoardRecoveryDB=null,lessonBoardRecoveryTimer=0,lessonBoardRecoveryPending=false;
let lessonBoardRecoveryRevision=0,lessonBoardRecoveryContent="",lessonBoardRecoveryBusy=false,lessonBoardRecoveryDirty=false;
const lessonBoardRecoveryKey=()=>"board:"+String(data?.pilot_user||"local-preview");
function lessonBoardRecoveryStatus(text){const el=document.getElementById("lessonBoardSaveState");if(el)el.textContent=text;}
function lessonBoardRecoveryRead(){return new Promise((resolve,reject)=>{
 const tx=lessonBoardRecoveryDB.transaction("boards","readonly"),request=tx.objectStore("boards").get(lessonBoardRecoveryKey());
 request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
});}
function lessonBoardQueueRecovery(){
 if(!lessonBoardRecoveryDB||lessonBoardRecoveryPending)return;
 lessonBoardRecoveryDirty=true;clearTimeout(lessonBoardRecoveryTimer);
 lessonBoardRecoveryTimer=setTimeout(lessonBoardFlushRecovery,650);
}
async function lessonBoardFlushRecovery(){
 clearTimeout(lessonBoardRecoveryTimer);
 if(!lessonBoardRecoveryDB||lessonBoardRecoveryPending||lessonBoardRecoveryBusy||!lessonBoardRecoveryDirty)return;
 lessonBoardRecoveryBusy=true;lessonBoardRecoveryDirty=false;
 try{
  const content=lessonBoardSerializeProject();
  if(content.length>55*1024*1024)throw Error("size");
  if(content===lessonBoardRecoveryContent)return;
  lessonBoardRecoveryStatus("Доска: сохраняем локально…");
  const revision=lessonBoardRecoveryRevision+1;
  await new Promise((resolve,reject)=>{
   const tx=lessonBoardRecoveryDB.transaction("boards","readwrite"),store=tx.objectStore("boards");
   const request=store.get(lessonBoardRecoveryKey());let conflict=false;
   request.onsuccess=()=>{
    if((request.result?.revision||0)!==lessonBoardRecoveryRevision){conflict=true;tx.abort();return;}
    store.put({revision,content,savedAt:Date.now()},lessonBoardRecoveryKey());
   };
   tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error||Error("storage"));
   tx.onabort=()=>reject(Error(conflict?"conflict":"storage"));
  });
  lessonBoardRecoveryRevision=revision;lessonBoardRecoveryContent=content;
  lessonBoardRecoveryStatus("Доска сохранена в этом браузере");
 }catch(err){
  if(err.message==="conflict")lessonBoardRecoveryPending=true;
  lessonBoardRecoveryStatus(err.message==="conflict"?"Доска изменена в другой вкладке — сохраните свой проект отдельно":"Доска не сохранена — скачайте проект");
 }finally{lessonBoardRecoveryBusy=false;if(lessonBoardRecoveryDirty)lessonBoardQueueRecovery();}
}
async function lessonBoardSetupRecovery(){
 if(!data?.preview)return;
 try{
  lessonBoardRecoveryDB=await new Promise((resolve,reject)=>{
   const request=indexedDB.open("ege-blizko-board-recovery",1);
   request.onupgradeneeded=()=>request.result.createObjectStore("boards");
   request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
   request.onblocked=()=>reject(Error("blocked"));
  });
  const saved=await lessonBoardRecoveryRead();
  lessonBoardRecoveryRevision=saved?.revision||0;
  lessonBoardRecoveryPending=!!saved;
  const recover=document.getElementById("lessonBoardRecover"),fresh=document.getElementById("lessonBoardStartNew");
  recover.hidden=fresh.hidden=!saved;
  if(saved){
   lessonBoardRecoveryStatus("Найдена локальная копия доски — можно восстановить");
   recover.onclick=async()=>{
    if(!window.confirm("Восстановить локальную копию? Текущая доска будет заменена. При необходимости сначала скачайте её проект."))return;
    const restored=await lessonBoardOpenProject(new File([saved.content],"recovery.json",{type:"application/json"}));
    if(restored){lessonBoardRecoveryContent=saved.content;lessonBoardRecoveryPending=false;recover.hidden=fresh.hidden=true;lessonBoardRecoveryStatus("Доска восстановлена из локальной копии");lessonBoardQueueRecovery();}
    else lessonBoardRecoveryStatus("Копия повреждена — текущая доска не заменена");
   };
   fresh.onclick=()=>{
    if(!window.confirm("Заменить локальную копию текущей доской? Старую копию после этого восстановить нельзя."))return;
    lessonBoardRecoveryPending=false;recover.hidden=fresh.hidden=true;lessonBoardQueueRecovery();
   };
  }else{lessonBoardRecoveryStatus("Доска: локальная копия будет сохранена после изменения");}
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="hidden")lessonBoardFlushRecovery();});
  window.addEventListener("pagehide",()=>lessonBoardFlushRecovery());
 }catch(err){lessonBoardRecoveryStatus("Локальная копия доски недоступна — скачивайте проект");}
}
function lessonBoardSetup(){
 lessonBoardSetupRecovery();
 const canvas=document.getElementById("lessonBoardCanvas");
 new ResizeObserver(()=>{if(lessonBoardFitMode&&lessonBoardMode)lessonBoardFit(lessonBoardFitMode);else lessonBoardScheduleDraw();}).observe(document.getElementById("lessonBoardSpace"));
 document.getElementById("lessonBoardPan").onclick=()=>lessonBoardSetTool("pan");
 document.getElementById("lessonBoardZoomIn").onclick=()=>lessonBoardZoomTo(lessonBoardView.zoom*1.25);
 document.getElementById("lessonBoardZoomOut").onclick=()=>lessonBoardZoomTo(lessonBoardView.zoom/1.25);
 document.getElementById("lessonBoardZoom").onclick=()=>lessonBoardZoomTo(1);
 document.getElementById("lessonBoardFit").onclick=()=>lessonBoardFit("all");
 document.getElementById("lessonBoardDocument").onclick=()=>lessonBoardFit("document");
 document.getElementById("lessonBoardPrevious").onclick=()=>lessonBoardTurnPage(-1);
 document.getElementById("lessonBoardNext").onclick=()=>lessonBoardTurnPage(1);
 document.getElementById("lessonBoardHome").onclick=()=>{lessonBoardFitMode=null;lessonBoardView={x:0,y:0,zoom:1};lessonBoardDraw();};
 canvas.addEventListener("wheel",event=>{
  lessonBoardFitMode=null;event.preventDefault();
  if(event.ctrlKey||event.metaKey){
   const anchor=lessonBoardPoint(event),old=lessonBoardView.zoom;
   const zoom=Math.max(.1,Math.min(4,old*Math.exp(-Math.max(-1000,Math.min(1000,event.deltaY))*.002)));
   lessonBoardView.x=anchor.x-(anchor.x-lessonBoardView.x)*old/zoom;
   lessonBoardView.y=anchor.y-(anchor.y-lessonBoardView.y)*old/zoom;
   lessonBoardView.zoom=zoom;
  }else{lessonBoardView.x+=event.deltaX/lessonBoardView.zoom;lessonBoardView.y+=event.deltaY/lessonBoardView.zoom;}
  lessonBoardScheduleDraw();
 },{passive:false});
 document.getElementById("lessonBoardImageSize").addEventListener("pointerdown",lessonBoardSnapshot);
 document.getElementById("lessonBoardImageSize").addEventListener("keydown",event=>{if(event.key.startsWith("Arrow"))lessonBoardSnapshot();});
 document.getElementById("lessonPresentationExit").onclick=()=>lessonPresentationSetFullscreen(false);
 document.getElementById("lessonPresentationFullscreen").onclick=()=>lessonPresentationSetFullscreen(!document.querySelector("#lesson .lesson-studio").classList.contains("presentation-fullscreen"));
 document.getElementById("lessonBoardFullscreen").onclick=()=>lessonBoardSetFullscreen(!document.querySelector("#lesson .lesson-studio")?.classList.contains("board-fullscreen"));
 document.addEventListener("keydown",event=>{
  if(event.key==="Escape"){document.getElementById("lessonBoardMore").open=false;lessonPresentationSetFullscreen(false);}
  if(event.key==="Escape"&&document.querySelector("#lesson .lesson-studio")?.classList.contains("board-fullscreen"))lessonBoardSetFullscreen(false);
 });
 document.getElementById("lessonBoardPDFInput").onchange=async event=>{
  await lessonBoardImportPDF(event.target.files[0]);event.target.value="";
 };
 document.getElementById("lessonBoardSaveProject").onclick=lessonBoardSaveProject;
 document.getElementById("lessonBoardOpenProject").onchange=async event=>{
  const file=event.target.files[0];
  if(file&&window.confirm("Открыть сохранённый проект? Текущая доска будет заменена. Если она нужна, сначала сохрани её."))await lessonBoardOpenProject(file);
  event.target.value="";
 };
 lessonBoardRefreshPages();
 document.getElementById("lessonBoardPages").onchange=event=>lessonBoardSwitchPage(Number(event.target.value));
 document.getElementById("lessonBoardAddPage").onclick=()=>{
  if(lessonBoardPages.length>=40){lessonStatus("Достигнут предел в 40 листов на одну доску.");return;}
  lessonBoardStoreCurrent();
  lessonBoardPages.push({name:"Лист "+(lessonBoardPages.length+1),items:[],strokes:[]});
  lessonBoardSwitchPage(lessonBoardPages.length-1);
 };
 document.getElementById("lessonBoardRenamePage").onclick=()=>{
  const name=window.prompt("Название текущего листа",lessonBoardPages[lessonBoardPageIndex].name);
  if(name===null)return;
  if(!name.trim()){lessonStatus("Название листа не может быть пустым.");return;}
  lessonBoardPages[lessonBoardPageIndex].name=name.trim().slice(0,65);
  lessonBoardRefreshPages();
 };
 document.getElementById("lessonBoardToggle").onclick=()=>lessonBoardToggle(true);
 document.getElementById("lessonPresentationTab").onclick=()=>lessonBoardToggle(false);
 document.getElementById("lessonBoardPen").onclick=()=>lessonSetTool("pen");
 document.getElementById("lessonBoardMarker").onclick=()=>lessonSetTool("marker");
 document.getElementById("lessonBoardLine").onclick=()=>{
  if(lessonTool==="erase")lessonSetTool("pen");lessonSetLineMode(!lessonLineMode);
 };
 document.getElementById("lessonBoardEraser").onclick=()=>lessonSetTool("erase");
 document.getElementById("lessonBoardMove").onclick=()=>lessonBoardSetTool("move");
 document.getElementById("lessonBoardImageInput").onchange=async event=>{
  const file=event.target.files[0];if(!file)return;
  if(file.size>8*1024*1024){lessonStatus("Изображение больше 8 МБ — выбери файл поменьше.");return;}
  const url=URL.createObjectURL(file),img=new Image();
  try{
   await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url;});
   lessonBoardSnapshot();
   const w=Math.min(650,img.naturalWidth),h=w*img.naturalHeight/img.naturalWidth;
   const view=document.getElementById("lessonBoardSpace");
   const x=lessonBoardView.x+60/lessonBoardView.zoom;
   const y=lessonBoardView.y+60/lessonBoardView.zoom;
   lessonBoardSelection={image:img,x,y,w,h};lessonBoardItems.push(lessonBoardSelection);
   document.getElementById("lessonBoardImageSize").value=Math.round(w);
   lessonBoardSetTool("move");lessonStatus("Изображение добавлено. Перетаскивай его по доске.");
  }catch(err){lessonStatus("Не удалось открыть изображение.");}
  finally{URL.revokeObjectURL(url);event.target.value="";}
 };
 document.getElementById("lessonBoardImageSize").oninput=event=>{
  if(!lessonBoardSelection)return;
  const w=Number(event.target.value),ratio=lessonBoardSelection.h/lessonBoardSelection.w;
  lessonBoardSelection.w=w;lessonBoardSelection.h=w*ratio;lessonBoardDraw();
 };
 document.getElementById("lessonBoardUndo").onclick=()=>{
  const previous=lessonBoardUndoStack.pop();if(!previous)return;
  lessonBoardItems=previous.items;lessonBoardStrokes=previous.strokes;lessonBoardSelection=null;lessonBoardDraw();
 };
 const touches=new Map();let pinch=null,touchBlocked=false;
 const touchPair=()=>{const points=[...touches.values()];return {distance:Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y),mid:{x:(points[0].x+points[1].x)/2,y:(points[0].y+points[1].y)/2}};};
 canvas.onpointerdown=event=>{
  if(event.pointerType==="touch"&&lessonBoardPointer?.pointerType==="pen")return;
  if(event.pointerType==="touch"){
   touches.set(event.pointerId,{x:event.clientX,y:event.clientY});
   if(touches.size>=2){
    event.preventDefault();canvas.setPointerCapture(event.pointerId);
    if(touches.size===2){
     if(lessonBoardPointer&&lessonBoardPointer.kind!=="pan"){
      const previous=lessonBoardUndoStack.pop();
      if(previous){lessonBoardItems=previous.items;lessonBoardStrokes=previous.strokes;lessonBoardSelection=null;}
     }
     lessonBoardPointer=null;touchBlocked=true;
     const pair=touchPair(),rect=canvas.getBoundingClientRect();
     pinch={distance:Math.max(1,pair.distance),zoom:lessonBoardView.zoom,anchor:{x:lessonBoardView.x+(pair.mid.x-rect.left)/lessonBoardView.zoom,y:lessonBoardView.y+(pair.mid.y-rect.top)/lessonBoardView.zoom}};
    }
    lessonBoardDraw();return;
   }
   if(touchBlocked)return;
  }
  if(event.button!==0&&event.pointerType==="mouse")return;
  if(lessonBoardPointer)return;
  const p=lessonBoardPoint(event);
  if(lessonBoardTool==="pan"){
   lessonBoardFitMode=null;lessonBoardPointer={kind:"pan",clientX:event.clientX,clientY:event.clientY,x:lessonBoardView.x,y:lessonBoardView.y};
  }else if(lessonBoardTool==="move"){
   lessonBoardSelection=[...lessonBoardItems].reverse().find(item=>!item.locked&&p.x>=item.x&&p.x<=item.x+item.w&&p.y>=item.y&&p.y<=item.y+item.h)||null;
   if(!lessonBoardSelection){lessonBoardDraw();lessonStatus("PDF закреплён под записями. Для увеличения используй ＋ / −, для перемещения — «Перемещать доску».");return;}
   lessonBoardSnapshot();lessonBoardPointer={kind:"move",start:p,x:lessonBoardSelection.x,y:lessonBoardSelection.y};
  }else{
   lessonBoardSnapshot();
   if(lessonTool==="erase"){
    lessonBoardErase(p);lessonBoardPointer={kind:"erase"};
    lessonBoardPointer.pointerType=event.pointerType;lessonBoardPointer.pointerId=event.pointerId;
    event.preventDefault();canvas.setPointerCapture(event.pointerId);lessonBoardDraw();return;
   }
   const marker=lessonTool==="marker",width=Number(document.getElementById("lessonPenWidth").value)||3;
   const stroke={renderVersion:2,color:marker?lessonMarkerColorValue:lessonPenColorValue,width:marker?width*4:width,opacity:marker?.32:1,points:lessonLineMode?[p,p]:[p],straight:lessonLineMode};
   lessonBoardStrokes.push(stroke);lessonBoardPointer={kind:"draw",stroke};
  }
  if(lessonBoardPointer){lessonBoardPointer.pointerType=event.pointerType;lessonBoardPointer.pointerId=event.pointerId;}
  event.preventDefault();canvas.setPointerCapture(event.pointerId);lessonBoardDraw();
 };
 canvas.onpointermove=event=>{
  if(event.pointerType==="touch"&&touches.has(event.pointerId)){
   touches.set(event.pointerId,{x:event.clientX,y:event.clientY});
   if(pinch&&touches.size===2){
    event.preventDefault();const pair=touchPair(),rect=canvas.getBoundingClientRect();
    lessonBoardZoomTo(pinch.zoom*pair.distance/pinch.distance,pinch.anchor,{x:pair.mid.x-rect.left,y:pair.mid.y-rect.top});return;
   }
   if(touchBlocked)return;
  }
  if(!lessonBoardPointer||!canvas.hasPointerCapture(event.pointerId))return;
  const p=lessonBoardPoint(event);
  if(lessonBoardPointer.kind==="pan"){
   lessonBoardView.x=lessonBoardPointer.x-(event.clientX-lessonBoardPointer.clientX)/lessonBoardView.zoom;
   lessonBoardView.y=lessonBoardPointer.y-(event.clientY-lessonBoardPointer.clientY)/lessonBoardView.zoom;
  }else if(lessonBoardPointer.kind==="erase")lessonBoardErase(p);
  else if(lessonBoardPointer.kind==="move"&&lessonBoardSelection){
   lessonBoardSelection.x=lessonBoardPointer.x+p.x-lessonBoardPointer.start.x;
   lessonBoardSelection.y=lessonBoardPointer.y+p.y-lessonBoardPointer.start.y;
  }else if(lessonBoardPointer.stroke){
   if(lessonBoardPointer.stroke.straight)lessonBoardPointer.stroke.points[1]=p;
   else lessonAddStrokeSamples(lessonBoardPointer.stroke,event,lessonBoardPoint,{clientWidth:lessonBoardView.zoom,clientHeight:lessonBoardView.zoom});
  }
  lessonBoardScheduleDraw();
 };
 canvas.onpointerup=canvas.onpointercancel=canvas.onlostpointercapture=event=>{
  if(event.pointerType==="touch"&&lessonBoardPointer?.pointerType==="pen")return;
  if(lessonBoardPointer&&event.pointerId!==lessonBoardPointer.pointerId)return;
  if(event.type==="pointerup"&&lessonBoardPointer?.stroke){
   if(lessonBoardPointer.stroke.straight)lessonBoardPointer.stroke.points[1]=lessonBoardPoint(event);
   else lessonAddStrokeSamples(lessonBoardPointer.stroke,event,lessonBoardPoint,{clientWidth:lessonBoardView.zoom,clientHeight:lessonBoardView.zoom});
  }
  if(event.type==="pointerup"&&lessonBoardPointer?.stroke)lessonFinishStroke(lessonBoardPointer.stroke,lessonBoardView.zoom,lessonBoardView.zoom);
  touches.delete(event.pointerId);if(touches.size<2)pinch=null;if(!touches.size)touchBlocked=false;
  lessonBoardPointer=null;lessonBoardScheduleDraw();
 };
 document.getElementById("lessonBoardExport").onclick=async()=>{
  const exportPages=lessonBoardPages.map(page=>({...page,items:page.items.map(item=>({...item})),strokes:page.strokes.map(stroke=>({...stroke,points:stroke.points.map(p=>({...p}))}))}));
  try{
   lessonStatus("Подготавливаю все листы доски с записями...");
   lessonBoardStoreCurrent();
   exportPages[lessonBoardPageIndex]={...lessonBoardPages[lessonBoardPageIndex],items:lessonBoardItems.map(item=>({...item})),strokes:lessonBoardStrokes.map(stroke=>({...stroke,points:stroke.points.map(p=>({...p}))}))};
   const lib=await lessonLibrary("https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js","PDFLib");
   const pdf=await lib.PDFDocument.create();
   for(const boardPage of exportPages){
    let minX=0,minY=0,maxX=1200,maxY=800;
    const include=(x,y,w,h)=>{minX=Math.min(minX,x-20);minY=Math.min(minY,y-20);maxX=Math.max(maxX,x+w+20);maxY=Math.max(maxY,y+h+20);};
    for(const item of boardPage.items)include(item.x,item.y,item.w,item.h);
    for(const stroke of boardPage.strokes)for(const p of stroke.points)include(p.x-stroke.width,p.y-stroke.width,stroke.width*2,stroke.width*2);
    const scale=Math.min(1,2400/(maxX-minX),2400/(maxY-minY));
    const bitmap=document.createElement("canvas");bitmap.width=Math.ceil((maxX-minX)*scale);bitmap.height=Math.ceil((maxY-minY)*scale);
    lessonBoardPaint(bitmap.getContext("2d"),bitmap.width,bitmap.height,{x:minX,y:minY,zoom:scale},false,boardPage);
    const jpeg=await pdf.embedJpg(bitmap.toDataURL("image/jpeg",.93));
    const page=pdf.addPage([bitmap.width/2,bitmap.height/2]);page.drawImage(jpeg,{x:0,y:0,width:bitmap.width/2,height:bitmap.height/2});
    bitmap.width=bitmap.height=0;
   }
   const bytes=await pdf.save();lessonDownload(bytes,"Доска_ЕГЭ_БЛИЗКО_с_записями.pdf","application/pdf");
   lessonStatus("Все "+lessonBoardPages.length+" листов доски сохранены в один PDF.");
  }catch(err){lessonStatus("Не удалось сохранить доску в PDF.");}
  finally{lessonBoardDraw();}
 };
 lessonBoardDraw();
}
async function lessonPilotDiagnostic(message){
 let build="недоступна";
 try{const response=await fetch("/healthz",{cache:"no-store"});if(response.ok){const health=await response.json();if(health.sandbox===true)build=String(health.build||build);}}catch(err){}
 return {format:"ege-blizko-pilot-feedback",version:1,createdAt:new Date().toISOString(),build,
  message:String(message||"").slice(0,4000),browser:navigator.userAgent,
  viewport:{width:innerWidth,height:innerHeight,pixelRatio:devicePixelRatio},
  workspace:lessonBoardMode?"board":"presentation",tool:lessonTool,
  reaction:{a:lessonSelectedReagents.a||"",b:lessonSelectedReagents.b||"",heated:lessonHeated,medium:document.getElementById("lessonMedium").value}};
}
function lessonPilotSetup(){
 if(!data?.preview)return;
 document.getElementById("lessonPilotBar").hidden=false;
 const dialog=document.getElementById("lessonPilotDialog");
 const open=feedback=>{
  document.getElementById("lessonPilotTitle").textContent=feedback?"Сообщить о проблеме":"Перед первым уроком";
  document.getElementById("lessonPilotGuide").hidden=feedback;
  document.getElementById("lessonPilotFeedback").hidden=!feedback;
  dialog.showModal();
  document.getElementById(feedback?"lessonPilotMessage":"lessonPilotClose").focus();
 };
 document.getElementById("lessonPilotHelp").onclick=()=>open(false);
 document.getElementById("lessonPilotReport").onclick=()=>open(true);
 document.getElementById("lessonPilotClose").onclick=()=>dialog.close();
 document.getElementById("lessonPilotDownload").onclick=async event=>{
  const button=event.currentTarget;button.disabled=true;
  try{const report=await lessonPilotDiagnostic(document.getElementById("lessonPilotMessage").value);
   lessonDownload(JSON.stringify(report,null,2),"ЕГЭ_БЛИЗКО_сообщение_об_ошибке.json","application/json");
  }finally{button.disabled=false;}
 };
}
function lessonSetup(){
 lessonPilotSetup();
 if(lessonReady)return;
 lessonReady=true;
 lessonRestoreInkTools();
 const inkMenu=document.querySelector("#lesson .lesson-extra-menu");
 const positionInkMenu=()=>{const rect=inkMenu.querySelector("summary").getBoundingClientRect();inkMenu.style.setProperty("--lesson-settings-top",Math.min(rect.bottom+6,window.innerHeight-120)+"px");inkMenu.style.setProperty("--lesson-settings-right",Math.max(8,window.innerWidth-rect.right)+"px");};
 inkMenu.addEventListener("toggle",()=>{if(inkMenu.open)positionInkMenu();});
 window.addEventListener("resize",()=>{if(inkMenu.open)positionInkMenu();});
 document.querySelector("#lesson .lesson-lesson-tools").addEventListener("scroll",()=>{if(inkMenu.open)positionInkMenu();});
 document.getElementById("lessonBeautify").onchange=event=>{lessonBeautify=event.target.checked;lessonSaveInkTools();};
 document.getElementById("lesson").addEventListener("pointerdown",event=>{
  if(!event.target.closest(".lesson-extra-menu"))document.querySelector("#lesson .lesson-extra-menu").open=false;
  if(!event.target.closest("#lessonBoardMore"))document.getElementById("lessonBoardMore").open=false;
  if(!event.target.closest(".indicator-tools")){
   document.getElementById("lessonIndicatorPanel").hidden=true;
   document.getElementById("lessonIndicatorToggle").setAttribute("aria-expanded","false");
  }
 },true);
 document.querySelector("#lesson .lesson-lab-pane").addEventListener("pointerdown",event=>{
  if(event.target.closest("button,input,select")&&!event.target.closest(".lesson-ink-tools"))lessonLabInkMode("view");
 },true);
 lessonBoardSetup();
 lessonLabInkSetup();
 lessonTubeStates[0]=lessonCaptureTube();
 for(let i=1;i<4;i++)lessonTubeStates[i]=lessonEmptyTube();
 document.querySelectorAll("[data-lesson-tube]").forEach(btn=>{
  btn.onclick=()=>lessonSelectTube(Number(btn.dataset.lessonTube));
 });
 document.querySelectorAll("[data-lesson-count]").forEach(btn=>{
  btn.onclick=()=>lessonSetTubeCount(Number(btn.dataset.lessonCount));
 });
 lessonPopulateReagents();
 lessonRestoreLocal();
 document.getElementById("lessonPDFInput").onchange=event=>lessonOpenPDF(event.target.files[0]);
 document.getElementById("lessonMedium").onchange=()=>{lessonStarted=false;lessonRenderExperiment();};
 document.getElementById("lessonConduct").onclick=lessonConductStep;
 document.getElementById("lessonExcess").onclick=()=>{
  const {a,b}=lessonSelectedReagents;
  const alkali=[a,b].find(id=>id==="naoh"||id==="koh");
  const variant=alkali&&reactionVariants(a,b).find(x=>x.excess===alkali);
  if(!variant){lessonStatus("Для этой пары нет проверенного варианта с избытком щёлочи.");return;}
  // Keep the visual precipitate briefly, then advance the same tube's
  // qualitative chain to the dissolved aluminate/zincate products.
  const canUpdateChain=!!(lessonChain&&lessonChain.steps.length===1&&
    lessonChain.steps[0].reactant===a&&lessonChain.steps[0].reagent===b);
  lessonMotion.extraPours=(lessonMotion.extraPours||0)+1;
 lessonExcess=alkali;lessonStarted=true;lessonDissolving=canUpdateChain;
  document.getElementById("lessonExcess").setAttribute("aria-pressed","true");
  lessonRenderExperiment();
  const targetTube=lessonActiveTube,targetStates=lessonTubeStates,targetChain=lessonChain;
  const finishDissolving=()=>{
    // Finish the originating experiment even if another workbench is visible.
    // A reset or a new experiment invalidates the pending animation.
    const current=lessonTubeStates===targetStates&&lessonActiveTube===targetTube;
    const state=current?lessonCaptureTube():targetStates[targetTube];
    if(!state||state.excess!==alkali||state.chain!==targetChain)return;
    state.dissolving=false;
    if(canUpdateChain&&state.chain&&state.chain.steps.length===1){
      const details=chainProductDetails(variant);
      state.chain.steps[0]={...state.chain.steps[0],reaction:variant,untracked:details.untracked};
      state.chain.available=details.ids;
    }
    targetStates[targetTube]=state;
    if(current){lessonApplyTube(state);lessonRenderExperiment();}
  };
  if(canUpdateChain)setTimeout(finishDissolving,1100);
  else finishDissolving();
 };
 document.getElementById("lessonReset").onclick=lessonClearActiveTube;
 document.getElementById("lessonHeat").onclick=()=>{lessonHeated=!lessonHeated;document.getElementById("lessonHeat").setAttribute("aria-pressed",String(lessonHeated));lessonRenderExperiment();};
 document.getElementById("lessonPrevious").onclick=()=>{if(lessonPage>1){lessonPage--;lessonRenderPage();}};
 document.getElementById("lessonNext").onclick=()=>{if(lessonPage<lessonPageCount){lessonPage++;lessonRenderPage();}};
 const lessonToolbar=document.querySelector("#lesson .lesson-pdf-pane");
 const lessonStudio=document.querySelector("#lesson .lesson-studio");
 const lessonDivider=document.getElementById("lessonPanelDivider");
 const lessonSetPanelWidth=percent=>{
  const clamped=Math.max(20,Math.min(65,percent));
  lessonStudio.style.setProperty("--lesson-lab-width",clamped+"%");
  lessonDivider.setAttribute("aria-valuenow",String(Math.round(clamped)));
 };
 lessonDivider.addEventListener("pointerdown",event=>{
  if(event.button!==0)return;
  event.preventDefault();lessonDivider.setPointerCapture(event.pointerId);
 });
 lessonDivider.addEventListener("pointermove",event=>{
  if(!lessonDivider.hasPointerCapture(event.pointerId))return;
  const rect=lessonStudio.getBoundingClientRect();
  if(rect.width>0)lessonSetPanelWidth(100*(event.clientX-rect.left)/rect.width);
 });
 lessonDivider.addEventListener("keydown",event=>{
  if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight")return;
  event.preventDefault();
  const current=Number(lessonDivider.getAttribute("aria-valuenow"))||30;
  lessonSetPanelWidth(current+(event.key==="ArrowRight"?5:-5));
 });
 const lessonToolbarToggle=document.getElementById("lessonToolbarToggle");
 lessonToolbarToggle.onclick=()=>{
  const closed=lessonToolbar.classList.toggle("lesson-toolbar-collapsed");
  lessonToolbarToggle.textContent=closed?"Показать инструменты":"Скрыть инструменты";
  lessonToolbarToggle.setAttribute("aria-expanded",String(!closed));
  lessonRenderPage();
 };
 document.addEventListener("keydown",event=>{
  if(!document.getElementById("lesson").classList.contains("on")||event.altKey||event.ctrlKey||event.metaKey)return;
  const target=event.target;
  if(target&&(target.isContentEditable||target.id==="lessonPanelDivider"||/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)))return;
  let page=lessonPage;
  if(event.key==="ArrowRight"||event.key==="PageDown")page++;
  else if(event.key==="ArrowLeft"||event.key==="PageUp")page--;
  else if(event.key==="Home")page=1;
  else if(event.key==="End")page=lessonPageCount;
  else return;
  event.preventDefault();
  page=Math.max(1,Math.min(lessonPageCount,page));
  if(page!==lessonPage){lessonPage=page;lessonRenderPage();}
 });
 document.getElementById("lessonToolPen").onclick=()=>lessonSetTool("pen");
  document.getElementById("lessonToolMarker").onclick=()=>lessonSetTool("marker");
 document.getElementById("lessonStraightLine").onclick=()=>{
  if(lessonTool==="erase")lessonSetTool("pen");
  lessonSetLineMode(!lessonLineMode);
 };
 const lessonColors=[
  "#171719","#5b5b5d","#8b8b8e","#b7b7bc","#dedee0","#ffffff",
  "#f00087","#c44988","#f02b3b","#ff6a1e","#ffa600","#ffce00","#fff000",
  "#a4d628","#2bdc30","#00946f","#00b4cc","#2078db","#5024ce",
  "#722bd7","#8533a6","#f0ceb9","#c59d7d","#996542","#69483f",
  "#ee72e6","#ffc07c","#fff49d","#8eedaa","#86d9f6","#c1b9ff"
 ];
 const palette=document.getElementById("lessonColorPresets");
 const quickPalette=document.getElementById("lessonQuickColors");
 const picker=document.getElementById("lessonPenColor");
 const menu=document.querySelector("#lesson .lesson-extra-menu");
 const applyInkColor=(color,selected)=>{
  if(lessonTool==="erase")lessonSetTool(lessonLastInkTool);
  picker.value=color;
  if(lessonTool==="marker")lessonMarkerColorValue=color;
  else lessonPenColorValue=color;
  for(const button of document.querySelectorAll("#lessonColorPresets button,#lessonQuickColors button")){
   button.setAttribute("aria-pressed",String(button.dataset.ink===color));
  }
  lessonSyncInkTools();lessonSaveInkTools();
  if(selected)menu.open=false;
 };
 lessonColors.forEach(color=>{
  const btn=document.createElement("button");btn.type="button";btn.dataset.ink=color;
  btn.style.setProperty("--swatch",color);btn.setAttribute("aria-label","Цвет "+color);
  btn.setAttribute("aria-pressed",String(color.toLowerCase()===picker.value.toLowerCase()));
  btn.onclick=()=>applyInkColor(color,true);
  palette.appendChild(btn);
 });
 ["#171719","#ffffff","#f00087","#f02b3b","#ffce00","#2078db","#86c767"].forEach(color=>{
  const btn=document.createElement("button");btn.type="button";btn.dataset.ink=color;
  btn.style.setProperty("--swatch",color);
  btn.setAttribute("aria-label","Выбрать цвет "+color);
  btn.setAttribute("aria-pressed",String(color===picker.value));
  btn.onclick=()=>applyInkColor(color,false);
  quickPalette.appendChild(btn);
 });
 picker.oninput=()=>applyInkColor(picker.value,false);
 document.getElementById("lessonPenWidth").addEventListener("input",()=>{
  if(lessonTool==="marker")lessonMarkerWidthValue=Number(document.getElementById("lessonPenWidth").value);
  else lessonPenWidthValue=Number(document.getElementById("lessonPenWidth").value);
  lessonSaveInkTools();
 });
 document.getElementById("lessonPenWidth").addEventListener("change",()=>{menu.open=false;});
 document.getElementById("lessonToolEraser").onclick=()=>lessonSetTool("erase");
 document.getElementById("lessonUndo").onclick=()=>{if(lessonBoardMode){document.getElementById("lessonBoardUndo").click();return;}lessonCurrentStrokes().pop();lessonRedrawInk();lessonSaveLocal();};
 document.getElementById("lessonClearPage").onclick=()=>{
  const strokes=lessonCurrentStrokes();
  if(!strokes.length){lessonStatus("На текущем слайде нет пометок.");return;}
  lessonNotes[String(lessonPage)]=[];
  lessonRedrawInk();lessonSaveLocal();
  lessonStatus("Пометки текущего слайда удалены. Другие слайды не изменены.");
 };
 document.getElementById("lessonClearAll").onclick=()=>{
  const count=Object.values(lessonNotes).reduce((sum,strokes)=>sum+(Array.isArray(strokes)?strokes.length:0),0);
  if(!count){lessonStatus("В PDF нет рукописных пометок.");return;}
  if(!window.confirm("Удалить все рукописные пометки и выделения со всех слайдов этого PDF? Сам PDF останется без изменений."))return;
  lessonNotes={};lessonRedrawInk();lessonSaveLocal();
  lessonStatus("Все пометки этого PDF удалены. Исходный PDF не изменён.");
 };
 document.getElementById("lessonExport").onclick=lessonExportPDF;
 document.getElementById("lessonExportNotes").onclick=()=>{
  const payload=JSON.stringify({version:1,notes:lessonNotes,fileName:lessonPdfName, pages:lessonPageCount});
  lessonDownload(payload, "Записи_ЕГЭ_БЛИЗКО.json","application/json");
 };
 document.getElementById("lessonImportNotes").onchange=async event=>{
  try{
   const file=event.target.files[0];if(!file||file.size>3000000)throw Error("bad-size");
   const parsed=JSON.parse(await file.text());
   if(parsed.version!==1||!parsed.notes||!Array.isArray(parsed.notes[String(lessonPage)]||[]))throw Error("invalid");
   if(parsed.pages!==lessonPageCount)throw Error("pages");
   lessonNotes=parsed.notes;lessonSaveLocal();lessonRedrawInk();lessonStatus("Рукописные записи восстановлены.");
  }catch(err){lessonStatus("Не удалось прочитать записи или не совпадает число страниц.");}
 };
 const canvas=document.getElementById("lessonInkCanvas");
 let inkPointer=null;
 canvas.onpointerdown=event=>{
  if(inkPointer!==null||(event.pointerType==="mouse"&&event.button!==0))return;
  inkPointer=event.pointerId;event.preventDefault();canvas.setPointerCapture(event.pointerId);
  const point=lessonGetPoint(event);
  if(lessonTool==="erase"){lessonEraseAt(point);return;}
  lessonDrawing={renderVersion:2,color:lessonTool==="marker"?lessonMarkerColorValue:lessonPenColorValue,
   tool:lessonTool,opacity:lessonTool==="marker"?.32:1,
   width:lessonTool==="marker"?Math.max(12,Number(document.getElementById("lessonPenWidth").value)*4):Number(document.getElementById("lessonPenWidth").value),
   points:lessonLineMode?[point,point]:[point],straight:lessonLineMode};
  lessonCurrentStrokes().push(lessonDrawing);lessonSchedulePdfInk();
 };
 canvas.onpointermove=event=>{
  if(event.pointerId!==inkPointer||!canvas.hasPointerCapture(event.pointerId))return;
  event.preventDefault();const point=lessonGetPoint(event);
  if(lessonTool==="erase"){lessonEraseAt(point);return;}
  if(!lessonDrawing)return;
  if(lessonDrawing.straight)lessonDrawing.points[1]=point;
  else lessonAddStrokeSamples(lessonDrawing,event,lessonGetPoint,canvas);
  lessonSchedulePdfInk();
 };
 const endDrawing=event=>{
  if(event.pointerId!==inkPointer)return;
  if(lessonDrawing&&event.type==="pointerup"){
   const point=lessonGetPoint(event);
   if(lessonDrawing.straight)lessonDrawing.points[1]=point;
   else lessonAddStrokeSamples(lessonDrawing,event,lessonGetPoint,canvas);
  }
  inkPointer=null;
  if(lessonDrawing){if(event.type==="pointerup")lessonFinishStroke(lessonDrawing,canvas.clientWidth,canvas.clientHeight);lessonDrawing=null;lessonSchedulePdfInk();lessonSaveLocal();}
 };
 canvas.onpointerup=endDrawing;canvas.onpointercancel=endDrawing;canvas.onlostpointercapture=endDrawing;
 if(window.ResizeObserver){
  const watcher=new ResizeObserver(()=>{if(document.getElementById("lesson").classList.contains("on"))lessonRenderPage();});
  watcher.observe(document.getElementById("lessonPaperSpace"));
 }
 lessonSetTool("pen");
}

document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>{
 if(b.dataset.page!=="lesson"){lessonBoardSetFullscreen(false);lessonPresentationSetFullscreen(false);}
 document.querySelectorAll("[data-page]").forEach(x=>x.classList.remove("on"));document.querySelectorAll(".page").forEach(x=>x.classList.remove("on"));
 b.classList.add("on");document.getElementById(b.dataset.page).classList.add("on");if(b.dataset.page==="lesson"){lessonRenderPage();}if(b.dataset.page==="exam"&&!exam)nextExam();if(b.dataset.page==="oge")renderOge();if(b.dataset.page==="ege")renderEge();
});
api({action:"load"}).then(j=>{
 if(!j.ok){document.body.innerHTML="<p>Не удалось открыть лабораторию.</p>";return}
 data=j.data;Object.entries(data.reagents).forEach(x=>reagentMap.set(x[0],x[1]));
 task6Progress=data.task6_progress||null;task6Session=data.task6_session||null;
 if(task6Session){task6SelectedX=task6Session.selected_x||"";task6SelectedY=task6Session.selected_y||"";task6Target=task6SelectedX&&!task6SelectedY?"y":"x";}
 data.reactions.forEach(x=>{const k=key(x.a,x.b);if(!reactionMap.has(k))reactionMap.set(k,[]);reactionMap.get(k).push(x)});
 const cv=document.getElementById("labCoverage");if(cv&&data.coverage)cv.textContent="В текущем ЕГЭ-каталоге: "+data.coverage.substances+" веществ · "+data.coverage.reactions+" реакций/условий.";
 renderTubes();renderReagents();setupMobileTubePicker();setupReagentFilters();setupReagentSearch();setupLab();renderStats();lessonSetup();
 const requestedPage=labQs.get("page")||"";
 if(requestedPage){
   const btn=document.querySelector('[data-page="'+requestedPage+'"]');
   if(btn)btn.click();
 }
});
</script></body></html>'''

def do_get(self):
    path = urlparse(self.path).path
    if path == "/lab-solubility":
        try:
            body = Path(__file__).with_name("ege_lab_solubility_public.html").read_bytes()
        except OSError as exc:
            print(f"EGE public solubility unavailable: {type(exc).__name__}: {exc}", flush=True)
            return self._send_json(503, {"ok": False, "error": "solubility_unavailable"})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)
        return
    if path != "/lab-app":
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
                "medium_reactions":MEDIUM_REACTIONS,
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
