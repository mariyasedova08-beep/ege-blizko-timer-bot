"""EGE inorganic laboratory expansion.

EXTRA_REACTIONS keeps the legacy tuple shape used by ege_lab_webapp:
(a, b, equation, kind, observation, solution_colour, precipitate_colour,
 gas, heat_required)

REACTION_VARIANTS adds condition-dependent outcomes.  The Mini App selects
these when the learner explicitly marks the last added reagent as excess.
"""

EXTRA_REACTIONS = [
    # Simple substances: water and non-oxidising acids
    ("na","h2o","2Na + 2H₂O → 2NaOH + H₂↑","g","бурное выделение H₂, металл быстро исчезает","#f8fbff","","H₂",0),
    ("k","h2o","2K + 2H₂O → 2KOH + H₂↑","g","очень бурное выделение H₂, металл быстро исчезает","#f8fbff","","H₂",0),
    ("ca","h2o","Ca + 2H₂O → Ca(OH)₂ + H₂↑","x","выделяется H₂, раствор мутнеет из-за Ca(OH)₂","#f8fbff","#ffffff","H₂",0),
    ("ba","h2o","Ba + 2H₂O → Ba(OH)₂ + H₂↑","g","активно выделяется H₂, металл растворяется","#f8fbff","","H₂",0),
    ("mg","h2o","Mg + 2H₂O —t°→ Mg(OH)₂↓ + H₂↑","x","при нагревании выделяется H₂ и появляется белый Mg(OH)₂","#f8fbff","#ffffff","H₂",1),

    ("mg","hcl","Mg + 2HCl → MgCl₂ + H₂↑","g","металл растворяется, выделяются пузырьки H₂","#f8fbff","","H₂",0),
    ("al","hcl","2Al + 6HCl → 2AlCl₃ + 3H₂↑","g","алюминий растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("zn","hcl","Zn + 2HCl → ZnCl₂ + H₂↑","g","цинк растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("cr","hcl","Cr + 2HCl → CrCl₂ + H₂↑","g","хром растворяется, выделяется H₂","#91a7bd","","H₂",0),
    ("fe","hcl","Fe + 2HCl → FeCl₂ + H₂↑","x","железо растворяется, выделяется H₂, раствор становится светло-зелёным","#c8e5c8","","H₂",0),
    ("ni","hcl","Ni + 2HCl → NiCl₂ + H₂↑","g","никель постепенно растворяется, выделяется H₂","#a9d8b1","","H₂",0),
    ("sn","hcl","Sn + 2HCl → SnCl₂ + H₂↑","g","олово растворяется с выделением H₂","#f8fbff","","H₂",0),
    ("pb","hcl","Pb + 2HCl → PbCl₂↓ + H₂↑","x","на свинце образуется белый PbCl₂, выделение H₂ постепенно замедляется","#f8fbff","#ffffff","H₂",0),
    ("cu","hcl","Cu + HCl → реакция не идёт","z","медь не вытесняет водород из неокисляющей кислоты","#f8fbff","","",0),
    ("ag","hcl","Ag + HCl → реакция не идёт","z","серебро не вытесняет водород из неокисляющей кислоты","#f8fbff","","",0),

    ("mg","h2so4","Mg + H₂SO₄(разб.) → MgSO₄ + H₂↑","g","металл растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("al","h2so4","2Al + 3H₂SO₄(разб.) → Al₂(SO₄)₃ + 3H₂↑","g","алюминий растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("zn","h2so4","Zn + H₂SO₄(разб.) → ZnSO₄ + H₂↑","g","цинк растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("cr","h2so4","Cr + H₂SO₄(разб.) → CrSO₄ + H₂↑","g","хром растворяется, выделяется H₂","#91a7bd","","H₂",0),
    ("fe","h2so4","Fe + H₂SO₄(разб.) → FeSO₄ + H₂↑","x","железо растворяется, выделяется H₂, раствор становится светло-зелёным","#bfe7c5","","H₂",0),
    ("pb","h2so4","Pb + H₂SO₄(разб.) → PbSO₄↓ + H₂↑","x","образуется белая плёнка PbSO₄, реакция быстро замедляется","#f8fbff","#ffffff","H₂",0),
    ("cu","h2so4","Cu + H₂SO₄(разб.) → реакция не идёт","z","медь не вытесняет водород из разбавленной H₂SO₄","#f8fbff","","",0),
    ("ag","h2so4","Ag + H₂SO₄(разб.) → реакция не идёт","z","серебро не вытесняет водород из разбавленной H₂SO₄","#f8fbff","","",0),

    # Oxidising acids: HNO3 and concentrated H2SO4
    ("cu","hno3","3Cu + 8HNO₃(разб.) → 3Cu(NO₃)₂ + 2NO↑ + 4H₂O","x","медь растворяется, раствор становится голубым, выделяется бесцветный NO","#42baf5","","NO",0),
    ("ag","hno3","3Ag + 4HNO₃(разб.) → 3AgNO₃ + NO↑ + 2H₂O","g","серебро растворяется, выделяется бесцветный NO","#f8fbff","","NO",0),

    ("cu","hno3_conc","Cu + 4HNO₃(конц.) → Cu(NO₃)₂ + 2NO₂↑ + 2H₂O","x","медь растворяется, раствор становится голубым, выделяется бурый NO₂","#42baf5","","NO₂",0),
    ("ag","hno3_conc","Ag + 2HNO₃(конц.) → AgNO₃ + NO₂↑ + H₂O","g","серебро растворяется, выделяется бурый NO₂","#f8fbff","","NO₂",0),
    ("zn","hno3_conc","Zn + 4HNO₃(конц.) → Zn(NO₃)₂ + 2NO₂↑ + 2H₂O","g","цинк растворяется, выделяется бурый NO₂","#f8fbff","","NO₂",0),
    ("mg","hno3_conc","Mg + 4HNO₃(конц.) → Mg(NO₃)₂ + 2NO₂↑ + 2H₂O","g","магний растворяется, выделяется бурый NO₂","#f8fbff","","NO₂",0),
    ("pb","hno3_conc","Pb + 4HNO₃(конц.) → Pb(NO₃)₂ + 2NO₂↑ + 2H₂O","g","свинец растворяется, выделяется бурый NO₂","#f8fbff","","NO₂",0),
    ("c","hno3_conc","C + 4HNO₃(конц.) → CO₂↑ + 4NO₂↑ + 2H₂O","g","углерод окисляется, выделяются газы, заметен бурый NO₂","#f8fbff","","NO₂",0),
    ("s","hno3_conc","S + 6HNO₃(конц.) → H₂SO₄ + 6NO₂↑ + 2H₂O","g","сера растворяется, выделяется бурый NO₂","#f8fbff","","NO₂",0),
    ("p","hno3_conc","P + 5HNO₃(конц.) → H₃PO₄ + 5NO₂↑ + H₂O","g","фосфор окисляется, выделяется бурый NO₂","#f8fbff","","NO₂",0),

    ("al","hno3_conc","Al + HNO₃(конц., холодн.) → реакция не идёт (пассивация)","z","алюминий пассивируется холодной концентрированной HNO₃","#f8fbff","","",0),
    ("fe","hno3_conc","Fe + HNO₃(конц., холодн.) → реакция не идёт (пассивация)","z","железо пассивируется холодной концентрированной HNO₃","#f8fbff","","",0),
    ("cr","hno3_conc","Cr + HNO₃(конц., холодн.) → реакция не идёт (пассивация)","z","хром пассивируется холодной концентрированной HNO₃","#f8fbff","","",0),
    ("al","hno3_conc","Al + 6HNO₃(конц.) —t°→ Al(NO₃)₃ + 3NO₂↑ + 3H₂O","g","при нагревании пассивная плёнка разрушается, выделяется бурый NO₂","#f8fbff","","NO₂",1),
    ("fe","hno3_conc","Fe + 6HNO₃(конц.) —t°→ Fe(NO₃)₃ + 3NO₂↑ + 3H₂O","x","при нагревании железо растворяется, выделяется бурый NO₂, раствор желтеет","#e2b35e","","NO₂",1),
    ("cr","hno3_conc","Cr + 6HNO₃(конц.) —t°→ Cr(NO₃)₃ + 3NO₂↑ + 3H₂O","x","при нагревании хром растворяется, выделяется бурый NO₂","#6e966f","","NO₂",1),

    ("cu","h2so4_conc","Cu + 2H₂SO₄(конц.) —t°→ CuSO₄ + SO₂↑ + 2H₂O","x","при нагревании медь растворяется, раствор становится голубым, выделяется SO₂","#42baf5","","SO₂",1),
    ("ag","h2so4_conc","2Ag + 2H₂SO₄(конц.) —t°→ Ag₂SO₄ + SO₂↑ + 2H₂O","g","при нагревании серебро растворяется, выделяется SO₂","#f8fbff","","SO₂",1),
    ("c","h2so4_conc","C + 2H₂SO₄(конц.) —t°→ CO₂↑ + 2SO₂↑ + 2H₂O","g","при нагревании углерод окисляется, выделяется SO₂","#f8fbff","","SO₂",1),
    ("s","h2so4_conc","S + 2H₂SO₄(конц.) —t°→ 3SO₂↑ + 2H₂O","g","при нагревании сера растворяется, выделяется SO₂","#f8fbff","","SO₂",1),
    ("p","h2so4_conc","2P + 5H₂SO₄(конц.) —t°→ 2H₃PO₄ + 5SO₂↑ + 2H₂O","g","при нагревании фосфор окисляется, выделяется SO₂","#f8fbff","","SO₂",1),
    ("al","h2so4_conc","Al + H₂SO₄(конц., холодн.) → реакция не идёт (пассивация)","z","алюминий пассивируется холодной концентрированной H₂SO₄","#f8fbff","","",0),
    ("fe","h2so4_conc","Fe + H₂SO₄(конц., холодн.) → реакция не идёт (пассивация)","z","железо пассивируется холодной концентрированной H₂SO₄","#f8fbff","","",0),
    ("cr","h2so4_conc","Cr + H₂SO₄(конц., холодн.) → реакция не идёт (пассивация)","z","хром пассивируется холодной концентрированной H₂SO₄","#f8fbff","","",0),
    ("al","h2so4_conc","2Al + 6H₂SO₄(конц.) —t°→ Al₂(SO₄)₃ + 3SO₂↑ + 6H₂O","g","при нагревании алюминий растворяется, выделяется SO₂","#f8fbff","","SO₂",1),
    ("fe","h2so4_conc","2Fe + 6H₂SO₄(конц.) —t°→ Fe₂(SO₄)₃ + 3SO₂↑ + 6H₂O","x","при нагревании железо растворяется, выделяется SO₂, раствор желтеет","#e1b562","","SO₂",1),
    ("cr","h2so4_conc","2Cr + 6H₂SO₄(конц.) —t°→ Cr₂(SO₄)₃ + 3SO₂↑ + 6H₂O","x","при нагревании хром растворяется, выделяется SO₂, раствор становится зелёным","#6e966f","","SO₂",1),

    # Concentrated oxidising acids with Fe(II) compounds
    ("feo","hno3","3FeO + 10HNO₃(разб.) → 3Fe(NO₃)₃ + NO↑ + 5H₂O","x","чёрный FeO растворяется, Fe(II) окисляется до Fe(III), выделяется NO","#e2b35e","","NO",0),
    ("feo","hno3_conc","FeO + 4HNO₃(конц.) → Fe(NO₃)₃ + NO₂↑ + 2H₂O","x","чёрный FeO растворяется, раствор желтеет, выделяется бурый NO₂","#e2b35e","","NO₂",0),
    ("feoh2","hno3","3Fe(OH)₂ + 10HNO₃(разб.) → 3Fe(NO₃)₃ + NO↑ + 8H₂O","x","светло-зелёный Fe(OH)₂ растворяется и окисляется до Fe(III), выделяется NO","#e2b35e","","NO",0),
    ("feoh2","hno3_conc","Fe(OH)₂ + 4HNO₃(конц.) → Fe(NO₃)₃ + NO₂↑ + 3H₂O","x","Fe(OH)₂ растворяется, раствор желтеет, выделяется бурый NO₂","#e2b35e","","NO₂",0),
    ("feo","h2so4_conc","2FeO + 4H₂SO₄(конц.) → Fe₂(SO₄)₃ + SO₂↑ + 4H₂O","x","чёрный FeO растворяется, Fe(II) окисляется до Fe(III), выделяется SO₂","#e1b562","","SO₂",0),
    ("feoh2","h2so4_conc","2Fe(OH)₂ + 4H₂SO₄(конц.) → Fe₂(SO₄)₃ + SO₂↑ + 6H₂O","x","Fe(OH)₂ растворяется и окисляется до Fe(III), выделяется SO₂","#e1b562","","SO₂",0),

    # Metals + salt solutions — EGE experiments
    # Copper(II) salts: a more active metal dissolves and copper plates onto it.
    ("fe","cuso4","Fe + CuSO₄ → FeSO₄ + Cu↓","x","голубая окраска ослабевает, раствор становится светло-зелёным, на железе появляется красно-бурый налёт Cu","#bfe7c5","#b96f4a","",0),
    ("zn","cuso4","Zn + CuSO₄ → ZnSO₄ + Cu↓","x","голубая окраска исчезает, на цинке появляется красно-бурый налёт Cu","#f8fbff","#b96f4a","",0),
    ("mg","cuso4","Mg + CuSO₄ → MgSO₄ + Cu↓","x","голубая окраска исчезает, на магнии выделяется красно-бурая медь","#f8fbff","#b96f4a","",0),
    ("pb","cuso4","Pb + CuSO₄ → PbSO₄↓ + Cu↓","x","на свинце появляется медь и белый слой PbSO₄, реакция постепенно замедляется","#f8fbff","#b96f4a","",0),
    ("fe","cucl2","Fe + CuCl₂ → FeCl₂ + Cu↓","x","голубовато-зелёная окраска ослабевает, раствор становится светло-зелёным, на железе выделяется Cu","#c8e5c8","#b96f4a","",0),
    ("zn","cucl2","Zn + CuCl₂ → ZnCl₂ + Cu↓","x","окраска раствора исчезает, на цинке выделяется красно-бурая медь","#f8fbff","#b96f4a","",0),
    ("mg","cucl2","Mg + CuCl₂ → MgCl₂ + Cu↓","x","окраска раствора исчезает, на магнии выделяется красно-бурая медь","#f8fbff","#b96f4a","",0),
    ("al","cucl2","2Al + 3CuCl₂ → 2AlCl₃ + 3Cu↓","x","алюминий растворяется, раствор обесцвечивается, выделяется красно-бурая медь","#f8fbff","#b96f4a","",0),

    # Silver nitrate: metallic silver grows on the more active metal.
    ("cu","agno3","Cu + 2AgNO₃ → Cu(NO₃)₂ + 2Ag↓","x","на меди растут серебристые кристаллы Ag, раствор становится голубым","#42baf5","#d8dadd","",0),
    ("fe","agno3","Fe + 2AgNO₃ → Fe(NO₃)₂ + 2Ag↓","x","на железе выделяется серебро, раствор становится светло-зелёным","#c8e5c8","#d8dadd","",0),
    ("zn","agno3","Zn + 2AgNO₃ → Zn(NO₃)₂ + 2Ag↓","x","на цинке выделяются серебристые кристаллы Ag","#f8fbff","#d8dadd","",0),
    ("mg","agno3","Mg + 2AgNO₃ → Mg(NO₃)₂ + 2Ag↓","x","магний растворяется, на поверхности выделяется серебро","#f8fbff","#d8dadd","",0),
    ("pb","agno3","Pb + 2AgNO₃ → Pb(NO₃)₂ + 2Ag↓","x","на свинце появляются серебристые кристаллы Ag","#f8fbff","#d8dadd","",0),

    # Iron(II) salts: Mg and Zn displace iron.
    ("mg","feso4","Mg + FeSO₄ → MgSO₄ + Fe↓","x","светло-зелёная окраска исчезает, на магнии появляется тёмно-серый налёт Fe","#f8fbff","#666b70","",0),
    ("zn","feso4","Zn + FeSO₄ → ZnSO₄ + Fe↓","x","светло-зелёная окраска исчезает, на цинке появляется тёмно-серый налёт Fe","#f8fbff","#666b70","",0),
    ("mg","fecl2","Mg + FeCl₂ → MgCl₂ + Fe↓","x","светло-зелёная окраска исчезает, на магнии выделяется тёмно-серое Fe","#f8fbff","#666b70","",0),
    ("zn","fecl2","Zn + FeCl₂ → ZnCl₂ + Fe↓","x","светло-зелёная окраска исчезает, на цинке выделяется тёмно-серое Fe","#f8fbff","#666b70","",0),

    # Fe(III) salts are oxidising: the metal can reduce Fe(III) to Fe(II).
    ("cu","fecl3","Cu + 2FeCl₃ → CuCl₂ + 2FeCl₂","c","жёлто-бурая окраска Fe(III) исчезает, медь растворяется, появляется голубовато-зелёный оттенок Cu(II)/Fe(II)","#6fae93","","",0),
    ("fe","fecl3","Fe + 2FeCl₃ → 3FeCl₂","c","железо растворяется, жёлтая окраска исчезает, раствор становится светло-зелёным","#c8e5c8","","",0),
    ("zn","fecl3","Zn + 2FeCl₃ → ZnCl₂ + 2FeCl₂","c","цинк растворяется, жёлтая окраска Fe(III) сменяется светло-зелёной Fe(II)","#c8e5c8","","",0),

    # Highly active alkali metals in salt solutions first react with water.
    ("na","cuso4","2Na + CuSO₄ + 2H₂O → Cu(OH)₂↓ + Na₂SO₄ + H₂↑","x","натрий бурно реагирует с водой: выделяется H₂ и выпадает голубой Cu(OH)₂","#eaf7ff","#39bced","H₂",0),
    ("k","cuso4","2K + CuSO₄ + 2H₂O → Cu(OH)₂↓ + K₂SO₄ + H₂↑","x","калий очень бурно реагирует с водой: выделяется H₂ и выпадает голубой Cu(OH)₂","#eaf7ff","#39bced","H₂",0),

    # Important negative experiments for the activity series.
    ("cu","feso4","Cu + FeSO₄ → реакция не идёт","z","Cu менее активна, чем Fe, поэтому железо из соли не вытесняет","#bfe7c5","","",0),
    ("cu","fecl2","Cu + FeCl₂ → реакция не идёт","z","Cu менее активна, чем Fe, поэтому железо из соли не вытесняет","#c8e5c8","","",0),
    ("cu","znso4","Cu + ZnSO₄ → реакция не идёт","z","Cu менее активна, чем Zn, поэтому цинк из соли не вытесняет","#f8fbff","","",0),
    ("ag","cuso4","Ag + CuSO₄ → реакция не идёт","z","Ag менее активна, чем Cu, поэтому медь из соли не вытесняет","#42baf5","","",0),
    ("fe","znso4","Fe + ZnSO₄ → реакция не идёт","z","Fe менее активно, чем Zn, поэтому цинк из соли не вытесняет","#f8fbff","","",0),
    ("zn","mgso4","Zn + MgSO₄ → реакция не идёт","z","Zn менее активен, чем Mg, поэтому магний из соли не вытесняет","#f8fbff","","",0),

    # Amphoteric simple substances + alkali
    ("al","naoh","2Al + 2NaOH + 6H₂O → 2Na[Al(OH)₄] + 3H₂↑","g","алюминий растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("zn","naoh","Zn + 2NaOH + 2H₂O → Na₂[Zn(OH)₄] + H₂↑","g","цинк растворяется, выделяется H₂","#f8fbff","","H₂",0),
    ("si","naoh","Si + 2NaOH + H₂O → Na₂SiO₃ + 2H₂↑","g","кремний растворяется, выделяется H₂","#f8fbff","","H₂",0),

    # Simple substances with oxygen / halogens
    ("h2","o2","2H₂ + O₂ —t°→ 2H₂O","x","при поджигании реакция идёт быстро с выделением тепла","#eaf7ff","","",1),
    ("mg","o2","2Mg + O₂ —t°→ 2MgO","x","магний горит ослепительно-белым светом, образуется белый MgO","#ffffff","#ffffff","",1),
    ("al","o2","4Al + 3O₂ —t°→ 2Al₂O₃","x","при сильном нагревании алюминий окисляется, образуется белый Al₂O₃","#f8fbff","#ffffff","",1),
    ("fe","o2","3Fe + 2O₂ —t°→ Fe₃O₄","x","железо горит искрами, образуется чёрный Fe₃O₄","#f8fbff","#202020","",1),
    ("cu","o2","2Cu + O₂ —t°→ 2CuO","x","медь чернеет: образуется CuO","#f8fbff","#161616","",1),
    ("c","o2","C + O₂ —t°→ CO₂","g","углерод сгорает, образуется CO₂","#f8fbff","","CO₂",1),
    ("s","o2","S + O₂ —t°→ SO₂","g","сера горит голубым пламенем, образуется SO₂","#f8fbff","","SO₂",1),
    ("p","o2","4P + 5O₂ —t°→ 2P₂O₅","x","фосфор ярко горит, образуется белый дым P₂O₅","#f8fbff","#ffffff","",1),
    ("si","o2","Si + O₂ —t°→ SiO₂","x","при сильном нагревании образуется SiO₂","#f8fbff","#ffffff","",1),
    ("fe","cl2","2Fe + 3Cl₂ —t°→ 2FeCl₃","x","железо горит в хлоре, образуется буро-жёлтый FeCl₃","#d99d2b","","",1),
    ("cu","cl2","Cu + Cl₂ —t°→ CuCl₂","x","медь реагирует с хлором, образуется хлорид меди(II)","#55b7a1","","",1),
    ("cl2","kbr","Cl₂ + 2KBr → 2KCl + Br₂","c","появляется оранжево-бурая окраска Br₂","#a95b38","","",0),
    ("cl2","ki","Cl₂ + 2KI → 2KCl + I₂","c","появляется бурая окраска I₂","#6b493e","","",0),
    ("br2","ki","Br₂ + 2KI → 2KBr + I₂","c","окраска Br₂ сменяется бурой окраской I₂","#6b493e","","",0),
    ("cl2","h2o","Cl₂ + H₂O ⇄ HCl + HClO","c","жёлто-зелёная окраска хлора постепенно бледнеет","#f3f7da","","",0),
    ("cl2","naoh","Cl₂ + 2NaOH → NaCl + NaClO + H₂O","c","хлор поглощается, жёлто-зелёная окраска исчезает","#f8fbff","","",0),
    ("cl2","naoh","3Cl₂ + 6NaOH —t°→ 5NaCl + NaClO₃ + 3H₂O","c","при нагревании хлор поглощается щёлочью","#f8fbff","","",1),
    ("br2","naoh","Br₂ + 2NaOH → NaBr + NaBrO + H₂O","c","буро-оранжевая окраска брома исчезает","#f8fbff","","",0),
    ("br2","naoh","3Br₂ + 6NaOH —t°→ 5NaBr + NaBrO₃ + 3H₂O","c","при нагревании окраска брома исчезает","#f8fbff","","",1),
    ("i2","naoh","3I₂ + 6NaOH —t°→ 5NaI + NaIO₃ + 3H₂O","c","при нагревании окраска иода исчезает","#f8fbff","","",1),
    ("s","naoh","3S + 6NaOH —t°→ 2Na₂S + Na₂SO₃ + 3H₂O","c","при нагревании сера растворяется в щёлочи","#f8fbff","","",1),

    # EGE task 6 pilot reactions (uploaded worksheet, pages 1-4)
    ("aloh3","koh","Al(OH)₃ + KOH → K[Al(OH)₄]","c","белый студенистый Al(OH)₃ растворяется в избытке KOH","#f8fbff","","",0),
    ("caoh2","cah2po4_2","Ca(H₂PO₄)₂ + 2Ca(OH)₂ → Ca₃(PO₄)₂↓ + 4H₂O","p","образуется белый осадок Ca₃(PO₄)₂","#f8fbff","#ffffff","",0),
    ("caoh2","hf","Ca(OH)₂ + 2HF → CaF₂↓ + 2H₂O","p","образуется белый осадок CaF₂","#f8fbff","#ffffff","",0),
    ("znoh2","lioh","Zn(OH)₂ + 2LiOH → Li₂[Zn(OH)₄]","c","белый Zn(OH)₂ растворяется в избытке LiOH","#f8fbff","","",0),
    ("fecl2","lioh","FeCl₂ + 2LiOH → Fe(OH)₂↓ + 2LiCl","p","образуется светло-зелёный осадок Fe(OH)₂","#eef7ee","#89b98e","",0),
    ("fecl2","kf","FeCl₂ + 2KF → FeF₂↓ + 2KCl","p","образуется светлый осадок FeF₂","#f8fbff","#f2f2ee","",0),
    ("ali3","nh3","AlI₃ + 3NH₃·H₂O → Al(OH)₃↓ + 3NH₄I","p","образуется белый студенистый осадок Al(OH)₃","#f8fbff","#ffffff","",0),
    ("h2so4","nh3","H₂SO₄ + 2NH₃·H₂O → (NH₄)₂SO₄ + 2H₂O","n","реакция протекает без видимого признака","#f8fbff","","",0),
    ("cahco3_2","hno3","Ca(HCO₃)₂ + 2HNO₃ → Ca(NO₃)₂ + 2CO₂↑ + 2H₂O","g","выделяются пузырьки CO₂","#f8fbff","","CO₂",0),
    ("cahco3_2","caoh2","Ca(HCO₃)₂ + Ca(OH)₂ → 2CaCO₃↓ + 2H₂O","p","образуется белый осадок CaCO₃","#f8fbff","#ffffff","",0),
    ("caoh2","cuno3","Ca(OH)₂ + Cu(NO₃)₂ → Cu(OH)₂↓ + Ca(NO₃)₂","p","образуется голубой осадок Cu(OH)₂","#eaf7ff","#39bced","",0),
    ("caoh2","hi","Ca(OH)₂ + 2HI → CaI₂ + 2H₂O","n","реакция нейтрализации без видимого признака","#f8fbff","","",0),
    ("baoh2","cucl2","Ba(OH)₂ + CuCl₂ → Cu(OH)₂↓ + BaCl₂","p","образуется голубой осадок Cu(OH)₂","#eaf7ff","#39bced","",0),
    ("baoh2","na2hpo4","Ba(OH)₂ + Na₂HPO₄ → BaHPO₄↓ + 2NaOH","p","образуется белый осадок BaHPO₄","#f8fbff","#ffffff","",0),
    ("nh4cl","pbno3","2NH₄Cl + Pb(NO₃)₂ → PbCl₂↓ + 2NH₄NO₃","p","образуется белый осадок PbCl₂","#f8fbff","#ffffff","",0),
    ("mgcl2","baoh2","MgCl₂ + Ba(OH)₂ → Mg(OH)₂↓ + BaCl₂","p","образуется белый осадок Mg(OH)₂","#f8fbff","#ffffff","",0),
    ("mgcl2","na3po4","3MgCl₂ + 2Na₃PO₄ → Mg₃(PO₄)₂↓ + 6NaCl","p","образуется белый осадок Mg₃(PO₄)₂","#f8fbff","#ffffff","",0),
    ("cucl2","agf","CuCl₂ + 2AgF → 2AgCl↓ + CuF₂","p","образуется белый осадок AgCl","#d9f4ff","#ffffff","",0),
    ("alcl3","agno3","AlCl₃ + 3AgNO₃ → 3AgCl↓ + Al(NO₃)₃","p","образуется белый осадок AgCl","#f8fbff","#ffffff","",0),
    ("alcl3","nh3","AlCl₃ + 3NH₃·H₂O → Al(OH)₃↓ + 3NH₄Cl","p","образуется белый студенистый осадок Al(OH)₃","#f8fbff","#ffffff","",0),

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

    # Non-redox reactions of oxidising acids with basic/amphoteric oxides
    # HNO3: oxidation states do not change; this is ordinary acid-base dissolution.
    ("na2o","hno3","Na₂O + 2HNO₃ → 2NaNO₃ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("k2o","hno3","K₂O + 2HNO₃ → 2KNO₃ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cao","hno3","CaO + 2HNO₃ → Ca(NO₃)₂ + H₂O","c","белый CaO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("mgo","hno3","MgO + 2HNO₃ → Mg(NO₃)₂ + H₂O","c","белый MgO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("al2o3","hno3","Al₂O₃ + 6HNO₃ → 2Al(NO₃)₃ + 3H₂O","c","белый Al₂O₃ растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("zno","hno3","ZnO + 2HNO₃ → Zn(NO₃)₂ + H₂O","c","белый ZnO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cr2o3","hno3","Cr₂O₃ + 6HNO₃ → 2Cr(NO₃)₃ + 3H₂O","c","зелёный Cr₂O₃ растворяется, образуется зелёный раствор Cr(III)","#6e966f","","",0),
    ("fe2o3","hno3","Fe₂O₃ + 6HNO₃ → 2Fe(NO₃)₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, образуется жёлтый раствор Fe(III)","#e2b35e","","",0),
    ("cuo","hno3","CuO + 2HNO₃ → Cu(NO₃)₂ + H₂O","c","чёрный CuO растворяется, образуется голубой раствор Cu(NO₃)₂","#42baf5","","",0),

    # Concentrated HNO3 with the same oxides: still no redox for these oxidation states.
    ("na2o","hno3_conc","Na₂O + 2HNO₃(конц.) → 2NaNO₃ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("k2o","hno3_conc","K₂O + 2HNO₃(конц.) → 2KNO₃ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cao","hno3_conc","CaO + 2HNO₃(конц.) → Ca(NO₃)₂ + H₂O","c","белый CaO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("mgo","hno3_conc","MgO + 2HNO₃(конц.) → Mg(NO₃)₂ + H₂O","c","белый MgO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("al2o3","hno3_conc","Al₂O₃ + 6HNO₃(конц.) → 2Al(NO₃)₃ + 3H₂O","c","белый Al₂O₃ растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("zno","hno3_conc","ZnO + 2HNO₃(конц.) → Zn(NO₃)₂ + H₂O","c","белый ZnO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cr2o3","hno3_conc","Cr₂O₃ + 6HNO₃(конц.) → 2Cr(NO₃)₃ + 3H₂O","c","зелёный Cr₂O₃ растворяется, образуется зелёный раствор Cr(III)","#6e966f","","",0),
    ("fe2o3","hno3_conc","Fe₂O₃ + 6HNO₃(конц.) → 2Fe(NO₃)₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, образуется жёлтый раствор Fe(III)","#e2b35e","","",0),
    ("cuo","hno3_conc","CuO + 2HNO₃(конц.) → Cu(NO₃)₂ + H₂O","c","чёрный CuO растворяется, образуется голубой раствор Cu(NO₃)₂","#42baf5","","",0),

    # Concentrated H2SO4 can also behave simply as an acid with oxides that are not reducing it.
    ("na2o","h2so4_conc","Na₂O + H₂SO₄(конц.) → Na₂SO₄ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("k2o","h2so4_conc","K₂O + H₂SO₄(конц.) → K₂SO₄ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cao","h2so4_conc","CaO + H₂SO₄(конц.) → CaSO₄↓ + H₂O","p","на поверхности образуется белый CaSO₄","#f8fbff","#ffffff","",0),
    ("mgo","h2so4_conc","MgO + H₂SO₄(конц.) → MgSO₄ + H₂O","c","белый MgO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("al2o3","h2so4_conc","Al₂O₃ + 3H₂SO₄(конц.) → Al₂(SO₄)₃ + 3H₂O","c","белый Al₂O₃ растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("zno","h2so4_conc","ZnO + H₂SO₄(конц.) → ZnSO₄ + H₂O","c","белый ZnO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cr2o3","h2so4_conc","Cr₂O₃ + 3H₂SO₄(конц.) → Cr₂(SO₄)₃ + 3H₂O","c","зелёный Cr₂O₃ растворяется, образуется зелёный раствор Cr(III)","#6e966f","","",0),
    ("fe2o3","h2so4_conc","Fe₂O₃ + 3H₂SO₄(конц.) → Fe₂(SO₄)₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, образуется жёлтый раствор Fe(III)","#e1b562","","",0),
    ("cuo","h2so4_conc","CuO + H₂SO₄(конц.) → CuSO₄ + H₂O","c","чёрный CuO растворяется, образуется голубой раствор CuSO₄","#42baf5","","",0),

    # Basic / amphoteric oxides + acids
    ("na2o","hcl","Na₂O + 2HCl → 2NaCl + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cao","hcl","CaO + 2HCl → CaCl₂ + H₂O","c","белый CaO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("mgo","hcl","MgO + 2HCl → MgCl₂ + H₂O","c","белый MgO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cuo","hcl","CuO + 2HCl → CuCl₂ + H₂O","c","чёрный CuO растворяется, образуется голубой раствор CuCl₂","#42baf5","","",0),
    ("feo","hcl","FeO + 2HCl → FeCl₂ + H₂O","c","чёрный FeO растворяется, образуется светло-зелёный раствор","#c8e5c8","","",0),
    ("fe2o3","hcl","Fe₂O₃ + 6HCl → 2FeCl₃ + 3H₂O","c","бурый Fe₂O₃ растворяется, раствор желтеет","#d99d2b","","",0),
    ("fe3o4","hcl","Fe₃O₄ + 8HCl → FeCl₂ + 2FeCl₃ + 4H₂O","c","чёрный Fe₃O₄ растворяется","#c8b56e","","",0),
    ("al2o3","hcl","Al₂O₃ + 6HCl → 2AlCl₃ + 3H₂O","c","белый Al₂O₃ растворяется","#f8fbff","","",0),
    ("zno","hcl","ZnO + 2HCl → ZnCl₂ + H₂O","c","белый ZnO растворяется","#f8fbff","","",0),
    ("cr2o3","hcl","Cr₂O₃ + 6HCl → 2CrCl₃ + 3H₂O","c","зелёный Cr₂O₃ растворяется, образуется зелёный раствор","#6e966f","","",0),
    ("na2o","h2so4","Na₂O + H₂SO₄ → Na₂SO₄ + H₂O","c","белое твёрдое вещество растворяется, образуется бесцветный раствор","#f8fbff","","",0),
    ("cao","h2so4","CaO + H₂SO₄ → CaSO₄ + H₂O","p","образуется белый малорастворимый CaSO₄","#f8fbff","#ffffff","",0),
    ("mgo","h2so4","MgO + H₂SO₄ → MgSO₄ + H₂O","c","белый MgO растворяется, образуется бесцветный раствор","#f8fbff","","",0),
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

    # Gas-forming salts + acids / alkalis
    ("k2co3","hcl","K₂CO₃ + 2HCl → 2KCl + CO₂↑ + H₂O","g","бурное выделение пузырьков CO₂","#f8fbff","","CO₂",0),
    ("k2co3","h2so4","K₂CO₃ + H₂SO₄ → K₂SO₄ + CO₂↑ + H₂O","g","бурное выделение пузырьков CO₂","#f8fbff","","CO₂",0),
    ("k2co3","hno3","K₂CO₃ + 2HNO₃ → 2KNO₃ + CO₂↑ + H₂O","g","бурное выделение пузырьков CO₂","#f8fbff","","CO₂",0),
    ("k2so3","hcl","K₂SO₃ + 2HCl → 2KCl + SO₂↑ + H₂O","g","выделяются пузырьки SO₂","#f8fbff","","SO₂",0),
    ("k2so3","h2so4","K₂SO₃ + H₂SO₄ → K₂SO₄ + SO₂↑ + H₂O","g","выделяются пузырьки SO₂","#f8fbff","","SO₂",0),
    ("k2s","hcl","K₂S + 2HCl → 2KCl + H₂S↑","g","выделяются пузырьки H₂S","#f8fbff","","H₂S",0),
    ("k2s","h2so4","K₂S + H₂SO₄(разб.) → K₂SO₄ + H₂S↑","g","выделяются пузырьки H₂S","#f8fbff","","H₂S",0),
    ("nh4cl","naoh","NH₄Cl + NaOH —t°→ NaCl + NH₃↑ + H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),
    ("nh4cl","koh","NH₄Cl + KOH —t°→ KCl + NH₃↑ + H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),
    ("nh4no3","koh","NH₄NO₃ + KOH —t°→ KNO₃ + NH₃↑ + H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),
    ("nh42so4","koh","(NH₄)₂SO₄ + 2KOH —t°→ K₂SO₄ + 2NH₃↑ + 2H₂O","g","при нагревании выделяется NH₃","#f8fbff","","NH₃",1),

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
