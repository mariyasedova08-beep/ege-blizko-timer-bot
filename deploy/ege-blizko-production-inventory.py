"""Read-only, allowlisted inventory of EGE BLIZKO production source.

No secrets, database contents, student details or server files are copied. Use:
  python3 deploy/ege-blizko-production-inventory.py --mode local
  ssh restricted_user@host 'python3 - --mode remote' < deploy/ege-blizko-production-inventory.py
  python3 deploy/ege-blizko-production-inventory.py --mode compare --local PATH --remote PATH
"""
import argparse
import hashlib
import pathlib
import subprocess
import sys

# Fixed allowlist only. New products need their own dedicated manifests.
FILES = (
    "run_bot_production.py",
    "run_bot_live7.py",
    "run_bot_live25.py",
    "run_bot_live41.py",
    "run_bot_live51.py",
    "public_channel_trainers.py",
    "oge9_trainer_notifications.py",
    "oge_classification_trainer.py",
    "ege11_lesson_transfer.py",
    "homework_deadline_logic.py",
    "ege_lab_webapp.py",
    "kulek_rewards.py",
)
PRODUCTION_DIR = pathlib.Path("/opt/bots/ege-blizko")
MISSING = "MISSING"


def file_digest(directory, name):
    path = directory / name
    # Fail closed: never follow a production symlink while hashing source.
    if path.is_symlink():
        raise ValueError(f"SYMLINK_FILE_FORBIDDEN: {name}")
    if not path.is_file():
        return MISSING
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(directory):
    return {name: file_digest(directory, name) for name in FILES}


def lines_for_inventory(records):
    return [f"FILE\t{name}\t{records[name]}" for name in FILES]


def read_inventory(text):
    found = {}
    service_status = None
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] == "FILE" and parts[1] in FILES:
            name, digest = parts[1], parts[2]
            if name in found:
                raise ValueError("Duplicate inventory record")
            if digest != MISSING and (
                len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("Malformed digest")
            found[name] = digest
        elif len(parts) == 2 and parts[0] == "SERVICE":
            if service_status is not None:
                raise ValueError("Duplicate service record")
            service_status = parts[1]
        elif line.strip():
            raise ValueError("Unexpected inventory output")
    if set(found) != set(FILES):
        raise ValueError("Incomplete inventory")
    return found, service_status


def compare(local, remote):
    result = {"same": [], "different": [], "only_server": [], "only_github": [], "missing_both": []}
    for name in FILES:
        l, r = local[name], remote[name]
        if l == MISSING and r == MISSING:
            result["missing_both"].append(name)
        elif l == MISSING:
            result["only_server"].append(name)
        elif r == MISSING:
            result["only_github"].append(name)
        elif l == r:
            result["same"].append(name)
        else:
            result["different"].append(name)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("local", "remote", "compare"), required=True)
    parser.add_argument("--local")
    parser.add_argument("--remote")
    args = parser.parse_args()
    if args.mode in {"local", "remote"}:
        root = pathlib.Path(".") if args.mode == "local" else PRODUCTION_DIR
        if args.mode == "remote" and not root.is_dir():
            raise SystemExit("PRODUCTION_DIRECTORY_UNAVAILABLE")
        for line in lines_for_inventory(inventory(root)):
            print(line)
        if args.mode == "remote":
            result = subprocess.run(
                ["systemctl", "is-active", "ege-blizko.service"],
                text=True, capture_output=True, check=False, timeout=10
            )
            value = (result.stdout or "").strip()
            if value not in {"active", "inactive", "failed", "activating", "deactivating", "unknown"}:
                value = "unknown"
            print("SERVICE\t" + value)
        return

    if not args.local or not args.remote:
        parser.error("--mode compare requires --local and --remote")
    github, _ = read_inventory(pathlib.Path(args.local).read_text(encoding="utf-8"))
    server, state = read_inventory(pathlib.Path(args.remote).read_text(encoding="utf-8"))
    outcome = compare(github, server)
    print("# ЕГЭ БЛИЗКО — безопасная сверка с VPS")
    print()
    print("Проверены только разрешённые файлы Python; секреты и базы не читались.")
    print("Сервис:", state or "не удалось определить")
    print()
    for title, key in (
        ("Совпадают", "same"),
        ("Различаются (не переносить автоматически)", "different"),
        ("Есть только на VPS", "only_server"),
        ("Есть только в GitHub", "only_github"),
        ("Отсутствуют в обоих местах", "missing_both"),
    ):
        print(f"## {title} — {len(outcome[key])}")
        for name in outcome[key]:
            print(f"- `{name}`")
        print()
    print("NO_SERVER_FILES_CHANGED")
    print("NO_DEPLOYMENT_PERFORMED")
    if state != "active":
        raise SystemExit("PRODUCTION_SERVICE_NOT_ACTIVE")
    if outcome["different"] or outcome["only_server"] or outcome["only_github"]:
        raise SystemExit("DRIFT_DETECTED_REVIEW_REQUIRED")
    print("NO_SOURCE_DRIFT_IN_ALLOWLIST")


if __name__ == "__main__":
    main()
