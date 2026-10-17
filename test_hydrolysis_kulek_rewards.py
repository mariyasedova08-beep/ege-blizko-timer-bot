"""Isolated real Kulyochki calculations using temporary SQLite, no bot/network."""
import ast
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent


def _logic(tmp_path):
    source = (ROOT / "kulek_rewards.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    tables = next(
        ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and
        any(isinstance(target, ast.Name) and target.id == "TRAINER_TABLES"
            for target in node.targets)
    )
    # Install-side integration explicitly maps the new trainer to its table.
    production = (ROOT / "run_bot_production.py").read_text(encoding="utf-8")
    assert 'kulek_rewards.TRAINER_TABLES["hydrolysis"] = "hydrolysis_sessions"' in production
    assert "hydrolysis" not in tables
    tables["hydrolysis"] = "hydrolysis_sessions"

    db_path = str(tmp_path / "testing.sqlite3")
    students = [(11, "Student", None, None, None, 93410)]
    names = {"_trainer_goals", "_trainer_half_month_counts"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == 2
    env = {
        "sqlite3": sqlite3, "re": re, "datetime": datetime,
        "bot": SimpleNamespace(COREAPP_DB_PATH=db_path, TIMEZONE=ZoneInfo("UTC")),
        "TRAINER_TABLES": tables,
        "ensure_tables": lambda: None,
        "_student_rows": lambda: students,
        "_month_key": lambda key=None: key,
    }
    for fun in functions:
        exec(compile(ast.Module(body=[fun], type_ignores=[]), source, "exec"), env)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE weekly_trainer_catalog(
                code TEXT, title TEXT, active INTEGER, sort_order INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO weekly_trainer_catalog VALUES (?,?,?,?)",
            ("hydrolysis", "🧪 Необратимый гидролиз", 1, 60)
        )
        conn.execute("""
            CREATE TABLE hydrolysis_sessions(
                telegram_user_id INTEGER,
                finished_at TEXT,
                total INTEGER,
                correct INTEGER
            )
        """)
        conn.commit()
    return env, students, db_path


def test_only_completed_sessions_award_single_kulyochek(tmp_path):
    env, students, db = _logic(tmp_path)
    calc = env["_trainer_goals"]
    assert calc("2026-10", students) == []  # Not a goal until first real completion.

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
            (93410, None, 10, 10)
        )
        conn.execute(
            "INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
            (93410, "2026-10-10T13:00:00+00:00", 10, 7)
        )
        conn.execute(
            "INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
            (93410, "2026-10-14T13:00:00+00:00", 20, 20)
        )
        conn.commit()

    item = calc("2026-10", students)[0]["students"][11]
    assert item == {"sessions": 2, "earned": False, "remaining": 1}

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
            (93410, "2026-10-18T13:00:00+00:00", 50, 30)
        )
        conn.commit()

    rows = calc("2026-10", students)
    assert len(rows) == 1
    item = rows[0]["students"][11]
    assert item == {"sessions": 3, "earned": True, "remaining": 0}
    # 1 reward per trainer, not 1 per correct answer or attempt.
    assert sum(int(x["students"][11]["earned"]) for x in rows) == 1
    assert calc("2026-09", students) == []  # Do not modify past months.


def test_first_vs_second_half_counts_hydrolysis(tmp_path):
    env, students, db = _logic(tmp_path)
    with sqlite3.connect(db) as conn:
        for date in (
            "2026-10-04T14:00:00+00:00",
            "2026-10-14T17:00:00+00:00",
            "2026-10-19T14:00:00+00:00",
        ):
            conn.execute("INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
                         (93410, date, 10, 8))
        conn.execute("INSERT INTO hydrolysis_sessions VALUES (?,?,?,?)",
                     (93410, None, 10, 0))
        conn.commit()
    assert env["_trainer_half_month_counts"](11, "2026-10") == (2, 1)
