"""50 вопросов: разложение НЕ ОВР / ОВР, для Telegram-бота ЕГЭ БЛИЗКО.

Данные хранятся отдельно в UTF-8 TSV, без HTML / WebApp.
Первые 25 вопросов — НЕ ОВР; следующие 25 — ОВР.
"""
from pathlib import Path

DATA_PATH = Path(__file__).with_name("decomposition_trainer_questions.tsv")
DECOMPOSITION_BANK = []
DECOMPOSITION_GROUPS = {}
DECOMPOSITION_EXPLANATIONS = {}

for number, line in enumerate(DATA_PATH.read_text(encoding="utf-8").splitlines(), start=1):
    parts = line.split("\t")
    if len(parts) != 7:
        raise RuntimeError(f"Invalid decomposition data row {number}: {len(parts)} fields")
    prompt, correct, wrong1, wrong2, wrong3, equation, note = parts
    qid = f"decomp{number:03d}"
    group = "non_ovr" if number <= 25 else "ovr"
    if not all((prompt, correct, wrong1, wrong2, wrong3, equation)):
        raise RuntimeError(f"Empty required decomposition field in {qid}")
    if len({correct, wrong1, wrong2, wrong3}) != 4:
        raise RuntimeError(f"Duplicate answer choices in {qid}")
    DECOMPOSITION_BANK.append((qid, prompt, correct, (wrong1, wrong2, wrong3)))
    DECOMPOSITION_GROUPS[qid] = group
    label = "НЕ ОВР: степени окисления не изменяются." if group == "non_ovr" else "ОВР: степени окисления изменяются."
    DECOMPOSITION_EXPLANATIONS[qid] = "\n".join(filter(None, (equation, label, note)))

DECOMPOSITION_BANK = tuple(DECOMPOSITION_BANK)
assert len(DECOMPOSITION_BANK) == 50
assert sum(group == "non_ovr" for group in DECOMPOSITION_GROUPS.values()) == 25
assert sum(group == "ovr" for group in DECOMPOSITION_GROUPS.values()) == 25
