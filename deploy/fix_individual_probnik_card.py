"""Patch only the individual admin card. Default is read-only; --apply requires approval."""
import argparse
import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path("/opt/bots/ege-blizko")
EXPECTED_FUNCTION = "def _individual_detail_markup(student_id, telegram_id):\n    rows = []\n    if telegram_id:\n        rows.append([InlineKeyboardButton(\"📊 Статистика тренажёров\", callback_data=f\"cab:individual:stats:{int(student_id)}\")])\n        rows.append([InlineKeyboardButton(\"🧪 Отправить тренажёры сейчас\", callback_data=f\"cab:individual:send:{int(student_id)}\")])\n    rows.append([InlineKeyboardButton(\"🔗 Ссылка подключения\", callback_data=f\"cab:individual:link:{int(student_id)}\")])\n    rows.append([InlineKeyboardButton(\"← К списку\", callback_data=\"cab:individuals\")])\n    return InlineKeyboardMarkup(rows)\n"

def patch_card(text):
    tree = ast.parse(text)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_individual_detail_markup"]
    if len(nodes) != 1:
        raise RuntimeError("Card function layout differs; preserve live code")
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    actual = "".join(lines[node.lineno-1:node.end_lineno])
    if ast.dump(ast.parse(actual)) != ast.dump(ast.parse(EXPECTED_FUNCTION)):
        raise RuntimeError("Card function changed or already patched; inspect first")
    replacement = actual.replace("    rows = []", '    import os\n    rows = []\n    if str(os.getenv("INDIVIDUAL_PROBNIK_ENABLED", "")).strip() == "1":\n        rows.append([InlineKeyboardButton("📝 Пробники", callback_data=f"cab:individual:probnik:{int(student_id)}")])', 1)
    result = "".join(lines[:node.lineno-1]) + replacement + "".join(lines[node.end_lineno:])
    compile(result, "individual_trainer_daily.py", "exec")
    return result

def healthy():
    try:
        with urlopen("http://127.0.0.1:8080/health", timeout=5) as response:
            return response.status == 200 and json.load(response).get("service") == "ege-blizko-timer-bot"
    except Exception:
        return False

def wait_health():
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if healthy():
            return
        print("WAITING_FOR_HTTP: startup in progress", flush=True)
        time.sleep(10)
    raise RuntimeError("Health did not recover within 600 seconds")

def atomic_write(path, data, metadata):
    fd, temp = tempfile.mkstemp(prefix=".individual-card-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, stat.S_IMODE(metadata.st_mode))
        os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = ROOT / "individual_trainer_daily.py"
    if path.is_symlink():
        raise RuntimeError("Refuse symlink source")
    before = path.read_bytes()
    after = patch_card(before.decode()).encode()
    cfg = json.loads((ROOT / "runtime-vars.json").read_text())
    if str(cfg.get("INDIVIDUAL_PROBNIK_ENABLED", "")).strip() != "1":
        raise RuntimeError("Individual probnik integration must already be enabled")
    if "_individual_probnik.install(" not in (ROOT / "run_bot_live67.py").read_text():
        raise RuntimeError("Individual result handler not installed")
    if not healthy():
        raise RuntimeError("Existing service is not healthy; do not change it")
    print("PREFLIGHT_OK: one card function only; results and queues untouched", flush=True)
    if not args.apply:
        return
    os.umask(0o077)
    backup = Path(tempfile.mkdtemp(prefix="ege-individual-card-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-", dir="/mnt"))
    (backup / path.name).write_bytes(before)
    if (backup / path.name).read_bytes() != before:
        raise RuntimeError("Backup verification failed")
    metadata = path.stat()
    (backup / "metadata.json").write_text(json.dumps({"mode":stat.S_IMODE(metadata.st_mode),"uid":metadata.st_uid,"gid":metadata.st_gid}))
    print("BACKUP_VERIFIED:", backup, flush=True)
    if path.read_bytes() != before:
        raise RuntimeError("Live source changed during preflight")
    try:
        atomic_write(path, after, metadata)
        subprocess.run(["systemctl", "restart", "ege-blizko.service"], check=True)
        wait_health()
    except BaseException:
        atomic_write(path, before, metadata)
        subprocess.run(["systemctl", "restart", "ege-blizko.service"], check=True)
        wait_health()
        print("ROLLBACK_OK: original card restored; database untouched", flush=True)
        raise
    print("INDIVIDUAL_CARD_PATCHED: HTTP OK; reopen Alina/Olya and verify Probniks", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("STOP: " + type(exc).__name__ + ": " + str(exc))

