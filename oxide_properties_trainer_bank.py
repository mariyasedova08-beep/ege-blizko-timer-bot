"""80 вопросов для тренажёра «Свойства оксидов» ЕГЭ БЛИЗКО.

Каждый вопрос посвящён одному оксиду.
Каждый вариант ответа содержит ровно три вещества.
Условия реакций подразумевают стандартные школьные условия ЕГЭ; для реакций,
требующих нагревания/сплавления, это указано в формулировке вопроса.
"""

PROMPTS = (
    "С какими тремя веществами реагирует {oxide}?",
    "Выберите ряд из трёх веществ, каждое из которых реагирует с {oxide}.",
    "В каком наборе все три вещества взаимодействуют с {oxide}?",
    "Для {oxide} выберите три реагента, с каждым из которых возможна реакция.",
)

WRONG_BASIC = (
    "NaOH · KOH · NaCl",
    "O₂ · N₂ · CH₄",
    "KCl · NaNO₃ · H₂",
)
WRONG_CUO = (
    "NaOH · KOH · H₂O",
    "NaCl · KNO₃ · O₂",
    "N₂ · H₂O · NaNO₃",
)
WRONG_FEO = (
    "NaOH · KOH · H₂O",
    "NaCl · KNO₃ · N₂",
    "CH₄ · KCl · NaNO₃",
)
WRONG_ACIDIC = (
    "NaCl · KNO₃ · N₂",
    "O₂ · N₂ · CH₄",
    "KCl · NaNO₃ · H₂",
)
WRONG_CO2 = (
    "HCl · H₂SO₄ · HNO₃",
    "NaCl · KNO₃ · O₂",
    "N₂ · HCl · NaNO₃",
)
WRONG_SO2 = (
    "HCl · HNO₃ · NaCl",
    "NaCl · KNO₃ · N₂",
    "CH₄ · HCl · NaNO₃",
)
WRONG_SIO2 = (
    "H₂O · HCl · HNO₃",
    "O₂ · N₂ · H₂SO₄",
    "NaCl · KNO₃ · H₂O",
)
WRONG_AMPH = (
    "H₂O · NaCl · KNO₃",
    "O₂ · N₂ · CH₄",
    "KCl · NaNO₃ · H₂",
)

