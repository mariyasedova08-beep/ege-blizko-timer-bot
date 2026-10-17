"""Offline bank-format checks for the irreversible hydrolysis trainer."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hydrolysis_bank", ROOT / "irreversible_hydrolysis_trainer_bank.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BANK = mod.IRREVERSIBLE_HYDROLYSIS_BANK


def test_exactly_50_unique_questions():
    assert len(BANK) == 50
    assert len({item[0] for item in BANK}) == 50
    assert len({item[1] for item in BANK}) == 50


def test_each_question_has_four_distinct_answers():
    for code, prompt, correct, wrong in BANK:
        assert code.startswith("gh")
        assert "→ ?" in prompt
        assert correct
        assert len(wrong) == 3
        assert len({correct, *wrong}) == 4


def test_no_embedded_bot_secrets_or_network_calls():
    text = (ROOT / "irreversible_hydrolysis_trainer_bank.py").read_text(encoding="utf-8")
    assert "BOT_TOKEN" not in text
    assert "telegram.Bot(" not in text


def test_menu_callback_contract():
    text = (ROOT / "irreversible_hydrolysis_trainer.py").read_text(encoding="utf-8")
    for fragment in (
        "triv:hydrolysis:start:10",
        "triv:hydrolysis:start:20",
        "triv:hydrolysis:start:50",
        "triv:hydrolysis:start:errors",
        "triv:hydrolysis:stats",
        'if str(session["index"]) != question_index:',
    ):
        assert fragment in text


def test_unrelated_salt_deeplinks_not_hijacked():
    text = (ROOT / "irreversible_hydrolysis_trainer.py").read_text(encoding="utf-8")
    assert '"middlesaltprops"' not in text
    assert '"свойствасолей"' not in text
    assert '"irreversible_hydrolysis"' in text
