"""Pilot bank for the interactive EGE chemistry task 6 trainer.

The wording is transcribed from the user-provided "6_zadania.pdf" (pages 1-4).
Answers and experiment metadata are authored for the trainer.
"""

TASK6_BANK = [
    {
        "id":"t6_001",
        "text":"Даны две пробирки с осадком гидроксида алюминия. В одну из них добавили раствор вещества X, а в другую – раствор вещества Y. В результате в каждой из пробирок наблюдали растворение осадка. При этом в пробирке с раствором вещества Y произошла реакция, которую описывает сокращённое ионное уравнение Al(OH)₃ + 3H⁺ = Al³⁺ + 3H₂O. Выберите вещества X и Y.",
        "base_x":"aloh3","base_y":"aloh3",
        "options":[["h2so4","серная кислота"],["nahco3","гидрокарбонат натрия"],["koh","гидроксид калия"],["nh4cl","хлорид аммония"],["hf","фтороводород"]],
        "answer_x":"koh","answer_y":"h2so4","heat_x":False,"heat_y":False,"excess_x":"koh","excess_y":"",
        "why":"Al(OH)₃ амфотерен: растворяется в избытке щёлочи и в сильной кислоте. Ионное уравнение с H⁺ соответствует H₂SO₄.",
    },
    {
        "id":"t6_002",
        "text":"Даны две пробирки с раствором гидроксида кальция. В одну добавили раствор сильного электролита X, а в другую – раствор слабого электролита Y. В каждой пробирке наблюдали образование осадка. Выберите X и Y.",
        "base_x":"caoh2","base_y":"caoh2",
        "options":[["baco3","BaCO₃"],["hf","HF"],["hno3","HNO₃"],["ch3cooh","CH₃COOH"],["cah2po4_2","Ca(H₂PO₄)₂"]],
        "answer_x":"cah2po4_2","answer_y":"hf","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"Ca(H₂PO₄)₂ — электролит и даёт малорастворимый фосфат кальция; HF — слабый электролит и образует CaF₂.",
    },
    {
        "id":"t6_003",
        "text":"Даны две пробирки с осадком гидроксида цинка. В одну добавили раствор сильной кислоты X, а в другую – раствор сильного электролита Y. В каждой пробирке наблюдали растворение осадка. Выберите X и Y.",
        "base_x":"znoh2","base_y":"znoh2",
        "options":[["hf","фтороводородная кислота"],["lioh","гидроксид лития"],["nh3","аммиак"],["h2so4","серная кислота"],["na2so4","сульфат натрия"]],
        "answer_x":"h2so4","answer_y":"lioh","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"lioh",
        "why":"Zn(OH)₂ амфотерен. Сильная кислота H₂SO₄ растворяет осадок; избыток LiOH переводит его в растворимый гидроксокомплекс.",
    },
    {
        "id":"t6_004",
        "text":"Даны две пробирки с раствором хлорида железа(II). С веществом X образовалось нерастворимое основание. С веществом Y реакцию описывает Fe²⁺ + 2F⁻ = FeF₂. Выберите X и Y.",
        "base_x":"fecl2","base_y":"fecl2",
        "options":[["hf","фтороводородная кислота"],["agno3","нитрат серебра"],["nh4no3","нитрат аммония"],["lioh","гидроксид лития"],["kf","фторид калия"]],
        "answer_x":"lioh","answer_y":"kf","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"LiOH осаждает Fe(OH)₂, а KF даёт ионы F⁻ для образования FeF₂.",
    },
    {
        "id":"t6_005",
        "text":"В пробирки с растворами веществ X и Y пропускали аммиак. В пробирке X образовался белый осадок, а в пробирке Y реакция не сопровождалась видимыми признаками. Выберите X и Y.",
        "base_x":"nh3","base_y":"nh3",
        "options":[["nabr","бромид натрия"],["k2so3","сульфит калия"],["nh42co3","карбонат аммония"],["h2so4","серная кислота"],["ali3","иодид алюминия"]],
        "answer_x":"ali3","answer_y":"h2so4","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"NH₃·H₂O осаждает белый Al(OH)₃ из соли алюминия; с H₂SO₄ идёт нейтрализация без видимого признака.",
    },
    {
        "id":"t6_006",
        "text":"Даны две пробирки с раствором гидрокарбоната кальция. С веществом X наблюдали выделение газа, а с веществом Y — выпадение осадка. Выберите X и Y.",
        "base_x":"cahco3_2","base_y":"cahco3_2",
        "options":[["co2","CO₂"],["hno3","HNO₃"],["nh4oac","CH₃COONH₄"],["caoh2","Ca(OH)₂"],["baco3","BaCO₃"]],
        "answer_x":"hno3","answer_y":"caoh2","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"Кислота разлагает HCO₃⁻ с выделением CO₂, а Ca(OH)₂ переводит гидрокарбонат в CaCO₃↓.",
    },
    {
        "id":"t6_007",
        "text":"В одну пробирку с раствором гидроксида кальция добавили X и наблюдали осадок. В другую добавили Y; реакцию описывает H⁺ + OH⁻ = H₂O. Выберите X и Y.",
        "base_x":"caoh2","base_y":"caoh2",
        "options":[["hno2","азотистая кислота"],["cuno3","нитрат меди(II)"],["nh4cl","хлорид аммония"],["hi","иодоводородная кислота"],["koac","ацетат калия"]],
        "answer_x":"cuno3","answer_y":"hi","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"Cu²⁺ образует Cu(OH)₂↓, а HI — сильная кислота, поэтому нейтрализация описывается H⁺ + OH⁻ = H₂O.",
    },
    {
        "id":"t6_008",
        "text":"В одну пробирку с раствором гидроксида бария добавили сильный электролит X и получили нерастворимое основание. В другую добавили сильный электролит Y и получили нерастворимую соль. Выберите X и Y.",
        "base_x":"baoh2","base_y":"baoh2",
        "options":[["na2hpo4","гидрофосфат натрия"],["hno2","азотистая кислота"],["cucl2","хлорид меди(II)"],["nh4no3","нитрат аммония"],["agi","иодид серебра"]],
        "answer_x":"cucl2","answer_y":"na2hpo4","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"CuCl₂ даёт Cu(OH)₂↓, а Na₂HPO₄ — малорастворимый BaHPO₄.",
    },
    {
        "id":"t6_009",
        "text":"В одну пробирку с раствором хлорида аммония добавили X и нагрели — выделился газ с резким запахом. В другую добавили Y — выпал осадок. Выберите X и Y.",
        "base_x":"nh4cl","base_y":"nh4cl",
        "options":[["agi","иодид серебра"],["koh","гидроксид калия"],["pbno3","нитрат свинца(II)"],["hno3","азотная кислота"],["k2so3","сульфит калия"]],
        "answer_x":"koh","answer_y":"pbno3","heat_x":True,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"NH₄⁺ + OH⁻ при нагревании даёт NH₃↑; Pb²⁺ с Cl⁻ образует PbCl₂↓.",
    },
    {
        "id":"t6_010",
        "text":"Даны две пробирки с раствором хлорида магния. С веществом X образовался нерастворимый гидроксид, а с веществом Y — нерастворимая соль. Выберите X и Y.",
        "base_x":"mgcl2","base_y":"mgcl2",
        "options":[["caso4","CaSO₄"],["na3po4","Na₃PO₄"],["koac","CH₃COOK"],["cuno3","Cu(NO₃)₂"],["baoh2","Ba(OH)₂"]],
        "answer_x":"baoh2","answer_y":"na3po4","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"Ba(OH)₂ осаждает Mg(OH)₂, а PO₄³⁻ — Mg₃(PO₄)₂.",
    },
    {
        "id":"t6_011",
        "text":"В одну пробирку с раствором хлорида меди(II) добавили X и получили осадок красного цвета. В другую добавили раствор Y и получили нерастворимую соль. Выберите X и Y.",
        "base_x":"cucl2","base_y":"cucl2",
        "options":[["zno","оксид цинка"],["ag","серебро"],["agf","фторид серебра"],["zn","цинк"],["kbr","бромид калия"]],
        "answer_x":"zn","answer_y":"agf","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"Zn вытесняет Cu — появляется красно-бурая медь; AgF даёт Ag⁺, который осаждает AgCl.",
    },
    {
        "id":"t6_012",
        "text":"Даны две пробирки с раствором хлорида алюминия. В одну добавили сильный электролит X, в другую — слабый электролит Y. В каждой пробирке наблюдали образование осадка. Выберите X и Y.",
        "base_x":"alcl3","base_y":"alcl3",
        "options":[["feoh2","гидроксид железа(II)"],["agno3","нитрат серебра"],["nh3","аммиак"],["hi","иодоводород"],["nano3","нитрат натрия"]],
        "answer_x":"agno3","answer_y":"nh3","heat_x":False,"heat_y":False,"excess_x":"","excess_y":"",
        "why":"AgNO₃ — сильный электролит и осаждает AgCl; NH₃·H₂O — слабый электролит и осаждает Al(OH)₃.",
    },
]

def validate_task6_bank(known_reagents):
    for task in TASK6_BANK:
        if task["base_x"] not in known_reagents or task["base_y"] not in known_reagents:
            raise RuntimeError(f"Task6 unknown base: {task['id']}")
        ids=[x[0] for x in task["options"]]
        for reagent_id in ids:
            if reagent_id not in known_reagents:
                raise RuntimeError(f"Task6 unknown option {reagent_id}: {task['id']}")
        if task["answer_x"] not in ids or task["answer_y"] not in ids:
            raise RuntimeError(f"Task6 bad answer: {task['id']}")
    return True