SPECS = (
    ("Na₂O", 5, (
        "H₂O · HCl · CO₂",
        "H₂SO₄ · SO₃ · H₂O",
        "HNO₃ · P₂O₅ · CO₂",
        "HCl · SO₂ · H₂O",
        "H₂SO₄ · N₂O₅ · H₂O",
    ), WRONG_BASIC),
    ("CaO", 5, (
        "H₂O · HCl · CO₂",
        "H₂SO₄ · SO₃ · H₂O",
        "HNO₃ · P₂O₅ · CO₂",
        "HCl · SO₂ · H₂O",
        "H₂SO₄ · N₂O₅ · H₂O",
    ), WRONG_BASIC),
    ("MgO", 4, (
        "HCl · H₂SO₄ · HNO₃",
        "HCl · SO₃ · P₂O₅",
        "HNO₃ · CO₂ · SO₃",
        "H₂SO₄ · SO₂ · P₂O₅",
    ), WRONG_BASIC),
    ("CuO", 8, (
        "HCl · H₂SO₄ · HNO₃",
        "H₂ · CO · C",
        "HCl · H₂ · CO",
        "H₂SO₄ · CO · C",
        "HNO₃ · H₂ · C",
        "HCl · H₂SO₄ · CO",
        "HNO₃ · CO · C",
        "HCl · HNO₃ · H₂",
    ), WRONG_CUO),
    ("FeO", 4, (
        "HCl · H₂SO₄ · HNO₃",
        "O₂ · HCl · H₂SO₄",
        "CO · H₂ · HCl",
        "C · CO · H₂SO₄",
    ), WRONG_FEO),
    ("CO₂", 8, (
        "H₂O · NaOH · CaO",
        "Na₂O · KOH · Ca(OH)₂",
        "MgO · Ba(OH)₂ · H₂O",
        "C · NaOH · CaO",
        "K₂O · Ca(OH)₂ · H₂O",
        "NaOH · MgO · BaO",
        "CaO · KOH · C",
        "Na₂O · Ba(OH)₂ · H₂O",
    ), WRONG_CO2),
    ("SO₂", 8, (
        "H₂O · NaOH · CaO",
        "O₂ · NaOH · K₂O",
        "H₂S · NaOH · CaO",
        "KOH · MgO · H₂O",
        "O₂ · Ca(OH)₂ · Na₂O",
        "H₂S · KOH · BaO",
        "NaOH · CaO · H₂O",
        "H₂S · Na₂O · KOH",
    ), WRONG_SO2),
    ("SO₃", 6, (
        "H₂O · NaOH · CaO",
        "KOH · MgO · H₂O",
        "BaO · Ca(OH)₂ · H₂O",
        "Na₂O · KOH · CaO",
        "MgO · NaOH · H₂O",
        "Ba(OH)₂ · K₂O · H₂O",
    ), WRONG_ACIDIC),
    ("SiO₂", 8, (
        "HF · NaOH · CaO",
        "KOH · Na₂CO₃ · CaCO₃",
        "HF · Mg · C",
        "NaOH · CaO · Na₂CO₃",
        "HF · KOH · MgO",
        "C · CaO · Na₂CO₃",
        "HF · NaOH · CaCO₃",
        "Mg · KOH · CaO",
    ), WRONG_SIO2),
    ("P₂O₅", 5, (
        "H₂O · NaOH · CaO",
        "KOH · MgO · H₂O",
        "BaO · Ca(OH)₂ · H₂O",
        "Na₂O · KOH · CaO",
        "MgO · NaOH · H₂O",
    ), WRONG_ACIDIC),
    ("Al₂O₃", 7, (
        "HCl · NaOH · KOH",
        "H₂SO₄ · NaOH · KOH",
        "HNO₃ · KOH · NaOH",
        "HCl · H₂SO₄ · NaOH",
        "HNO₃ · HCl · KOH",
        "H₂SO₄ · KOH · NaOH",
        "HCl · HNO₃ · NaOH",
    ), WRONG_AMPH),
    ("ZnO", 7, (
        "HCl · NaOH · H₂SO₄",
        "KOH · HNO₃ · HCl",
        "H₂SO₄ · NaOH · KOH",
        "HCl · CO · C",
        "HNO₃ · CO · C",
        "NaOH · HCl · CO",
        "KOH · H₂SO₄ · C",
    ), WRONG_AMPH),
    ("BeO", 3, (
        "HCl · NaOH · H₂SO₄",
        "KOH · HNO₃ · HCl",
        "H₂SO₄ · NaOH · KOH",
    ), WRONG_AMPH),
    ("Cr₂O₃", 2, (
        "HCl · H₂SO₄ · NaOH",
        "HNO₃ · KOH · HCl",
    ), WRONG_AMPH),
)


def _build_bank():
    bank = []
    index = 1
    for oxide, count, correct_rows, wrong_rows in SPECS:
        if count != len(correct_rows):
            raise RuntimeError(f"Count mismatch for {oxide}")
        for variant, correct in enumerate(correct_rows):
            prompt = PROMPTS[variant % len(PROMPTS)].format(oxide=oxide)
            # Для SiO2 и амфотерных оксидов некоторые реакции требуют нагревания
            # или сплавления; это стандартно подразумевается в заданиях ЕГЭ.
            if oxide in {"SiO₂", "Al₂O₃", "ZnO", "BeO", "Cr₂O₃"} and variant % 3 == 1:
                prompt += " При необходимости учитывайте нагревание/сплавление."
            bank.append((
                f"op{index:03d}",
                prompt,
                correct,
                tuple(wrong_rows),
            ))
            index += 1
    return tuple(bank)


OXIDE_PROPERTIES_BANK = _build_bank()

if len(OXIDE_PROPERTIES_BANK) != 80:
    raise RuntimeError(
        f"Oxide properties bank must contain 80 questions, got {len(OXIDE_PROPERTIES_BANK)}"
    )

for qid, prompt, correct, distractors in OXIDE_PROPERTIES_BANK:
    if len(distractors) != 3:
        raise RuntimeError(f"{qid}: expected 3 distractors")
    for option in (correct, *distractors):
        if len([part for part in option.split(" · ") if part.strip()]) != 3:
            raise RuntimeError(f"{qid}: every answer option must contain exactly 3 substances")
