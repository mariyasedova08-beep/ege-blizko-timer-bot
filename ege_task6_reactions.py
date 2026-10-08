"""Reaction coverage required by the full EGE task 6 worksheet.

These records supplement the general laboratory chemistry database so every
correct virtual experiment in the 83-item task-6 bank has a modeled result.
"""

# a, b, equation, kind, observation, solution colour, precipitate colour, gas, heat_required
TASK6_REACTIONS = [
    ("mgcl2","nh3","MgCl₂ + 2NH₃·H₂O → Mg(OH)₂↓ + 2NH₄Cl","p","образуется белый осадок Mg(OH)₂","#f8fbff","#ffffff","",0),
    ("agno3","mgcl2","2AgNO₃ + MgCl₂ → 2AgCl↓ + Mg(NO₃)₂","p","образуется белый осадок AgCl","#f8fbff","#ffffff","",0),
    ("baco3","hbr","BaCO₃ + 2HBr → BaBr₂ + CO₂↑ + H₂O","x","белый BaCO₃ растворяется, выделяется CO₂","#f8fbff","","CO₂",0),
    ("baco3","co2","BaCO₃ + CO₂ + H₂O → Ba(HCO₃)₂","c","белый осадок BaCO₃ растворяется","#f8fbff","","",0),
    ("cahco3_2","naoh","Ca(HCO₃)₂ + NaOH → CaCO₃↓ + NaHCO₃ + H₂O","p","образуется белый осадок CaCO₃","#f8fbff","#ffffff","",0),
    ("nh42hpo4","naoh","(NH₄)₂HPO₄ + 2NaOH —t°→ Na₂HPO₄ + 2NH₃↑ + 2H₂O","g","при нагревании выделяется NH₃ с резким запахом","#f8fbff","","NH₃",1),
    ("cuf2","na2s","CuF₂ + Na₂S → CuS↓ + 2NaF","p","образуется чёрный осадок CuS","#f8fbff","#151515","",0),
    ("hbr","na2s","Na₂S + 2HBr → 2NaBr + H₂S↑","g","выделяется H₂S","#f8fbff","","H₂S",0),
    ("aloh3","hbr","Al(OH)₃ + 3HBr → AlBr₃ + 3H₂O","c","белый Al(OH)₃ растворяется","#f8fbff","","",0),
    ("caoh2","cucl2","Ca(OH)₂ + CuCl₂ → Cu(OH)₂↓ + CaCl₂","p","образуется голубой осадок Cu(OH)₂","#eaf7ff","#39bced","",0),
    ("caoh2","kf","Ca(OH)₂ + 2KF → CaF₂↓ + 2KOH","p","образуется белый осадок CaF₂","#f8fbff","#ffffff","",0),
    ("aloh3","hi","Al(OH)₃ + 3HI → AlI₃ + 3H₂O","c","белый Al(OH)₃ растворяется","#f8fbff","","",0),
    ("aloh3","lioh","Al(OH)₃ + LiOH → Li[Al(OH)₄]","c","белый Al(OH)₃ растворяется в щёлочи","#f8fbff","","",0),
    ("baoh2","nahco3","Ba(OH)₂ + 2NaHCO₃ → BaCO₃↓ + Na₂CO₃ + 2H₂O","p","образуется белый осадок BaCO₃","#f8fbff","#ffffff","",0),
    ("hf","zno","ZnO + 2HF → ZnF₂ + H₂O","c","белый ZnO растворяется","#f8fbff","","",0),
    ("hi","zno","ZnO + 2HI → ZnI₂ + H₂O","c","белый ZnO растворяется","#f8fbff","","",0),
    ("hi","khco3","KHCO₃ + HI → KI + CO₂↑ + H₂O","g","выделяются пузырьки CO₂","#f8fbff","","CO₂",0),
    ("agno3","hi","AgNO₃ + HI → AgI↓ + HNO₃","p","образуется жёлтый осадок AgI","#f8fbff","#f4d534","",0),
    ("hbr","nahco3","NaHCO₃ + HBr → NaBr + CO₂↑ + H₂O","g","выделяются пузырьки CO₂","#f8fbff","","CO₂",0),
    ("baoh2","zno","ZnO + Ba(OH)₂ + H₂O → Ba[Zn(OH)₄]","c","белый ZnO растворяется в щёлочи","#f8fbff","","",0),
    ("baoh2","nh4no3","Ba(OH)₂ + 2NH₄NO₃ → Ba(NO₃)₂ + 2NH₃↑ + 2H₂O","g","выделяется NH₃","#f8fbff","","NH₃",0),
    ("h2so4","kno2","2KNO₂ + H₂SO₄ → K₂SO₄ + 2HNO₂","n","видимого признака нет: образуется слабая HNO₂","#f8fbff","","",0),
    ("hbr","khs","KHS + HBr → KBr + H₂S↑","g","выделяется H₂S","#f8fbff","","H₂S",0),
    ("khs","koh","KHS + KOH → K₂S + H₂O","n","видимого признака нет","#f8fbff","","",0),
    ("hcl","kf","KF + HCl → KCl + HF","n","видимого признака нет: образуется слабая HF","#f8fbff","","",0),
    ("al2so43","koh","Al₂(SO₄)₃ + 6KOH → 2Al(OH)₃↓ + 3K₂SO₄","p","образуется белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("al2so43","na3po4","Al₂(SO₄)₃ + 2Na₃PO₄ → 2AlPO₄↓ + 3Na₂SO₄","p","образуется белый осадок AlPO₄","#f8fbff","#ffffff","",0),
    ("cubr2","fe","Fe + CuBr₂ → FeBr₂ + Cu↓","x","раствор светлеет и зеленеет, на железе появляется красно-бурая медь","#c8e5c8","#b96f4a","",0),
    ("cubr2","na2s","CuBr₂ + Na₂S → CuS↓ + 2NaBr","p","образуется чёрный осадок CuS","#f8fbff","#151515","",0),
    ("febr3","k3po4","FeBr₃ + K₃PO₄ → FePO₄↓ + 3KBr","p","образуется светлый осадок FePO₄","#f8fbff","#f1e8c8","",0),
    ("febr3","nh3","FeBr₃ + 3NH₃·H₂O → Fe(OH)₃↓ + 3NH₄Br","p","образуется бурый осадок Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("baoh2","hbr","Ba(OH)₂ + 2HBr → BaBr₂ + 2H₂O","n","нейтрализация без видимого признака","#f8fbff","","",0),
    ("baoh2","cuno3","Ba(OH)₂ + Cu(NO₃)₂ → Cu(OH)₂↓ + Ba(NO₃)₂","p","образуется голубой осадок Cu(OH)₂","#eaf7ff","#39bced","",0),
    ("cuno3","na2s","Cu(NO₃)₂ + Na₂S → CuS↓ + 2NaNO₃","p","образуется чёрный осадок CuS","#f8fbff","#151515","",0),
    ("na2co3","srcl2","SrCl₂ + Na₂CO₃ → SrCO₃↓ + 2NaCl","p","образуется белый осадок SrCO₃","#f8fbff","#ffffff","",0),
    ("h2so4","srcl2","SrCl₂ + H₂SO₄ → SrSO₄↓ + 2HCl","p","образуется белый осадок SrSO₄","#f8fbff","#ffffff","",0),
    ("bano2_2","k3po4","3Ba(NO₂)₂ + 2K₃PO₄ → Ba₃(PO₄)₂↓ + 6KNO₂","p","образуется белый осадок Ba₃(PO₄)₂","#f8fbff","#ffffff","",0),
    ("bano2_2","hcl","Ba(NO₂)₂ + 2HCl → BaCl₂ + 2HNO₂","n","видимого признака нет: образуется слабая HNO₂","#f8fbff","","",0),
    ("bano3","nh42so4","Ba(NO₃)₂ + (NH₄)₂SO₄ → BaSO₄↓ + 2NH₄NO₃","p","образуется белый осадок BaSO₄","#f8fbff","#ffffff","",0),
    ("naoh","nh42so4","(NH₄)₂SO₄ + 2NaOH → Na₂SO₄ + 2NH₃↑ + 2H₂O","g","выделяется NH₃","#f8fbff","","NH₃",0),
    ("hcl","k2sio3","K₂SiO₃ + 2HCl → H₂SiO₃↓ + 2KCl","p","образуется белый студенистый H₂SiO₃","#f8fbff","#ffffff","",0),
    ("cacl2","k2sio3","K₂SiO₃ + CaCl₂ → CaSiO₃↓ + 2KCl","p","образуется белый осадок CaSiO₃","#f8fbff","#ffffff","",0),
    ("baoh2","znoh2","Zn(OH)₂ + Ba(OH)₂ → Ba[Zn(OH)₄]","c","белый Zn(OH)₂ растворяется в избытке щёлочи","#f8fbff","","",0),
    ("baoh2","nh4oac","Ba(OH)₂ + 2CH₃COONH₄ → Ba(CH₃COO)₂ + 2NH₃↑ + 2H₂O","g","выделяется NH₃","#f8fbff","","NH₃",0),
    ("naoh","nh4oac","CH₃COONH₄ + NaOH → CH₃COONa + NH₃↑ + H₂O","g","выделяется NH₃","#f8fbff","","NH₃",0),
    ("koh","nahco3","NaHCO₃ + KOH → NaKCO₃ + H₂O","n","видимого признака нет; HCO₃⁻ превращается в CO₃²⁻","#f8fbff","","",0),
    ("naoh","nh4hso4","NH₄HSO₄ + 2NaOH —t°→ Na₂SO₄ + NH₃↑ + 2H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),
    ("khso3","naoh","KHSO₃ + NaOH → KNaSO₃ + H₂O","n","видимого признака нет","#f8fbff","","",0),
    ("hbr","nh3","NH₃·H₂O + HBr → NH₄Br + H₂O","n","нейтрализация без видимого признака","#f8fbff","","",0),
    ("al2so43","babr2","Al₂(SO₄)₃ + 3BaBr₂ → 3BaSO₄↓ + 2AlBr₃","p","образуется белый осадок BaSO₄","#f8fbff","#ffffff","",0),
    ("al2so43","lioh","Al₂(SO₄)₃ + 6LiOH → 2Al(OH)₃↓ + 3Li₂SO₄","p","образуется белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("hbr","na2sio3","Na₂SiO₃ + 2HBr → H₂SiO₃↓ + 2NaBr","p","образуется белый студенистый H₂SiO₃","#f8fbff","#ffffff","",0),
    ("hbr","khco3","KHCO₃ + HBr → KBr + CO₂↑ + H₂O","g","выделяется CO₂","#f8fbff","","CO₂",0),
    ("co2","sroh2","Sr(OH)₂ + CO₂ → SrCO₃↓ + H₂O","p","образуется белый осадок SrCO₃","#f8fbff","#ffffff","",0),
    ("hno3","na2sio3","Na₂SiO₃ + 2HNO₃ → H₂SiO₃↓ + 2NaNO₃","p","образуется белый студенистый H₂SiO₃","#f8fbff","#ffffff","",0),
    ("feno3_2","nh3","Fe(NO₃)₂ + 2NH₃·H₂O → Fe(OH)₂↓ + 2NH₄NO₃","p","образуется светло-зелёный осадок Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("hcl","nh3","NH₃·H₂O + HCl → NH₄Cl + H₂O","n","нейтрализация без видимого признака","#f8fbff","","",0),
    ("fe2so43","koh","Fe₂(SO₄)₃ + 6KOH → 2Fe(OH)₃↓ + 3K₂SO₄","p","образуется бурый осадок Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("fe2so43","nh3","Fe₂(SO₄)₃ + 6NH₃·H₂O → 2Fe(OH)₃↓ + 3(NH₄)₂SO₄","p","образуется бурый осадок Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("hi","nahso3","NaHSO₃ + HI → NaI + SO₂↑ + H₂O","g","выделяется SO₂","#f8fbff","","SO₂",0),
    ("caoh2","nahso3","2NaHSO₃ + Ca(OH)₂ → CaSO₃↓ + Na₂SO₃ + 2H₂O","p","образуется белый осадок CaSO₃","#f8fbff","#ffffff","",0),
    ("al2so43","nh3","Al₂(SO₄)₃ + 6NH₃·H₂O → 2Al(OH)₃↓ + 3(NH₄)₂SO₄","p","образуется белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("lioh","mgcl2","MgCl₂ + 2LiOH → Mg(OH)₂↓ + 2LiCl","p","образуется белый осадок Mg(OH)₂","#f8fbff","#ffffff","",0),
    ("k3po4","lioh","K₃PO₄ + 3LiOH → Li₃PO₄↓ + 3KOH","p","образуется белый осадок Li₃PO₄","#f8fbff","#ffffff","",0),
    ("koh","zn","Zn + 2KOH + 2H₂O → K₂[Zn(OH)₄] + H₂↑","g","цинк растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("baoh2","hno3","Ba(OH)₂ + 2HNO₃ → Ba(NO₃)₂ + 2H₂O","n","нейтрализация без видимого признака","#f8fbff","","",0),
    ("k3po4","li2so4","2K₃PO₄ + 3Li₂SO₄ → 2Li₃PO₄↓ + 3K₂SO₄","p","образуется белый осадок Li₃PO₄","#f8fbff","#ffffff","",0),
    ("li2so4","na2sio3","Li₂SO₄ + Na₂SiO₃ → Li₂SiO₃↓ + Na₂SO₄","p","образуется белый осадок Li₂SiO₃","#f8fbff","#ffffff","",0),
    ("al","koh","2Al + 2KOH + 6H₂O → 2K[Al(OH)₄] + 3H₂↑","g","алюминий растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("alcl3","k2co3","2AlCl₃ + 3K₂CO₃ + 3H₂O → 2Al(OH)₃↓ + 3CO₂↑ + 6KCl","x","образуется белый Al(OH)₃ и выделяется CO₂","#f8fbff","#ffffff","CO₂",0),
    ("baoh2","cahco3_2","Ba(OH)₂ + Ca(HCO₃)₂ → BaCO₃↓ + CaCO₃↓ + 2H₂O","p","образуется белый карбонатный осадок","#f8fbff","#ffffff","",0),
    ("cahco3_2","hcl","Ca(HCO₃)₂ + 2HCl → CaCl₂ + 2CO₂↑ + 2H₂O","g","выделяется CO₂","#f8fbff","","CO₂",0),
    ("lioh","zno","ZnO + 2LiOH + H₂O → Li₂[Zn(OH)₄]","c","белый ZnO растворяется в щёлочи","#f8fbff","","",0),
    ("lioh","nh4no3","NH₄NO₃ + LiOH → LiNO₃ + NH₃↑ + H₂O","g","выделяется NH₃","#f8fbff","","NH₃",0),
    ("h2sio3","naoh","H₂SiO₃ + 2NaOH → Na₂SiO₃ + 2H₂O","c","белый H₂SiO₃ растворяется","#f8fbff","","",0),
    ("hno3","znoh2","Zn(OH)₂ + 2HNO₃ → Zn(NO₃)₂ + 2H₂O","c","белый Zn(OH)₂ растворяется","#f8fbff","","",0),
    ("koh","znoh2","Zn(OH)₂ + 2KOH → K₂[Zn(OH)₄]","c","белый Zn(OH)₂ растворяется в щёлочи","#f8fbff","","",0),
    ("fe","hi","Fe + 2HI → FeI₂ + H₂↑","g","железо растворяется, выделяется H₂","#c8e5c8","","H₂",0),
    ("hi","naf","NaF + HI → NaI + HF","n","видимого признака нет: образуется слабая HF","#f8fbff","","",0),
    ("baoh2","nh42co3","Ba(OH)₂ + (NH₄)₂CO₃ → BaCO₃↓ + 2NH₃↑ + 2H₂O","x","образуется белый BaCO₃ и выделяется NH₃","#f8fbff","#ffffff","NH₃",0),
    ("kh2po4","naoh","KH₂PO₄ + 2NaOH → KNa₂PO₄ + 2H₂O","n","видимого признака нет; H₂PO₄⁻ превращается в PO₄³⁻","#f8fbff","","",0),
    ("mgso4","nh42co3","MgSO₄ + (NH₄)₂CO₃ → MgCO₃↓ + (NH₄)₂SO₄","p","образуется белый осадок MgCO₃","#f8fbff","#ffffff","",0),
    ("hbr","nh4hco3","NH₄HCO₃ + HBr → NH₄Br + CO₂↑ + H₂O","g","выделяется CO₂","#f8fbff","","CO₂",0),
    ("bahco3_2","naoh","Ba(HCO₃)₂ + NaOH → BaCO₃↓ + NaHCO₃ + H₂O","p","образуется белый осадок BaCO₃","#f8fbff","#ffffff","",0),
    ("lino3","na3po4","3LiNO₃ + Na₃PO₄ → Li₃PO₄↓ + 3NaNO₃","p","образуется белый осадок Li₃PO₄","#f8fbff","#ffffff","",0),
    ("al2s3","h2so4","Al₂S₃ + 3H₂SO₄ → Al₂(SO₄)₃ + 3H₂S↑","x","твёрдый Al₂S₃ растворяется, выделяется H₂S","#f8fbff","","H₂S",0),
    ("bahco3_2","hcl","Ba(HCO₃)₂ + 2HCl → BaCl₂ + 2CO₂↑ + 2H₂O","g","выделяется CO₂","#f8fbff","","CO₂",0),
    ("bahco3_2","koh","Ba(HCO₃)₂ + KOH → BaCO₃↓ + KHCO₃ + H₂O","p","образуется белый осадок BaCO₃","#f8fbff","#ffffff","",0),
    ("agno3","k3po4","3AgNO₃ + K₃PO₄ → Ag₃PO₄↓ + 3KNO₃","p","образуется жёлтый осадок Ag₃PO₄","#f8fbff","#e6cf44","",0),
    ("k3po4","lino3","K₃PO₄ + 3LiNO₃ → Li₃PO₄↓ + 3KNO₃","p","образуется белый осадок Li₃PO₄","#f8fbff","#ffffff","",0),
    ("baoh2","nh42hpo4","Ba(OH)₂ + (NH₄)₂HPO₄ → BaHPO₄↓ + 2NH₃↑ + 2H₂O","x","образуется белый BaHPO₄ и выделяется NH₃","#f8fbff","#ffffff","NH₃",0),
    ("hbr","na2co3","Na₂CO₃ + 2HBr → 2NaBr + CO₂↑ + H₂O","g","выделяется CO₂","#f8fbff","","CO₂",0),
]

# Same pair but the worksheet explicitly specifies excess reagent.
TASK6_VARIANTS = [
    {
        "a":"mgso4","b":"naoh","excess":"naoh",
        "eq":"MgSO₄ + 2NaOH → Mg(OH)₂↓ + Na₂SO₄",
        "t":"p","sign":"белый Mg(OH)₂ выпадает и не растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"#ffffff","gas":"","heat":False,"condition":"избыток NaOH",
    },
    {
        "a":"albr3","b":"naoh","excess":"naoh",
        "eq":"AlBr₃ + 4NaOH → Na[Al(OH)₄] + 3NaBr",
        "t":"c","sign":"белый Al(OH)₃ сначала выпадает, затем растворяется",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,"condition":"избыток NaOH",
    },
    {
        "a":"znbr2","b":"naoh","excess":"naoh",
        "eq":"ZnBr₂ + 4NaOH → Na₂[Zn(OH)₄] + 2NaBr",
        "t":"c","sign":"белый Zn(OH)₂ сначала выпадает, затем растворяется",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,"condition":"избыток NaOH",
    },
    {
        "a":"caco3","b":"co2","excess":"co2",
        "eq":"CaCO₃ + CO₂ + H₂O → Ca(HCO₃)₂",
        "t":"c","sign":"белый CaCO₃ растворяется при пропускании избытка CO₂",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,"condition":"вода и избыток CO₂",
    },
    {
        "a":"mgno3","b":"naoh","excess":"naoh",
        "eq":"Mg(NO₃)₂ + 2NaOH → Mg(OH)₂↓ + 2NaNO₃",
        "t":"p","sign":"белый Mg(OH)₂ выпадает и не растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"#ffffff","gas":"","heat":False,"condition":"избыток NaOH",
    },
    {
        "a":"al2s3","b":"naoh","excess":"naoh",
        "eq":"Al₂S₃ + 8NaOH → 2Na[Al(OH)₄] + 3Na₂S",
        "t":"c","sign":"твёрдый Al₂S₃ растворяется, образуется прозрачный раствор",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,"condition":"избыток NaOH",
    },
]


def validate_task6_reactions(known_ids):
    for row in TASK6_REACTIONS:
        if len(row) != 9:
            raise RuntimeError(f"bad task6 reaction row: {row}")
        if row[0] not in known_ids or row[1] not in known_ids:
            raise RuntimeError(f"unknown task6 reagent: {row[0]} + {row[1]}")
    for row in TASK6_VARIANTS:
        if row["a"] not in known_ids or row["b"] not in known_ids:
            raise RuntimeError(f"unknown task6 variant reagent: {row}")
        if row.get("excess") not in {row["a"], row["b"]}:
            raise RuntimeError(f"bad task6 excess: {row}")
    return True
