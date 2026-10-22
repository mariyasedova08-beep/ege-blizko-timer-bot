"""Build an OFFLINE, non-runnable sandbox from PUBLIC GitHub source only.

NEVER import or execute application modules. NEVER connect to Telegram, read
production secrets, copy databases, or touch Timeweb VPS. This is a first
rehearsal boundary, not a claim that GitHub matches deployed production.
"""
import argparse
import ast
from collections import deque
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys

SEEDS = ("run_bot_production", "ege_lab_webapp")
OTHER_PRODUCTS = ("teacher_product_", "prepodmin_", "sedova_pill_", "pill_tracker")
DEPENDENCIES_FROM_REQUIREMENTS = frozenset(("telegram", "openpyxl", "tzdata"))
MAX_MODULES = 250
MAX_SOURCE_BYTES = 1_000_000
MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def blocked_other_product(name):
    return name.startswith(OTHER_PRODUCTS)


def static_imports(tree):
    result, dynamic = set(), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            fn = node.func
            is_dynamic = (
                isinstance(fn, ast.Name) and fn.id == "__import__"
            ) or (
                isinstance(fn, ast.Attribute) and fn.attr == "import_module"
                and isinstance(fn.value, ast.Name) and fn.value.id == "importlib"
            )
            if is_dynamic:
                if (node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    name = node.args[0].value.strip(".").split(".")[0]
                    result.add(name)
                else:
                    dynamic += 1
    return sorted(name for name in result if MODULE_NAME.fullmatch(name)), dynamic


def safe_sources(root):
    # Only top-level Python source: no .env, sqlite, private JSON, user files,
    # symlinked code, nested repositories or static assets.
    names, refused = {}, set()
    for path in root.iterdir():
        if path.suffix != ".py" or not MODULE_NAME.fullmatch(path.stem):
            continue
        if blocked_other_product(path.stem):
            continue
        if path.is_symlink():
            refused.add(path.stem)
        elif path.is_file():
            names[path.stem] = path
    return names, refused


def assert_destination_safe(root, output):
    if output.exists():
        raise ValueError("SANDBOX_OUTPUT_MUST_NOT_EXIST")
    if output == root or root in output.parents or output in root.parents:
        raise ValueError("SANDBOX_MUST_BE_OUTSIDE_SOURCE_TREE")
    if output.is_symlink() or root.is_symlink():
        raise ValueError("SYMLINK_DIRECTORY_REFUSED")


def make_fixture_db(output):
    # Entirely synthetic test fixture: no production schema or student data.
    db = output / "fixtures" / "synthetic-only.sqlite"
    db.parent.mkdir(mode=0o700)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE synthetic_students (id INTEGER PRIMARY KEY, label TEXT NOT NULL)")
        con.execute("INSERT INTO synthetic_students VALUES (?, ?)", (1001, "FAKE_STUDENT_FOR_TESTS"))
        con.commit()


def build(root, output):
    root = root.resolve(strict=True)
    output = output.absolute()
    assert_destination_safe(root, output)
    sources, refused = safe_sources(root)
    output.mkdir(mode=0o700, parents=True)
    copied = []
    unresolved = set()
    rejected = set(refused)
    excluded = set()
    third_party_or_unknown = set()
    dynamic_calls = 0
    queue, seen = deque(SEEDS), set()
    (output / "source").mkdir(mode=0o700)

    while queue:
        name = queue.popleft()
        if name in seen:
            continue
        seen.add(name)
        if len(seen) > MAX_MODULES:
            raise ValueError("MAX_MODULES_EXCEEDED")
        if blocked_other_product(name):
            excluded.add(name)
            continue
        path = sources.get(name)
        if path is None:
            unresolved.add(name)
            continue
        if path.stat().st_size > MAX_SOURCE_BYTES or path.is_symlink():
            rejected.add(name)
            continue
        data = path.read_bytes()
        if len(data) > MAX_SOURCE_BYTES:
            rejected.add(name)
            continue
        try:
            tree = ast.parse(data.decode("utf-8-sig"), filename=name + ".py")
        except (SyntaxError, UnicodeError):
            rejected.add(name)
            continue

        imports, calls = static_imports(tree)
        dynamic_calls += calls
        for dep in imports:
            if blocked_other_product(dep):
                excluded.add(dep)
            elif dep in sources or dep in refused:
                queue.append(dep)
            elif dep not in sys.stdlib_module_names and dep not in DEPENDENCIES_FROM_REQUIREMENTS:
                third_party_or_unknown.add(dep)
        # Public GitHub source is copied into disposable isolated folder.
        (output / "source" / (name + ".py")).write_bytes(data)
        copied.append(name)

    make_fixture_db(output)
    report = {
        "status": "PREPARATION_ONLY_NOT_READY_TO_RUN_BOT",
        "source": "github_checkout_only_not_vps",
        "copied_python_modules": len(copied),
        "entrypoints": list(SEEDS),
        "missing_entrypoint_or_traversal_modules": sorted(unresolved),
        "excluded_separate_product_imports": sorted(excluded),
        "unverified_external_imports": sorted(third_party_or_unknown),
        "refused_or_unreadable": sorted(rejected),
        "dynamic_import_calls_not_resolved": dynamic_calls,
        "fixture": "fixtures/synthetic-only.sqlite",
        "real_student_data_used": False,
        "telegram_bot_started": False,
        "server_connected": False,
        "next_gate": "restore_missing_vps_only_dependencies_in_private_staging_and_test_functionality",
    }
    (output / "preflight.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("OFFLINE_SANDBOX_CREATED")
    print("PYTHON_MODULES_COPIED=" + str(len(copied)))
    print("UNVERIFIED_IMPORTS=" + str(len(third_party_or_unknown)))
    print("EXCLUDED_OTHER_PRODUCTS=" + str(len(excluded)))
    print("NO_VPS_NO_TELEGRAM_NO_REAL_STUDENTS")
    print("NOT_A_DEPLOYABLE_BOT")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    root = Path(options.root).absolute()
    output = Path(options.output).absolute()
    try:
        build(root, output)
    except (OSError, ValueError) as exc:
        # Do not print paths or source text in CI error messages.
        print("SANDBOX_BUILD_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
