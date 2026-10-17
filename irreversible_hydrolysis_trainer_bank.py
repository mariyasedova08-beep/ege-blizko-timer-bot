"""ЕГЭ БЛИЗКО — банк 50 вопросов по необратимому гидролизу.

Источник: учебный конспект «30(1).pdf», 8 страниц.
Формат аналогичен middle_salts_trainer_bank.py.
Этот модуль только хранит вопросы, не включает/регистрирует тренажёр в боте.
"""

IRREVERSIBLE_HYDROLYSIS_BANK = (
    ('gh001', 'Какие продукты образуются?\nKH + H₂O → ?', 'KOH + H₂', ('K₂O + H₂', 'KOH + O₂', 'KCl + H₂')),
    ('gh002', 'Какие продукты образуются?\nCaH₂ + 2H₂O → ?', 'Ca(OH)₂ + 2H₂', ('CaO + 2H₂', 'Ca(OH)₂ + O₂', 'CaH₂O₂ + H₂')),
    ('gh003', 'Какие продукты образуются?\nNaH + HCl → ?\nУсловие: кислая среда', 'NaCl + H₂', ('NaOH + H₂', 'NaCl + H₂O', 'Na₂O + HCl')),
    ('gh004', 'Какие продукты образуются?\nNa₂O₂ + 2H₂O → ?\nУсловие: без нагревания', '2NaOH + H₂O₂', ('2NaOH + O₂', 'Na₂O + 2H₂O', 'NaOH + H₂')),
    ('gh005', 'Какие продукты образуются?\nBaO₂ + 2H₂O → ?\nУсловие: без нагревания', 'Ba(OH)₂ + H₂O₂', ('BaO + O₂', 'Ba(OH)₂ + H₂', 'BaCO₃ + H₂O')),
    ('gh006', 'Какие продукты образуются?\n2Na₂O₂ + 2H₂O → ?\nУсловие: нагревание', '4NaOH + O₂', ('4NaOH + 2H₂', '2NaOH + H₂O₂', '2Na₂O + O₂')),
    ('gh007', 'Какие продукты образуются?\nNa₂O₂ + 2HCl → ?\nУсловие: кислая среда, без нагревания', '2NaCl + H₂O₂', ('2NaCl + H₂', 'NaOH + Cl₂', 'NaCl + H₂O')),
    ('gh008', 'Какие продукты образуются?\nNa₃N + 3H₂O → ?', '3NaOH + NH₃', ('NaNO₃ + H₂', '3NaOH + N₂', 'Na₃NH₂ + O₂')),
    ('gh009', 'Какие продукты образуются?\nCa₃N₂ + 6H₂O → ?', '3Ca(OH)₂ + 2NH₃', ('3CaO + 2NH₃', '3Ca(OH)₂ + N₂', 'Ca(NO₃)₂ + H₂')),
    ('gh010', 'Какие продукты образуются?\nMg₃N₂ + 6H₂O → ?', '3Mg(OH)₂ + 2NH₃', ('3MgO + N₂', '3Mg(OH)₂ + 2H₂', '3Mg(NO₃)₂ + NH₃')),
    ('gh011', 'Какие продукты образуются?\nAlN + 4HNO₃ → ?\nУсловие: кислая среда', 'Al(NO₃)₃ + NH₄NO₃', ('Al(OH)₃ + HNO₃', 'Al(NO₃)₃ + NH₃', 'Al₂O₃ + NH₄NO₃')),
    ('gh012', 'Какие продукты образуются?\nAlN + NaOH + 3H₂O → ?\nУсловие: избыток щёлочи', 'Na[Al(OH)₄] + NH₃', ('Al(OH)₃ + NaNO₃', 'NaAlO₂ + N₂', 'Na[Al(OH)₄] + N₂')),
    ('gh013', 'Какие продукты образуются?\nLi₃P + 3H₂O → ?', '3LiOH + PH₃', ('3LiOH + NH₃', 'Li₃PO₄ + H₂', '3LiH + H₃PO₄')),
    ('gh014', 'Какие продукты образуются?\nZn₃P₂ + 6H₂O → ?', '3Zn(OH)₂ + 2PH₃', ('3ZnO + 2H₃PO₄', '3Zn(OH)₂ + 2NH₃', 'Zn₃(PO₄)₂ + H₂')),
    ('gh015', 'Какие продукты образуются?\n2AlP + 3H₂SO₄ → ?\nУсловие: кислая среда', 'Al₂(SO₄)₃ + 2PH₃', ('2Al(OH)₃ + SO₂', 'Al₂(SO₄)₃ + 2NH₃', 'AlPO₄ + H₂S')),
    ('gh016', 'Какие продукты образуются?\nAlP + NaOH + 3H₂O → ?\nУсловие: избыток щёлочи', 'Na[Al(OH)₄] + PH₃', ('Na₃PO₄ + AlH₃', 'Al(OH)₃ + NH₃', 'NaAlO₂ + H₂S')),
    ('gh017', 'Какие продукты образуются?\nCaC₂ + 2H₂O → ?', 'Ca(OH)₂ + C₂H₂', ('Ca(OH)₂ + CH₄', 'CaCO₃ + 2H₂', 'CaO + CO₂')),
    ('gh018', 'Какие продукты образуются?\nAl₄C₃ + 12H₂O → ?', '4Al(OH)₃ + 3CH₄', ('4Al(OH)₃ + 3C₂H₂', '2Al₂O₃ + 3CO₂', '4Al(OH)₃ + 3CO')),
    ('gh019', 'Какие продукты образуются?\nBe₂C + 4H₂O → ?', '2Be(OH)₂ + CH₄', ('BeCO₃ + H₂', '2Be(OH)₂ + C₂H₂', '2BeO + CO₂')),
    ('gh020', 'Какие продукты образуются?\nNa₂C₂ + 2HBr → ?\nУсловие: кислая среда', '2NaBr + C₂H₂', ('2NaBr + CH₄', '2NaOH + Br₂', 'Na₂CO₃ + H₂')),
    ('gh021', 'Какие продукты образуются?\nAl₄C₃ + 4KOH + 12H₂O → ?\nУсловие: избыток щёлочи', '4K[Al(OH)₄] + 3CH₄', ('4KAlO₂ + 3C₂H₂', '4Al(OH)₃ + 3CO₂', '4K[Al(OH)₄] + 3C₂H₂')),
    ('gh022', 'Какие продукты образуются?\nNa₄Si + 4H₂O → ?', '4NaOH + SiH₄', ('4NaOH + SiO₂', 'Na₂SiO₃ + H₂', '4NaH + SiO₂')),
    ('gh023', 'Какие продукты образуются?\nMg₂Si + 4H₂O → ?', '2Mg(OH)₂ + SiH₄', ('2MgO + SiO₂', '2Mg(OH)₂ + H₂', 'MgSiO₃ + H₂')),
    ('gh024', 'Какие продукты образуются?\nMg₂Si + 2H₂SO₄ → ?\nУсловие: кислая среда', '2MgSO₄ + SiH₄', ('2MgSO₄ + SiO₂', 'MgSiO₃ + SO₂', '2MgSO₄ + H₂')),
    ('gh025', 'Какие продукты образуются?\nAl₂S₃ + 6H₂O → ?', '2Al(OH)₃ + 3H₂S', ('2Al(OH)₃ + 3SO₂', 'Al₂(SO₄)₃ + H₂', '2Al(OH)₃ + 3S')),
    ('gh026', 'Какие продукты образуются?\nCr₂S₃ + 6H₂O → ?', '2Cr(OH)₃ + 3H₂S', ('2Cr(OH)₃ + 3SO₂', 'Cr₂(SO₄)₃ + H₂', '2Cr(OH)₂ + 3H₂S')),
    ('gh027', 'Какие продукты образуются?\nAl₂S₃ + 8KOH → ?\nУсловие: избыток щёлочи', '2K[Al(OH)₄] + 3K₂S', ('2Al(OH)₃ + 3H₂S', 'Al₂(SO₄)₃ + K₂S', '2KAlO₂ + 3SO₂')),
    ('gh028', 'Какие продукты образуются?\nPCl₅ + 4H₂O → ?', 'H₃PO₄ + 5HCl', ('H₃PO₃ + 5HCl', 'PH₃ + Cl₂', 'P₂O₅ + H₂')),
    ('gh029', 'Какие продукты образуются?\nPCl₃ + 3H₂O → ?', 'H₃PO₃ + 3HCl', ('H₃PO₄ + 3HCl', 'PH₃ + 3HCl', 'P₂O₃ + H₂')),
    ('gh030', 'Какие продукты образуются?\nSiCl₄ + 3H₂O → ?', 'H₂SiO₃ + 4HCl', ('H₂SiO₄ + 4HCl', 'SiO₂ + 4H₂', 'SiH₄ + Cl₂')),
    ('gh031', 'Какие продукты образуются?\nCOCl₂ + H₂O → ?', 'CO₂ + 2HCl', ('CO + Cl₂', 'CH₄ + O₂', 'H₂CO₃ + Cl₂')),
    ('gh032', 'Какие продукты образуются?\nPCl₅ + 8KOH → ?\nУсловие: избыток щёлочи', '5KCl + K₃PO₄ + 4H₂O', ('5KCl + K₂HPO₄ + 3H₂O', '5KCl + KH₂PO₄ + 2H₂O', '3KCl + K₃PO₃ + H₂O')),
    ('gh033', 'Какие продукты образуются?\nPCl₅ + 7KOH → ?\nУсловие: недостаток щёлочи', '5KCl + K₂HPO₄ + 3H₂O', ('5KCl + K₃PO₄ + 4H₂O', '5KCl + KH₂PO₄ + 2H₂O', '5KCl + K₂SO₄ + H₂O')),
    ('gh034', 'Какие продукты образуются?\nPCl₅ + 6KOH → ?\nУсловие: большой недостаток щёлочи', '5KCl + KH₂PO₄ + 2H₂O', ('5KCl + K₂HPO₄ + 3H₂O', '5KCl + K₃PO₄ + 4H₂O', '3KCl + K₃PO₃ + H₂O')),
    ('gh035', 'Какие продукты образуются?\nSiCl₄ + 6KOH → ?\nУсловие: избыток щёлочи', '4KCl + K₂SiO₃ + 3H₂O', ('4KCl + K₂SO₄ + 3H₂O', '4KCl + K₂SiO₄ + 2H₂O', '4KCl + SiH₄')),
    ('gh036', 'Какие продукты образуются?\n2AlCl₃ + 3K₂CO₃ + 3H₂O → ?\nВодные растворы.', '2Al(OH)₃ + 3CO₂ + 6KCl', ('Al₂(CO₃)₃ + 6KCl', '2Al(OH)₃ + 3H₂S + 6KCl', '2Al(OH)₃ + 3SO₂ + 6KCl')),
    ('gh037', 'Какие продукты образуются?\n2Al(NO₃)₃ + 3Na₂SO₃ + 3H₂O → ?\nВодные растворы.', '2Al(OH)₃ + 3SO₂ + 6NaNO₃', ('Al₂(SO₃)₃ + 6NaNO₃', '2Al(OH)₃ + 3CO₂ + 6NaNO₃', '2Al(OH)₃ + 3H₂S + 6NaNO₃')),
    ('gh038', 'Какие продукты образуются?\nAl₂(SO₄)₃ + 3Na₂S + 6H₂O → ?\nВодные растворы.', '2Al(OH)₃ + 3H₂S + 3Na₂SO₄', ('Al₂S₃ + 3Na₂SO₄', '2Al(OH)₃ + 3SO₂ + 3Na₂SO₄', '2Al(OH)₃ + 3H₂ + 3Na₂SO₄')),
    ('gh039', 'Какие продукты образуются?\n2CrBr₃ + 3Na₂CO₃ + 3H₂O → ?\nВодные растворы.', '2Cr(OH)₃ + 3CO₂ + 6NaBr', ('Cr₂(CO₃)₃ + 6NaBr', '2Cr(OH)₃ + 3H₂S + 6NaBr', '2CrO₃ + 3CO₂ + 6NaBr')),
    ('gh040', 'Какие продукты образуются?\n2Cr(NO₃)₃ + 3Na₂SO₃ + 3H₂O → ?\nВодные растворы.', '2Cr(OH)₃ + 3SO₂ + 6NaNO₃', ('Cr₂(SO₃)₃ + 6NaNO₃', '2Cr(OH)₃ + 3CO₂ + 6NaNO₃', '2Cr(OH)₃ + 3H₂S + 6NaNO₃')),
    ('gh041', 'Какие продукты образуются?\n2FeCl₃ + 3K₂CO₃ + 3H₂O → ?\nВодные растворы.', '2Fe(OH)₃ + 3CO₂ + 6KCl', ('Fe₂(CO₃)₃ + 6KCl', '2Fe(OH)₃ + 3SO₂ + 6KCl', '2FeO + 3H₂S + 6KCl')),
    ('gh042', 'Какие продукты образуются?\nAlCl₃ + 3KHCO₃ → ?\nУсловие: гидрокарбонат в растворе', 'Al(OH)₃ + 3CO₂ + 3KCl', ('Al₂(CO₃)₃ + KCl', 'Al(OH)₃ + 3SO₂ + 3KCl', 'Al(OH)₃ + 3H₂S + 3KCl')),
    ('gh043', 'Какие продукты образуются?\nCr(NO₃)₃ + 3NaHSO₃ → ?\nУсловие: гидросульфит (HSO3−) в растворе', 'Cr(OH)₃ + 3SO₂ + 3NaNO₃', ('Cr(OH)₃ + 3CO₂ + 3NaNO₃', 'Cr₂(SO₃)₃ + NaNO₃', 'Cr(OH)₃ + 3H₂S + 3NaNO₃')),
    ('gh044', 'Какие продукты образуются?\nFeCl₃ + 3KHCO₃ → ?\nУсловие: гидрокарбонат в растворе', 'Fe(OH)₃ + 3CO₂ + 3KCl', ('FeCO₃ + 3KCl', 'Fe(OH)₃ + 3SO₂ + 3KCl', 'Fe(OH)₃ + 3H₂S + 3KCl')),
    ('gh045', 'Какие продукты образуются?\nNaAlO₂ + 2H₂O → ?', 'Na[Al(OH)₄]', ('Al(OH)₃ + NaOH', 'Na₂AlO₃ + H₂', 'Al₂O₃ + NaOH')),
    ('gh046', 'Какие продукты образуются?\nK₂ZnO₂ + 2H₂O → ?', 'K₂[Zn(OH)₄]', ('Zn(OH)₂ + 2KOH', 'KZnO₃ + H₂', 'K₂ZnO₃ + H₂')),
    ('gh047', 'Какие продукты образуются?\nNaFeO₂ + 2H₂O → ?', 'Fe(OH)₃ + NaOH', ('Na[Fe(OH)₄]', 'Fe(OH)₂ + NaOH', 'NaFeO₃ + H₂')),
    ('gh048', 'Какие продукты образуются?\n2FeCl₃ + 3K₂S → ?\nУсловие: избыток сульфида', '2FeS + S + 6KCl', ('2Fe(OH)₃ + 3H₂S + 6KCl', '2FeCl₂ + 3SO₂ + 6KCl', 'Fe₂S₃ + 6KCl')),
    ('gh049', 'Какие продукты образуются?\nFe₂(SO₄)₃ + K₂SO₃ + H₂O → ?', 'K₂SO₄ + 2FeSO₄ + H₂SO₄', ('2Fe(OH)₃ + SO₂ + K₂SO₄', 'Fe₂(SO₃)₃ + K₂SO₄', 'K₂S + 2FeSO₄ + H₂O')),
    ('gh050', 'Какие продукты образуются?\n2CuSO₄ + 4KI → ?', '2CuI + I₂ + 2K₂SO₄', ('2CuI₂ + 2K₂SO₄', '2Cu(OH)₂ + I₂ + 2K₂SO₄', 'Cu₂O + 4K₂SO₄ + I₂')),
 )

if len(IRREVERSIBLE_HYDROLYSIS_BANK) != 50:
    raise RuntimeError("Банк гидролиза должен содержать 50 вопросов")
for question_id, prompt, correct, distractors in IRREVERSIBLE_HYDROLYSIS_BANK:
    if not question_id or not prompt or not correct or len(distractors) != 3:
        raise RuntimeError(f"Некорректное задание: {question_id}")
    if len({correct, *distractors}) != 4:
        raise RuntimeError(f"Повторяющиеся варианты: {question_id}")