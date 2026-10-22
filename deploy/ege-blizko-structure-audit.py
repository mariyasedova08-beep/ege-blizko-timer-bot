"""Read-only structural comparison without publishing VPS source code.

Only fixed allowlisted Python files are opened, never imported or executed.
VPS output contains no raw source, comments, literals, function names, DB data,
credentials or paths outside this allowlist.
"""
import argparse
import ast
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path("/opt/bots/ege-blizko")
FILES = (
    "run_bot_production.py",
    "run_bot_live7.py",
    "public_channel_trainers.py",
    "ege_lab_webapp.py",
    "oge9_trainer_notifications.py",
    "oge_classification_trainer.py",
    "ege11_lesson_transfer.py",
)
EMPTY = "-"
HEX64 = re.compile(r"^[a-f0-9]{64}$")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class WithoutLiterals(ast.NodeTransformer):
    """Reduce accidental disclosure: fingerprints ignore literal values."""

    def visit_Constant(self, node):
        return ast.copy_location(
            ast.Constant(value="<constant:" + type(node.value).__name__ + ">"), node
        )


def fingerprint(node):
    # Values of string/number literals never enter this fingerprint.
    normalized = WithoutLiterals().visit(ast.fix_missing_locations(node))
    return digest(ast.dump(normalized, annotate_fields=True, include_attributes=False))


def analyse(directory, include_public_names=False):
    records = []
    for name in FILES:
        path = directory / name
        if path.is_symlink():
            raise ValueError("SYMLINK_SOURCE_REJECTED: " + name)
        if not path.is_file():
            records.append(("FILE", name, "MISSING", "0", "0"))
            continue
        try:
            raw = path.read_bytes()
            tree = ast.parse(raw.decode("utf-8-sig"), filename=name)
        except (OSError, UnicodeError, SyntaxError) as exc:
            # Exception details may contain source snippets. Never print them.
            raise ValueError("SOURCE_NOT_PARSEABLE: " + name) from None
        records.append(("FILE", name, "EXISTS", str(len(raw)), str(len(raw.splitlines()))))
        declarations = []
        top_level = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                declarations.append((node.name, node))
                if isinstance(node, ast.ClassDef):
                    for inner in node.body:
                        if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            declarations.append((node.name + "." + inner.name, inner))
            else:
                top_level.append(node)
        # At module scope, capture changes in imports and initialization structure.
        module_shape = ast.Module(body=top_level, type_ignores=[])
        records.append(("MODULE", name, fingerprint(module_shape), str(len(declarations)), EMPTY))
        for qualified, node in declarations:
            public_name = qualified if include_public_names else EMPTY
            if include_public_names and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", qualified):
                raise ValueError("UNSAFE_LOCAL_SYMBOL_NAME")
            records.append(("SYM", name, digest(qualified), fingerprint(node), public_name))
    return records


def parse_report(content, remote=False):
    result = {}
    for line in content.splitlines():
        cells = line.split("\t")
        if len(cells) != 5 or cells[0] not in ("FILE", "MODULE", "SYM") or cells[1] not in FILES:
            raise ValueError("UNEXPECTED_RECORD")
        kind, name, a, b, c = cells
        entry = result.setdefault(name, {"file": None, "module": None, "symbols": {}})
        if kind == "FILE":
            if entry["file"] is not None or a not in ("EXISTS", "MISSING"):
                raise ValueError("INVALID_FILE_RECORD")
            if not b.isdigit() or not c.isdigit():
                raise ValueError("INVALID_FILE_SIZE")
            entry["file"] = a
        elif kind == "MODULE":
            if entry["module"] is not None or not HEX64.fullmatch(a) or not b.isdigit() or c != EMPTY:
                raise ValueError("INVALID_MODULE_RECORD")
            entry["module"] = a
        else:
            if not HEX64.fullmatch(a) or not HEX64.fullmatch(b) or a in entry["symbols"]:
                raise ValueError("INVALID_SYMBOL_RECORD")
            if remote and c != EMPTY:
                raise ValueError("REMOTE_NAMES_FORBIDDEN")
            if c != EMPTY and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", c):
                raise ValueError("INVALID_SYMBOL_NAME")
            entry["symbols"][a] = (b, c)
    if set(result) != set(FILES):
        raise ValueError("INCOMPLETE_REPORT")
    for entry in result.values():
        if entry["file"] is None:
            raise ValueError("FILE_RECORD_MISSING")
        if (entry["file"] == "MISSING") != (entry["module"] is None):
            raise ValueError("INVALID_FILE_MODULE_PAIR")
    return result


def compare(local, remote):
    print("# ЕГЭ БЛИЗКО — структурная сверка (только чтение)")
    print()
    print("Исходники и значения констант VPS не передаются. Сравниваются структуры функций и классов, а не полный исходный текст.")
    print("Это предварительный анализ: совпадение структуры не означает совпадение поведения.")
    print()
    has_drift = False
    for name in FILES:
        a, b = local[name], remote[name]
        if a["file"] == "MISSING" and b["file"] == "EXISTS":
            print("- **" + name + "**: только на VPS, структурных объявлений: " + str(len(b["symbols"])))
            has_drift = True
            continue
        if a["file"] == "EXISTS" and b["file"] == "MISSING":
            print("- **" + name + "**: только в GitHub")
            has_drift = True
            continue
        if a["file"] == "MISSING":
            print("- **" + name + "**: отсутствует в обоих местах")
            continue
        common = set(a["symbols"]) & set(b["symbols"])
        changed = sorted(s for s in common if a["symbols"][s][0] != b["symbols"][s][0])
        only_local = sorted(set(a["symbols"]) - set(b["symbols"]))
        only_remote = sorted(set(b["symbols"]) - set(a["symbols"]))
        top_diff = a["module"] != b["module"]
        if changed or only_local or only_remote or top_diff:
            has_drift = True
            print("- **" + name + "**: изменены объявления " + str(len(changed))
                  + ", только GitHub " + str(len(only_local))
                  + ", только VPS " + str(len(only_remote))
                  + ", структура инициализации отличается: " + ("да" if top_diff else "нет"))
            for key in changed[:25]:
                print("  - Изменена структура: " + a["symbols"][key][1])
            for key in only_local[:25]:
                print("  - Отсутствует на VPS: " + a["symbols"][key][1])
            if len(changed) > 25 or len(only_local) > 25:
                print("  - Остальные имена скрыты ради краткости")
        else:
            print("- **" + name + "**: существенных структурных отличий не обнаружено (литералы не сравнивались)")
    print()
    print("NO_SERVER_SOURCE_EXPORTED")
    print("NO_SERVER_WRITES_NO_DEPLOYMENT")
    if has_drift:
        raise SystemExit("STRUCTURAL_DRIFT_REQUIRES_MANUAL_REVIEW")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("local", "remote", "compare"))
    parser.add_argument("--local")
    parser.add_argument("--remote")
    options = parser.parse_args()
    if options.mode in ("local", "remote"):
        directory = Path.cwd() if options.mode == "local" else ROOT
        if not directory.is_dir():
            raise SystemExit("SOURCE_DIRECTORY_UNAVAILABLE")
        for row in analyse(directory, include_public_names=options.mode == "local"):
            print("\t".join(row))
        return
    if not options.local or not options.remote:
        parser.error("comparison needs both reports")
    a = parse_report(Path(options.local).read_text(encoding="utf-8"), remote=False)
    b = parse_report(Path(options.remote).read_text(encoding="utf-8"), remote=True)
    compare(a, b)


if __name__ == "__main__":
    main()
