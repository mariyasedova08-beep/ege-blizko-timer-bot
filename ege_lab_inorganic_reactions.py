"""EGE inorganic laboratory expansion.

EXTRA_REACTIONS keeps the legacy tuple shape used by ege_lab_webapp:
(a, b, equation, kind, observation, solution_colour, precipitate_colour,
 gas, heat_required)

REACTION_VARIANTS adds condition-dependent outcomes.  The Mini App selects
these when the learner explicitly marks the last added reagent as excess.
"""

EXTRA_REACTIONS = [
    # Oxides + water
    ("na2o","h2o","Na₂O + H₂O → 2NaOH","n","образуется щёлочь","#f8fbff","","",0),
    ("k2o","h2o","K₂O + H₂O → 2KOH","n","образуется щёлочь","#f8fbff","","",0),
    ("cao","h2o","CaO + H₂O → Ca(OH)₂","x","смесь разогревается, появляется белая взвесь","#f8fbff","#ffffff","",0),
    ("co2","h2o","CO₂ + H₂O ⇄ H₂CO₃","n","образуется слабая кислота","#f8fbff","","",0),
    ("so2","h2o","SO₂ + H₂O ⇄ H₂SO₃","n","образуется сернистая кислота","#f8fbff","","",0),
    ("so3","h2o","SO₃ + H₂O → H₂SO₄","n","образуется серная кислота","#f8fbff","","",0),
    ("n2o5","h2o","N₂O₅ + H₂O → 2HNO₃","n","образуется азотная кислота","#f8fbff","","",0),
    ("p2o5","h2o","P₂O₅ + 3H₂O → 2H₃PO₄","n","образуется ортофосфорная кислота","#f8fbff","","",0),

    # Acidic oxides + alkalis / lime water
    ("co2","naoh","CO₂ + 2NaOH → Na₂CO₃ + H₂O","n","газ поглощается щёлочью","#f8fbff","","",0),
    ("co2","koh","CO₂ + 2KOH → K₂CO₃ + H₂O","n","газ поглощается щёлочью","#f8fbff","","",0),
    ("co2","caoh2","CO₂ + Ca(OH)₂ → CaCO₃↓ + H₂O","p","белый CaCO₃, раствор мутнеет","#f8fbff","#ffffff","",0),
    ("co2","baoh2","CO₂ + Ba(OH)₂ → BaCO₃↓ + H₂O","p","белый BaCO₃","#f8fbff","#ffffff","",0),
    ("so2","naoh","SO₂ + 2NaOH → Na₂SO₃ + H₂O","n","SO₂ поглощается щёлочью","#f8fbff","","",0),
    ("so2","koh","SO₂ + 2KOH → K₂SO₃ + H₂O","n","SO₂ поглощается щёлочью","#f8fbff","","",0),
    ("so2","caoh2","SO₂ + Ca(OH)₂ → CaSO₃↓ + H₂O","p","белый CaSO₃","#f8fbff","#ffffff","",0),
    ("so3","naoh","SO₃ + 2NaOH → Na₂SO₄ + H₂O","n","кислотный оксид нейтрализуется","#f8fbff","","",0),
    ("p2o5","naoh","P₂O₅ + 6NaOH → 2Na₃PO₄ + 3H₂O","n","кислотный оксид нейтрализуется","#f8fbff","","",0),
    ("sio2","naoh","SiO₂ + 2NaOH —t°→ Na₂SiO₃ + H₂O","c","твёрдый SiO₂ постепенно реагирует при нагревании","#f8fbff","","",1),
    ("no2","naoh","2NO₂ + 2NaOH → NaNO₂ + NaNO₃ + H₂O","c","бурый NO₂ поглощается, окраска исчезает","#f8fbff","","",0),

    # Basic / amphoteric oxides + acids
    ("na2o","hcl","Na₂O + 2HCl → 2NaCl + H₂O","n","основный оксид растворяется","#f8fbff","","",0),
    ("cao","hcl","CaO + 2HCl → CaCl₂ + H₂O","n","белый оксид растворяется","#f8fbff","","",0),
    ("mgo","hcl","MgO + 2HCl → MgCl₂ + H₂O","n","белый оксид растворяется","#f8fbff","","",0),
    ("cuo","hcl","CuO + 2HCl → CuCl₂ + H₂O","c","чёрный CuO растворяется, раствор становится голубовато-зелёным","#55b7a1","","",0),
    ("feo","hcl","FeO + 2HCl → FeCl₂ + H₂O","c","чёрный FeO растворяется, образуется светло-зелёный раствор","#c8e5c8","","",0),
    ("fe2o3","hcl","Fe₂O₃ + 6HCl → 2FeCl₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, раствор желтеет","#d99d2b","","",0),
    ("fe3o4","hcl","Fe₃O₄ + 8HCl → FeCl₂ + 2FeCl₃ + 4H₂O","c","чёрный Fe₃O₄ растворяется","#c8b56e","","",0),
    ("al2o3","hcl","Al₂O₃ + 6HCl → 2AlCl₃ + 3H₂O","c","белый Al₂O₃ растворяется","#f8fbff","","",0),
    ("zno","hcl","ZnO + 2HCl → ZnCl₂ + H₂O","c","белый ZnO растворяется","#f8fbff","","",0),
    ("cr2o3","hcl","Cr₂O₃ + 6HCl → 2CrCl₃ + 3H₂O","c","зелёный Cr₂O₃ растворяется, образуется зелёный раствор","#6e966f","","",0),
    ("na2o","h2so4","Na₂O + H₂SO₄ → Na₂SO₄ + H₂O","n","основный оксид нейтрализуется","#f8fbff","","",0),
    ("cao","h2so4","CaO + H₂SO₄ → CaSO₄ + H₂O","p","образуется белый малорастворимый CaSO₄","#f8fbff","#ffffff","",0),
    ("mgo","h2so4","MgO + H₂SO₄ → MgSO₄ + H₂O","n","белый MgO растворяется","#f8fbff","","",0),
    ("cuo","h2so4","CuO + H₂SO₄ → CuSO₄ + H₂O","c","чёрный CuO растворяется, раствор становится голубым","#42baf5","","",0),
    ("feo","h2so4","FeO + H₂SO₄ → FeSO₄ + H₂O","c","чёрный FeO растворяется, образуется светло-зелёный раствор","#bfe7c5","","",0),
    ("fe2o3","h2so4","Fe₂O₃ + 3H₂SO₄ → Fe₂(SO₄)₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, раствор желтеет","#e1b562","","",0),
    ("al2o3","h2so4","Al₂O₃ + 3H₂SO₄ → Al₂(SO₄)₃ + 3H₂O","c","белый Al₂O₃ растворяется","#f8fbff","","",0),
    ("zno","h2so4","ZnO + H₂SO₄ → ZnSO₄ + H₂O","c","белый ZnO растворяется","#f8fbff","","",0),

    # Amphoteric oxides + alkali
    ("al2o3","naoh","Al₂O₃ + 2NaOH + 3H₂O → 2Na[Al(OH)₄]","c","белый Al₂O₃ растворяется в щёлочи","#f8fbff","","",0),
    ("zno","naoh","ZnO + 2NaOH + H₂O → Na₂[Zn(OH)₄]","c","белый ZnO растворяется в щёлочи","#f8fbff","","",0),
    ("cr2o3","naoh","Cr₂O₃ + 2NaOH —t°→ 2NaCrO₂ + H₂O","c","зелёный оксид реагирует со щёлочью при нагревании","#6e966f","","",1),

    # Hydroxides + acids
    ("caoh2","hcl","Ca(OH)₂ + 2HCl → CaCl₂ + 2H₂O","n","нейтрализация","#f8fbff","","",0),
    ("baoh2","hcl","Ba(OH)₂ + 2HCl → BaCl₂ + 2H₂O","n","нейтрализация","#f8fbff","","",0),
    ("mgoh2","hcl","Mg(OH)₂ + 2HCl → MgCl₂ + 2H₂O","c","белый осадок Mg(OH)₂ растворяется","#f8fbff","","",0),
    ("cuoh2","hcl","Cu(OH)₂ + 2HCl → CuCl₂ + 2H₂O","c","голубой осадок растворяется, образуется голубовато-зелёный раствор","#55b7a1","","",0),
    ("feoh2","hcl","Fe(OH)₂ + 2HCl → FeCl₂ + 2H₂O","c","светло-зелёный осадок растворяется","#c8e5c8","","",0),
    ("feoh3","hcl","Fe(OH)₃ + 3HCl → FeCl₃ + 3H₂O","c","бурый осадок растворяется, раствор желтеет","#d99d2b","","",0),
    ("aloh3","hcl","Al(OH)₃ + 3HCl → AlCl₃ + 3H₂O","c","белый студенистый осадок растворяется","#f8fbff","","",0),
    ("znoh2","hcl","Zn(OH)₂ + 2HCl → ZnCl₂ + 2H₂O","c","белый осадок растворяется","#f8fbff","","",0),
    ("croh3","hcl","Cr(OH)₃ + 3HCl → CrCl₃ + 3H₂O","c","зелёный осадок растворяется","#6e966f","","",0),
    ("caoh2","h2so4","Ca(OH)₂ + H₂SO₄ → CaSO₄↓ + 2H₂O","p","белый CaSO₄","#f8fbff","#ffffff","",0),
    ("baoh2","h2so4","Ba(OH)₂ + H₂SO₄ → BaSO₄↓ + 2H₂O","p","белый BaSO₄","#f8fbff","#ffffff","",0),
    ("cuoh2","h2so4","Cu(OH)₂ + H₂SO₄ → CuSO₄ + 2H₂O","c","голубой осадок растворяется, образуется голубой раствор","#42baf5","","",0),
    ("feoh2","h2so4","Fe(OH)₂ + H₂SO₄ → FeSO₄ + 2H₂O","c","светло-зелёный осадок растворяется","#bfe7c5","","",0),
    ("feoh3","h2so4","2Fe(OH)₃ + 3H₂SO₄ → Fe₂(SO₄)₃ + 6H₂O","c","бурый осадок растворяется","#e1b562","","",0),
    ("aloh3","h2so4","2Al(OH)₃ + 3H₂SO₄ → Al₂(SO₄)₃ + 6H₂O","c","белый студенистый осадок растворяется","#f8fbff","","",0),
    ("znoh2","h2so4","Zn(OH)₂ + H₂SO₄ → ZnSO₄ + 2H₂O","c","белый осадок растворяется","#f8fbff","","",0),

    # Amphoteric hydroxides + alkali
    ("aloh3","naoh","Al(OH)₃ + NaOH → Na[Al(OH)₄]","c","белый студенистый Al(OH)₃ растворяется в избытке щёлочи","#f8fbff","","",0),
    ("znoh2","naoh","Zn(OH)₂ + 2NaOH → Na₂[Zn(OH)₄]","c","белый Zn(OH)₂ растворяется в избытке щёлочи","#f8fbff","","",0),
    ("croh3","naoh","Cr(OH)₃ + 3NaOH → Na₃[Cr(OH)₆]","c","зелёный Cr(OH)₃ растворяется в избытке щёлочи","#6f9f79","","",0),

    # Additional hydroxide precipitation from salts
    ("cucl2","naoh","CuCl₂ + 2NaOH → Cu(OH)₂↓ + 2NaCl","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),
    ("cuno3","naoh","Cu(NO₃)₂ + 2NaOH → Cu(OH)₂↓ + 2NaNO₃","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),
    ("fecl2","naoh","FeCl₂ + 2NaOH → Fe(OH)₂↓ + 2NaCl","p","светло-зелёный Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("feno3_2","naoh","Fe(NO₃)₂ + 2NaOH → Fe(OH)₂↓ + 2NaNO₃","p","светло-зелёный Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("feno3_3","naoh","Fe(NO₃)₃ + 3NaOH → Fe(OH)₃↓ + 3NaNO₃","p","бурый Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("fe2so43","naoh","Fe₂(SO₄)₃ + 6NaOH → 2Fe(OH)₃↓ + 3Na₂SO₄","p","бурый Fe(OH)₃","#fff3e8","#9a4a2b","",0),
    ("mgcl2","naoh","MgCl₂ + 2NaOH → Mg(OH)₂↓ + 2NaCl","p","белый Mg(OH)₂","#f8fbff","#ffffff","",0),
    ("mgno3","naoh","Mg(NO₃)₂ + 2NaOH → Mg(OH)₂↓ + 2NaNO₃","p","белый Mg(OH)₂","#f8fbff","#ffffff","",0),
    ("alno3","naoh","Al(NO₃)₃ + 3NaOH → Al(OH)₃↓ + 3NaNO₃","p","белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("al2so43","naoh","Al₂(SO₄)₃ + 6NaOH → 2Al(OH)₃↓ + 3Na₂SO₄","p","белый студенистый Al(OH)₃","#f8fbff","#ffffff","",0),
    ("zncl2","naoh","ZnCl₂ + 2NaOH → Zn(OH)₂↓ + 2NaCl","p","белый Zn(OH)₂","#f8fbff","#ffffff","",0),
    ("znno3","naoh","Zn(NO₃)₂ + 2NaOH → Zn(OH)₂↓ + 2NaNO₃","p","белый Zn(OH)₂","#f8fbff","#ffffff","",0),

    # Carbonates / hydrogen carbonate + acids
    ("nahco3","hcl","NaHCO₃ + HCl → NaCl + CO₂↑ + H₂O","g","пузырьки CO₂","#f8fbff","","CO₂",0),
    ("nahco3","h2so4","2NaHCO₃ + H₂SO₄ → Na₂SO₄ + 2CO₂↑ + 2H₂O","g","пузырьки CO₂","#f8fbff","","CO₂",0),
    ("caco3","hcl","CaCO₃ + 2HCl → CaCl₂ + CO₂↑ + H₂O","g","белый CaCO₃ растворяется с выделением CO₂","#f8fbff","","CO₂",0),
    ("mgco3","hcl","MgCO₃ + 2HCl → MgCl₂ + CO₂↑ + H₂O","g","белый MgCO₃ растворяется с выделением CO₂","#f8fbff","","CO₂",0),
    ("baco3","hcl","BaCO₃ + 2HCl → BaCl₂ + CO₂↑ + H₂O","g","белый BaCO₃ растворяется с выделением CO₂","#f8fbff","","CO₂",0),
    ("caco3","h2so4","CaCO₃ + H₂SO₄ → CaSO₄↓ + CO₂↑ + H₂O","x","CO₂ и белый слой CaSO₄","#f8fbff","#ffffff","CO₂",0),

    # Phosphates / silicates
    ("agno3","na3po4","3AgNO₃ + Na₃PO₄ → Ag₃PO₄↓ + 3NaNO₃","p","жёлтый Ag₃PO₄","#f8fbff","#e5c92d","",0),
    ("bacl2","na3po4","3BaCl₂ + 2Na₃PO₄ → Ba₃(PO₄)₂↓ + 6NaCl","p","белый Ba₃(PO₄)₂","#f8fbff","#ffffff","",0),
    ("cacl2","na3po4","3CaCl₂ + 2Na₃PO₄ → Ca₃(PO₄)₂↓ + 6NaCl","p","белый Ca₃(PO₄)₂","#f8fbff","#ffffff","",0),
    ("ca3po42","hcl","Ca₃(PO₄)₂ + 6HCl → 3CaCl₂ + 2H₃PO₄","c","белый фосфат кальция растворяется","#f8fbff","","",0),

    # Additional sulfate / carbonate precipitation
    ("bano3","na2so4","Ba(NO₃)₂ + Na₂SO₄ → BaSO₄↓ + 2NaNO₃","p","белый BaSO₄","#f8fbff","#ffffff","",0),
    ("bano3","k2so4","Ba(NO₃)₂ + K₂SO₄ → BaSO₄↓ + 2KNO₃","p","белый BaSO₄","#f8fbff","#ffffff","",0),
    ("cacl2","k2co3","CaCl₂ + K₂CO₃ → CaCO₃↓ + 2KCl","p","белый CaCO₃","#f8fbff","#ffffff","",0),
    ("mgcl2","na2co3","MgCl₂ + Na₂CO₃ → MgCO₃↓ + 2NaCl","p","белый MgCO₃","#f8fbff","#ffffff","",0),
    ("bacl2","k2co3","BaCl₂ + K₂CO₃ → BaCO₃↓ + 2KCl","p","белый BaCO₃","#f8fbff","#ffffff","",0),
    ("pbno3","na2so4","Pb(NO₃)₂ + Na₂SO₄ → PbSO₄↓ + 2NaNO₃","p","белый PbSO₄","#f8fbff","#ffffff","",0),
    ("pbno3","na2co3","Pb(NO₃)₂ + Na₂CO₃ → PbCO₃↓ + 2NaNO₃","p","белый PbCO₃","#f8fbff","#ffffff","",0),

    # Sulfides and qualitative reactions
    ("fes","hcl","FeS + 2HCl → FeCl₂ + H₂S↑","g","выделяется H₂S, твёрдый FeS растворяется","#c8e5c8","","H₂S",0),
    ("fecl3","ki","2FeCl₃ + 2KI → 2FeCl₂ + I₂ + 2KCl","c","появляется бурая окраска I₂","#a96d38","","",0),
    ("fecl3","kscn","FeCl₃ + 3KSCN ⇄ Fe(SCN)₃ + 3KCl","c","кроваво-красное окрашивание комплекса Fe(III)","#b31936","","",0),
    ("feno3_3","kscn","Fe(NO₃)₃ + 3KSCN ⇄ Fe(SCN)₃ + 3KNO₃","c","кроваво-красное окрашивание комплекса Fe(III)","#b31936","","",0),
    ("cuso4","nh3","CuSO₄ + 2NH₃·H₂O → Cu(OH)₂↓ + (NH₄)₂SO₄","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),
    ("cucl2","nh3","CuCl₂ + 2NH₃·H₂O → Cu(OH)₂↓ + 2NH₄Cl","p","голубой Cu(OH)₂","#d9f4ff","#39bced","",0),

    # Ammonium salts + alkali
    ("nh4no3","naoh","NH₄NO₃ + NaOH —t°→ NaNO₃ + NH₃↑ + H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),
    ("nh42so4","naoh","(NH₄)₂SO₄ + 2NaOH —t°→ Na₂SO₄ + 2NH₃↑ + 2H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),

    # Chromate / dichromate cross-checks
    ("k2cro4","h2so4","2K₂CrO₄ + H₂SO₄ ⇄ K₂Cr₂O₇ + K₂SO₄ + H₂O","c","жёлтый → оранжевый","#ef7c2d","","",0),
]

# Same pair, different result when the last-added reagent is explicitly in excess.
REACTION_VARIANTS = [
    {
        "a":"alcl3","b":"naoh","excess":"naoh",
        "eq":"AlCl₃ + 4NaOH → Na[Al(OH)₄] + 3NaCl",
        "t":"c","sign":"белый Al(OH)₃ сначала выпадает, затем растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"alno3","b":"naoh","excess":"naoh",
        "eq":"Al(NO₃)₃ + 4NaOH → Na[Al(OH)₄] + 3NaNO₃",
        "t":"c","sign":"белый Al(OH)₃ растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"al2so43","b":"naoh","excess":"naoh",
        "eq":"Al₂(SO₄)₃ + 8NaOH → 2Na[Al(OH)₄] + 3Na₂SO₄",
        "t":"c","sign":"белый Al(OH)₃ растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"znso4","b":"naoh","excess":"naoh",
        "eq":"ZnSO₄ + 4NaOH → Na₂[Zn(OH)₄] + Na₂SO₄",
        "t":"c","sign":"белый Zn(OH)₂ растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"zncl2","b":"naoh","excess":"naoh",
        "eq":"ZnCl₂ + 4NaOH → Na₂[Zn(OH)₄] + 2NaCl",
        "t":"c","sign":"белый Zn(OH)₂ растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"znno3","b":"naoh","excess":"naoh",
        "eq":"Zn(NO₃)₂ + 4NaOH → Na₂[Zn(OH)₄] + 2NaNO₃",
        "t":"c","sign":"белый Zn(OH)₂ растворяется в избытке NaOH",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток NaOH",
    },
    {
        "a":"co2","b":"caoh2","excess":"co2",
        "eq":"CaCO₃ + CO₂ + H₂O → Ca(HCO₃)₂",
        "t":"c","sign":"после помутнения осадок CaCO₃ растворяется в избытке CO₂",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток CO₂",
    },
    {
        "a":"co2","b":"baoh2","excess":"co2",
        "eq":"BaCO₃ + CO₂ + H₂O → Ba(HCO₃)₂",
        "t":"c","sign":"белый BaCO₃ растворяется в избытке CO₂",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток CO₂",
    },
    {
        "a":"co2","b":"naoh","excess":"co2",
        "eq":"CO₂ + NaOH → NaHCO₃",
        "t":"n","sign":"в избытке CO₂ образуется гидрокарбонат",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток CO₂",
    },
    {
        "a":"so2","b":"caoh2","excess":"so2",
        "eq":"CaSO₃ + SO₂ + H₂O → Ca(HSO₃)₂",
        "t":"c","sign":"белый CaSO₃ растворяется в избытке SO₂",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток SO₂",
    },
    {
        "a":"so2","b":"naoh","excess":"so2",
        "eq":"SO₂ + NaOH → NaHSO₃",
        "t":"n","sign":"в избытке SO₂ образуется гидросульфит",
        "sol":"#f8fbff","ppt":"","gas":"","heat":False,
        "condition":"избыток SO₂",
    },
    {
        "a":"cuso4","b":"nh3","excess":"nh3",
        "eq":"Cu(OH)₂ + 4NH₃ → [Cu(NH₃)₄](OH)₂",
        "t":"c","sign":"голубой осадок растворяется, появляется интенсивно-синяя окраска комплекса Cu(II)",
        "sol":"#214fa3","ppt":"","gas":"","heat":False,
        "condition":"избыток NH₃·H₂O",
    },
    {
        "a":"cucl2","b":"nh3","excess":"nh3",
        "eq":"Cu(OH)₂ + 4NH₃ → [Cu(NH₃)₄](OH)₂",
        "t":"c","sign":"голубой осадок растворяется, появляется интенсивно-синяя окраска комплекса Cu(II)",
        "sol":"#214fa3","ppt":"","gas":"","heat":False,
        "condition":"избыток NH₃·H₂O",
    },
]


def validate_reactions(known_ids):
    for row in EXTRA_REACTIONS:
        if row[0] not in known_ids or row[1] not in known_ids:
            raise RuntimeError(f"unknown reagent in reaction: {row[0]} + {row[1]}")
        if len(row) != 9:
            raise RuntimeError(f"bad reaction tuple: {row}")
    for row in REACTION_VARIANTS:
        if row["a"] not in known_ids or row["b"] not in known_ids:
            raise RuntimeError(f"unknown reagent in variant: {row}")
        if row.get("excess") not in {row["a"], row["b"]}:
            raise RuntimeError(f"bad excess reagent: {row}")
    return True
