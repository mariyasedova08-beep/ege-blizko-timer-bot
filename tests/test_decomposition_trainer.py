"""Offline validation of all 50 chemical equations and bot callback safety."""
import asyncio
from collections import Counter
import importlib.util
from pathlib import Path
import random
import re
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BANK_FILE = ROOT / "decomposition_trainer_bank.py"
TRAINER_FILE = ROOT / "decomposition_trainer.py"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def elements(formula):
    """Tiny independent balance checker for formulas with (), [] and coefficients."""
    expr = formula.replace("[", "(").replace("]", ")")
    tokens = re.findall(r"[A-Z][a-z]?|\d+|[()]|.", expr)
    if any(not (re.fullmatch(r"[A-Z][a-z]?|\d+|[()]", t)) for t in tokens):
        raise ValueError("Unparsed formula: " + formula)
    index = 0

    def group():
        nonlocal index
        atoms = Counter()
        while index < len(tokens):
            tok = tokens[index]
            if tok == ")":
                break
            if tok == "(":
                index += 1
                nested = group()
                if index >= len(tokens) or tokens[index] != ")":
                    raise ValueError("Unbalanced parentheses")
                index += 1
                mult = 1
                if index < len(tokens) and tokens[index].isdigit():
                    mult = int(tokens[index])
                    index += 1
                for element, amount in nested.items():
                    atoms[element] += amount * mult
                continue
            if not re.fullmatch(r"[A-Z][a-z]?", tok):
                raise ValueError("Unexpected token " + tok)
            index += 1
            amount = 1
            if index < len(tokens) and tokens[index].isdigit():
                amount = int(tokens[index])
                index += 1
            atoms[tok] += amount
        return atoms

    multiplier = 1
    if tokens and tokens[0].isdigit():
        multiplier = int(tokens[0])
        index += 1
    found = group()
    if index != len(tokens):
        raise ValueError("Unexpected trailing tokens")
    return Counter({k: n * multiplier for k, n in found.items()})


def equation_side(expression):
    combined = Counter()
    for formula in expression.split(" + "):
        combined.update(elements(formula.strip()))
    return combined


class TestQuestionBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = load_file("decomposition_trainer_bank", BANK_FILE).DECOMPOSITION_BANK

    def test_exact_counts_and_distinct_answers(self):
        self.assertEqual(len(self.bank), 50)
        self.assertEqual(len({q["id"] for q in self.bank}), 50)
        self.assertEqual(sum(q["type"] == "НЕ ОВР" for q in self.bank), 25)
        self.assertEqual(sum(q["type"] == "ОВР" for q in self.bank), 25)
        self.assertEqual(
            len({(q["reactants"], q["condition"]) for q in self.bank}), 50
        )
        for q in self.bank:
            with self.subTest(q=q["id"]):
                self.assertEqual(len(q["distractors"]), 3)
                self.assertEqual(len({q["products"], *q["distractors"]}), 4)
                self.assertTrue(q["explanation"])
                self.assertTrue(q["condition"])

    def test_every_decomposition_is_atom_balanced(self):
        for q in self.bank:
            with self.subTest(q=q["id"]):
                self.assertEqual(equation_side(q["reactants"]),
                                 equation_side(q["products"]))

    def test_condition_dependent_kclo3_and_ammonium(self):
        bank = {q["reactants"]: q for q in self.bank}
        self.assertIn("MnO2", bank["2KClO3"]["condition"])
        self.assertIn("без катализатора", bank["4KClO3"]["condition"])
        self.assertEqual(bank["NH4NO2"]["products"], "N2 + 2H2O")
        self.assertEqual(bank["NH4NO3"]["products"], "N2O + 2H2O")
        self.assertEqual(bank["(CuOH)2CO3"]["products"], "2CuO + CO2 + H2O")


class DummyButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class DummyMarkup:
    def __init__(self, rows, **kwargs):
        self.inline_keyboard = rows
        self.keyboard = rows


class DummyQuery:
    def __init__(self, data=""):
        self.data = data
        self.messages = []
    async def answer(self, *args, **kwargs):
        return None
    async def edit_message_text(self, text, reply_markup=None):
        self.messages.append((text, reply_markup))


class DummyContext:
    def __init__(self):
        self.user_data = {}
        self.args = []


class TestBotIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "synthetic.sqlite")

        async def previous_router(*args, **kwargs):
            raise AssertionError("Unexpected delegation to existing app")

        bot = types.SimpleNamespace(COREAPP_DB_PATH=self.db, TIMEZONE=timezone.utc)
        def catalog_table():
            with sqlite3.connect(self.db) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS weekly_trainer_catalog
                       (code TEXT PRIMARY KEY,title TEXT,start_param TEXT,
                        sort_order INTEGER, active INTEGER)"""
                )
                conn.commit()
        live7 = types.SimpleNamespace(
            STUDENT_KEYBOARD=DummyMarkup([["💳 Оплата"]]),
            trivial_callback=previous_router,
            start_router=previous_router,
            student_text_router=previous_router,
        )
        live41 = types.SimpleNamespace(ensure_weekly_report_tables=catalog_table)
        live79 = types.SimpleNamespace(live41=live41, live7=live7)
        live85 = types.ModuleType("run_bot_live85")
        live85.live79 = live79
        live85.bot = bot

        telegram = types.ModuleType("telegram")
        telegram.InlineKeyboardButton = DummyButton
        telegram.InlineKeyboardMarkup = DummyMarkup
        telegram.ReplyKeyboardMarkup = DummyMarkup
        self.patcher = patch.dict(sys.modules, {
            "telegram": telegram, "run_bot_live85": live85,
        })
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mod = load_file("decomposition_trainer_test_instance", TRAINER_FILE)
        self.live7 = live7
        self.user = types.SimpleNamespace(id=101, username="fake", full_name="FAKE")
        self.context = DummyContext()
        self.query = DummyQuery()
        self.update = types.SimpleNamespace(
            callback_query=self.query,
            effective_user=self.user,
            effective_chat=types.SimpleNamespace(type="private"),
            effective_message=types.SimpleNamespace(reply_text=previous_router),
            message=None,
        )

    def callback(self, data):
        self.query.data = data
        return asyncio.run(self.mod.callback(self.update, self.context))

    def test_five_modes_and_error_pool(self):
        mod = self.mod
        self.assertEqual(len(mod._select_ids("10", 101)), 10)
        self.assertEqual(len(mod._select_ids("non", 101)), 25)
        self.assertEqual(len(mod._select_ids("redox", 101)), 25)
        self.assertEqual(len(mod._select_ids("50", 101)), 50)
        self.assertEqual(mod._select_ids("errors", 101), [])
        self.assertEqual(
            {mod.BY_ID[q]["type"] for q in mod._select_ids("non", 101)},
            {"НЕ ОВР"},
        )
        self.assertEqual(
            {mod.BY_ID[q]["type"] for q in mod._select_ids("redox", 101)},
            {"ОВР"},
        )

    def test_install_is_idempotent_and_catalog_unassigned(self):
        self.mod.install()
        self.mod.install()
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(
                "SELECT code,active FROM weekly_trainer_catalog WHERE code='decomposition'"
            ).fetchone()
        self.assertEqual(row, ("decomposition", 0))
        self.assertEqual(
            sum("🧪 Реакции разложения" in row for row in self.live7.STUDENT_KEYBOARD.keyboard), 1
        )

    def test_wrong_answer_records_once_and_explains(self):
        self.mod.ensure_tables()
        self.callback("dec:start:10")
        state = self.context.user_data[self.mod.KEY]
        first = self.mod.BY_ID[state["ids"][0]]
        wrong = next(i for i, option in enumerate(state["choices"])
                     if option != first["products"])
        code = f"dec:a:{state['token']}:{state['nonce']}:{wrong}"
        self.callback(code)
        self.callback(code)  # duplicate Telegram callback
        with sqlite3.connect(self.db) as conn:
            n = conn.execute("SELECT COUNT(*) FROM decomposition_attempts").fetchone()[0]
        self.assertEqual(n, 1)
        self.assertEqual(self.context.user_data[self.mod.KEY]["index"], 1)
        self.assertIn(first["reactants"] + " → " + first["products"],
                      self.query.messages[-1][0])
        self.assertIn(first["id"], self.mod._errors(101))
        self.assertEqual(len(self.query.messages), 2)  # question + one response

    def test_next_nonce_rejects_replay(self):
        self.mod.ensure_tables()
        self.callback("dec:start:10")
        state = self.context.user_data[self.mod.KEY]
        q = self.mod.BY_ID[state["ids"][0]]
        correct = state["choices"].index(q["products"])
        self.callback(f"dec:a:{state['token']}:{state['nonce']}:{correct}")
        state = self.context.user_data[self.mod.KEY]
        next_code = f"dec:next:{state['token']}:{state['next_nonce']}"
        self.callback(next_code)
        self.callback(next_code)
        state = self.context.user_data[self.mod.KEY]
        self.assertEqual(state["index"], 1)
        self.assertEqual(state["phase"], "question")


if __name__ == "__main__":
    unittest.main()
