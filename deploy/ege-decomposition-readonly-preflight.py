"""Fail-closed PRE-RELEASE CHECK for adding the decomposition trainer.

This tool NEVER writes, deploys, imports bot modules, opens the student database,
or restarts services. It only checks compatibility of a candidate 2-file change
with the existing server entrypoint. Actual release requires separately approved
and reviewed installation + backup + rollback mechanics.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

APP_NAME = "run_bot_production.py"
CANDIDATES = ("decomposition_trainer.py", "decomposition_trainer_bank.py")
ANCHOR = "    middle_salts_trainer.install()"
INSERTION = "    import decomposition_trainer\n    decomposition_trainer.install()\n"
MAX_BYTES = 1_048_576


class StagingBlocked(ValueError):
    pass


def read_source(directory, name):
    if directory.is_symlink() or not directory.is_dir():
        raise StagingBlocked("UNSAFE_DIRECTORY")
    if Path(name).name != name:
        raise StagingBlocked("UNEXPECTED_FILE")
    path = directory / name
    if path.is_symlink() or not path.is_file():
        raise StagingBlocked("MISSING_OR_SYMLINK")
    if path.stat().st_size > MAX_BYTES:
        raise StagingBlocked("SOURCE_TOO_LARGE")
    data = path.read_bytes()
    if len(data) > MAX_BYTES or b"\x00" in data:
        raise StagingBlocked("INVALID_SOURCE_BYTES")
    try:
        source = data.decode("utf-8-sig")
        tree = ast.parse(source, filename=name)
    except (UnicodeError, SyntaxError):
        raise StagingBlocked("PYTHON_PARSE_FAILED") from None
    return data, source, tree


def unique_anchor_in_main(source, tree):
    mains = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == "main"]
    if len(mains) != 1 or not isinstance(mains[0], ast.FunctionDef):
        raise StagingBlocked("PRODUCTION_MAIN_MISSING_OR_DUPLICATED")
    main = mains[0]
    install = [
        node for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "middle_salts_trainer"
        and node.func.attr == "install"
        and not node.args and not node.keywords
    ]
    module_import = [
        node for node in ast.walk(main)
        if isinstance(node, ast.Import)
        and any(alias.name == "middle_salts_trainer" for alias in node.names)
    ]
    if len(install) != 1 or len(module_import) != 1:
        raise StagingBlocked("KNOWN_RUNTIME_ANCHOR_NOT_UNIQUE")
    if module_import[0].lineno >= install[0].lineno:
        raise StagingBlocked("KNOWN_IMPORT_AFTER_INSTALL")
    if source.count("decomposition_trainer") != 0:
        raise StagingBlocked("TRAINER_MAY_ALREADY_BE_INSTALLED")
    lines = source.splitlines(keepends=True)
    line_index = install[0].lineno - 1
    if line_index >= len(lines) or lines[line_index].strip() != ANCHOR.strip():
        raise StagingBlocked("ANCHOR_HAS_UNEXPECTED_LAYOUT")
    if source.count(ANCHOR.strip()) != 1:
        raise StagingBlocked("ANCHOR_DUPLICATED_IN_SOURCE")
    return line_index


def proposed_patch(source, tree):
    """Return a changed copy IN MEMORY; never change production file."""
    line_index = unique_anchor_in_main(source, tree)
    eol = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines(keepends=True)
    lines.insert(line_index + 1, eol + INSERTION.replace("\n", eol))
    text = "".join(lines)
    ast.parse(text)
    if text.count("decomposition_trainer.install()") != 1:
        raise StagingBlocked("DUPLICATE_INSTALLATION")
    return text


def check(live_dir, candidate_dir):
    live_data, live_source, live_tree = read_source(live_dir, APP_NAME)
    _dependency, _s, _t = read_source(live_dir, "run_bot_live85.py")
    hashes = {}
    for name in CANDIDATES:
        if (live_dir / name).exists() or (live_dir / name).is_symlink():
            raise StagingBlocked("CANDIDATE_FILENAME_ALREADY_EXISTS")
        data, _, _ = read_source(candidate_dir, name)
        hashes[name] = hashlib.sha256(data).hexdigest()
    patched = proposed_patch(live_source, live_tree)
    if patched == live_source:
        raise StagingBlocked("NO_CHANGE_DETECTED")
    # Never include source, AST, credentials, or absolute path in output.
    return {
        "status": "READ_ONLY_PRECHECK_OK_NOT_DEPLOYED",
        "production_entrypoint_sha256": hashlib.sha256(live_data).hexdigest(),
        "candidate_file_sha256": hashes,
        "patch_locations": 1,
        "new_python_files": 2,
        "existing_database_untouched": True,
        "student_data_read": False,
        "production_written": False,
        "bot_restarted": False,
        "next_step": "separate_review_of_root_owned_release_with_backup_and_rollback",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-dir", required=True)
    parser.add_argument("--candidate-dir", required=True)
    args = parser.parse_args()
    try:
        result = check(Path(args.live_dir), Path(args.candidate_dir))
    except (OSError, ValueError) as exc:
        # Only an allowlisted error code. Never log production source or paths.
        code = str(exc) if isinstance(exc, StagingBlocked) else type(exc).__name__
        print("DECOMPOSITION_PREFLIGHT_STOPPED: " + code, file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
