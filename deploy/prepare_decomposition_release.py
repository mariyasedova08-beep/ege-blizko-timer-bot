"""Prepare an offline reviewed file set. No install, SSH, bot or DB access.

Both input directories must be disposable, verified source copies. This tool
only reads five named runtime files and two baseline files; it never discovers
or copies credentials, databases or arbitrary server content.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

MANIFEST_PATH = Path(__file__).with_name("decomposition_release_manifest.json")
RUNTIME_FILES = frozenset({
    "decomposition_trainer.py", "decomposition_trainer_bank.py",
    "decomposition_trainer_questions.tsv", "run_bot_production.py", "kulek_rewards.py",
})
BASELINE_FILES = frozenset({"run_bot_production.py", "kulek_rewards.py"})


def _directory(path):
    path = Path(path).absolute()
    if path != path.resolve(strict=True) or not path.is_dir():
        raise ValueError("PLAIN_DIRECTORY_REQUIRED")
    return path


def _read_verified(root, name, expected):
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("MISSING_OR_LINKED_REVIEWED_FILE")
    if path.stat().st_size > 1_000_000:
        raise ValueError("SOURCE_FILE_TOO_LARGE")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("REVIEWED_CHECKSUM_MISMATCH")
    return data


def build(source, baseline, output, manifest_path=MANIFEST_PATH):
    source, baseline = _directory(source), _directory(baseline)
    output = Path(output).absolute()
    parent = _directory(output.parent)
    if output.exists() or output.is_symlink():
        raise ValueError("OUTPUT_MUST_NOT_EXIST")
    if any(output == root or root in output.parents or output in root.parents
           for root in (source, baseline)):
        raise ValueError("OUTPUT_MUST_BE_SEPARATE")
    if parent / output.name != output:
        raise ValueError("PLAIN_OUTPUT_PARENT_REQUIRED")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if (set(manifest["runtime_sha256"]) != RUNTIME_FILES
            or set(manifest["baseline_sha256"]) != BASELINE_FILES):
        raise ValueError("ALLOWLIST_MISMATCH")
    # Read and check everything before writing even an output directory.
    runtime = {name: _read_verified(source, name, digest)
               for name, digest in manifest["runtime_sha256"].items()}
    previous = {name: _read_verified(baseline, name, digest)
                for name, digest in manifest["baseline_sha256"].items()}
    for name in RUNTIME_FILES - BASELINE_FILES:
        if (baseline / name).exists() or (baseline / name).is_symlink():
            raise ValueError("NEW_FILE_ALREADY_EXISTS_IN_BASELINE")
    output.mkdir(mode=0o700)
    try:
        for folder, files in (("runtime", runtime), ("baseline", previous)):
            directory = output / folder
            directory.mkdir(mode=0o700)
            for name, data in files.items():
                path = directory / name
                path.write_bytes(data)
                path.chmod(0o600)
        report = {
            "status": "OFFLINE_FILESET_ONLY_NOT_APPROVED_FOR_DEPLOYMENT",
            "runtime_sha256": manifest["runtime_sha256"],
            "baseline_sha256": manifest["baseline_sha256"],
            "baseline_source": manifest["baseline_source"],
            "new_files_on_rollback": sorted(RUNTIME_FILES - BASELINE_FILES),
            "server_compatibility_verified": False,
            "telegram_verified": False,
            "production_backup_created": False,
            "production_modified": False,
            "next_gate": "reconcile_live_source_then_isolated_telegram_acceptance_then_separate_approval",
        }
        (output / "preflight.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        (output / "preflight.json").chmod(0o600)
    except BaseException:
        shutil.rmtree(output)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        build(args.source, args.baseline, args.output)
    except (OSError, ValueError, KeyError):
        parser.exit(1, "OFFLINE_PREPARATION_BLOCKED\n")
    print("OFFLINE_FILESET_READY; NO_VPS_NO_TELEGRAM_NO_DATABASE_ACCESS")


if __name__ == "__main__":
    main()
