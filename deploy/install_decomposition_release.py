#!/usr/bin/python3
"""Fixed root-owned release for the reviewed decomposition trainer only."""
import ast
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

RELEASE_ID = "EGE-DECOMPOSITION-20261022-REVIEWED"
SOURCE_SHA = "f8eeb92d7e1ecbaed9a1a46c7673125dae3512b6"
APP = Path("/opt/bots/ege-blizko")
DB = APP / "data/coreapp_webhooks.db"
STATE = Path("/var/lib/ege-blizko-decomposition")
SERVICE = "ege-blizko"
LOCK = Path("/run/lock/ege-blizko-autodeploy.lock")
NEW = {
    "decomposition_trainer.py": "364afa623956d154fa9d0ad01780aac3fd15f0b9871b7fd88bd5e0b97fa494be",
    "decomposition_trainer_bank.py": "b371826f16509227120c87574eda58e25876c6d4969f17a9fb66e08bdd812656",
    "decomposition_trainer_questions.tsv": "7576f6de5969434c602fb6f4cb970b50a770cbf55be13c8803c8ec161666eded",
}
OLD = {
    "run_bot_production.py": "303ace7665f229686f0e4c3cb2b37acaf2c4340846d360ac93e340c14d88db99",
    "kulek_rewards.py": "57e80fc0520f20c6c846a88f7a944165702c22cacdb321a88b7f102178a778cb",
}
PATCHED = {
    "run_bot_production.py": "e49f0eef9f8bde30a0129759cf6b516ea0351d151a21c2892accea0e290ceef1",
    "kulek_rewards.py": "76ab3666a6b62488f15b266dd6de2e4eeff4ec1635a84abb3cf7d8dd0b3f55a3",
}
ROUTERS = {
    "run_bot_live7.py": "d61df65fd87e52a5ae852a28b5edbc1a026af4cbb5998ae3a542f793070415da",
    "public_channel_trainers.py": "be7b8d058da8cfd90ed57f9dae1f9e7769b448763ef56a8a18bdbebeab8c9a53",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path, directory=False):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve(strict=True):
        raise ValueError("PLAIN_PATH_REQUIRED")
    info = path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("UNEXPECTED_FILE_TYPE")
    return info


def read_pinned(path, expected):
    plain(path)
    raw = Path(path).read_bytes()
    if len(raw) > 2_000_000 or digest(raw) != expected:
        raise ValueError("SOURCE_DRIFT_STOPPED")
    return raw


def patch_sources(original):
    startup = b"    middle_salts_trainer.install()\n"
    startup_add = b"    import decomposition_trainer\n    decomposition_trainer.install()\n"
    rewards = b'            table = TRAINER_TABLES.get(code, f"{code}_sessions")\n'
    rewards_add = b'            if code == "decomposition":\n                continue\n'
    result = {}
    for name, anchor, addition, after in [
        ("run_bot_production.py", startup, startup_add, True),
        ("kulek_rewards.py", rewards, rewards_add, False),
    ]:
        raw = original[name]
        if digest(raw) != OLD[name]:
            raise ValueError("PATCH_BASE_MISMATCH")
        lines = raw.splitlines(keepends=True)
        function_name = "main" if after else "_trainer_goals"
        functions = [n for n in ast.parse(raw).body
                     if isinstance(n, ast.FunctionDef) and n.name == function_name]
        if len(functions) != 1:
            raise ValueError("PATCH_FUNCTION_MISMATCH")
        node = functions[0]
        block = b"".join(lines[node.lineno-1:node.end_lineno])
        if block.count(anchor) != 1:
            raise ValueError("PATCH_ANCHOR_MISMATCH")
        block = block.replace(anchor, anchor + addition if after else addition + anchor, 1)
        patched = b"".join(lines[:node.lineno-1]) + block + b"".join(lines[node.end_lineno:])
        if digest(patched) != PATCHED[name]:
            raise ValueError("PATCH_RESULT_MISMATCH")
        ast.parse(patched)
        result[name] = patched
    return result


def validate_new(files):
    if set(files) != set(NEW):
        raise ValueError("PACKAGE_ALLOWLIST_MISMATCH")
    for name, raw in files.items():
        if digest(raw) != NEW[name]:
            raise ValueError("PACKAGE_HASH_MISMATCH")
        if name.endswith(".py"):
            compile(raw, name, "exec")
    rows = list(csv.reader(io.StringIO(files["decomposition_trainer_questions.tsv"].decode()), delimiter="\t"))
    if len(rows) != 50 or any(len(r) != 7 or len(set(r[1:5])) != 4 for r in rows):
        raise ValueError("QUESTION_BANK_INVALID")


def atomic_write(path, raw, metadata):
    fd, temporary = tempfile.mkstemp(prefix=".decomposition-release-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def database_backup(source, destination):
    plain(source)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30) as live:
        with sqlite3.connect(destination, timeout=30) as backup:
            live.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("DATABASE_BACKUP_INVALID")
    os.chmod(destination, 0o600)


def hide_rollback_catalog(db):
    # Preserve all attempts, payments and every other trainer setting.
    with sqlite3.connect(db, timeout=30) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "weekly_trainer_catalog" in tables:
            conn.execute("UPDATE weekly_trainer_catalog SET active=0 WHERE code='decomposition'")
        if "channel_trainer_catalog_settings" in tables:
            conn.execute("""INSERT INTO channel_trainer_catalog_settings(code,public_active,updated_at)
                VALUES('decomposition',0,?) ON CONFLICT(code)
                DO UPDATE SET public_active=0,updated_at=excluded.updated_at""",
                (datetime.now(timezone.utc).isoformat(),))


def enable_public_catalog(db):
    with sqlite3.connect(db, timeout=30) as conn:
        conn.execute("""INSERT INTO channel_trainer_catalog_settings(code,public_active,updated_at)
            VALUES('decomposition',1,?) ON CONFLICT(code)
            DO UPDATE SET public_active=1,updated_at=excluded.updated_at""",
            (datetime.now(timezone.utc).isoformat(),))


def run(command, timeout=30):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError("SERVICE_COMMAND_FAILED")
    return result.stdout.strip()


def verify_database_configuration():
    # Configuration stays on VPS. No credentials or environment values are logged.
    values = []
    config = APP / "runtime-vars.json"
    if config.exists():
        plain(config)
        data = json.loads(config.read_text())
        if isinstance(data, dict) and data.get("COREAPP_DB_PATH"):
            values.append(data["COREAPP_DB_PATH"])
    env = run(["systemctl", "show", SERVICE, "-p", "Environment", "--value"])
    for field in shlex.split(env):
        if field.startswith("COREAPP_DB_PATH="):
            values.append(field.split("=", 1)[1])
    if not values or any(Path(value) != DB for value in values):
        raise ValueError("DATABASE_CONFIGURATION_UNVERIFIED")
    plain(DB)
    for suffix in ("-wal", "-shm"):
        path = Path(str(DB) + suffix)
        if path.exists():
            plain(path)


def healthy(since):
    if run(["systemctl", "is-active", SERVICE]) != "active":
        return False
    with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5) as response:
        if response.status != 200:
            return False
    logs = run(["journalctl", "-u", SERVICE, "--since", "@" + str(since),
                "--no-pager", "-o", "cat", "-n", "2000"])
    if "Decomposition Telegram trainer: 50 questions ready" not in logs:
        return False
    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"decomposition_sessions", "decomposition_attempts", "decomposition_errors",
                "decomposition_progress"}.issubset(tables):
            return False
        row = conn.execute("SELECT start_param,active FROM weekly_trainer_catalog WHERE code='decomposition'").fetchone()
        if row != ("decomposition", 1):
            return False
    return True


def install():
    if os.geteuid() != 0 or sys.argv[1:] != [RELEASE_ID]:
        raise ValueError("ROOT_AND_FIXED_RELEASE_ID_REQUIRED")
    os.umask(0o077)
    plain(APP, directory=True)
    with open(LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if run(["systemctl", "is-active", SERVICE]) != "active":
            raise ValueError("SERVICE_NOT_ACTIVE")
        if run(["systemctl", "show", SERVICE, "-p", "User", "--value"]) != "ege-bot":
            raise ValueError("SERVICE_USER_MISMATCH")
        verify_database_configuration()
        for name, sha in ROUTERS.items():
            read_pinned(APP / name, sha)
        if all((APP / n).is_file() and not (APP / n).is_symlink()
               and digest((APP / n).read_bytes()) == sha for n, sha in {**NEW, **PATCHED}.items()):
            if healthy(0):
                print("DECOMPOSITION_ALREADY_INSTALLED_NO_RESTART")
                return
            raise ValueError("EXISTING_INSTALLATION_REQUIRES_REVIEW")
        for name in NEW:
            if os.path.lexists(APP / name):
                raise ValueError("NEW_FILE_COLLISION")
        original = {name: read_pinned(APP / name, sha) for name, sha in OLD.items()}
        metadata = {name: plain(APP / name) for name in OLD}
        payload = {}
        for name in NEW:
            url = "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/" + SOURCE_SHA + "/" + name
            with urllib.request.urlopen(url, timeout=30) as response:
                payload[name] = response.read(2_000_001)
        validate_new(payload)
        modified = patch_sources(original)
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        plain(STATE, directory=True)
        archive = STATE / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid()))
        archive.mkdir(mode=0o700)
        for name, raw in original.items():
            (archive / name).write_bytes(raw)
        (archive / "metadata.json").write_text(json.dumps({
            name: {"uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
            for name, info in metadata.items()}, sort_keys=True))
        database_backup(DB, archive / "database.sqlite")
        # Recheck after download/backup, before the first application write.
        for name, sha in {**OLD, **ROUTERS}.items():
            read_pinned(APP / name, sha)
        changed = []
        try:
            for name, raw in {**payload, **modified}.items():
                if name in NEW:
                    if os.path.lexists(APP / name):
                        raise ValueError("NEW_FILE_COLLISION")
                    reference = metadata["run_bot_production.py"]
                    reference = os.stat_result((stat.S_IFREG | 0o644,) + tuple(reference)[1:])
                else:
                    reference = metadata[name]
                changed.append(name)
                atomic_write(APP / name, raw, reference)
            enable_public_catalog(DB)
            since = int(time.time())
            run(["systemctl", "restart", SERVICE], timeout=60)
            for _ in range(15):
                try:
                    if healthy(since):
                        (STATE / "last-success").write_text(str(archive))
                        print("DECOMPOSITION_RELEASE_OK_BACKUP_AND_STARTUP_VERIFIED")
                        return
                except Exception:
                    pass
                time.sleep(2)
            raise ValueError("POST_RELEASE_CHECK_FAILED")
        except BaseException:
            for name in reversed(changed):
                if name in original:
                    atomic_write(APP / name, original[name], metadata[name])
                else:
                    (APP / name).unlink(missing_ok=True)
            hide_rollback_catalog(DB)
            run(["systemctl", "restart", SERVICE], timeout=60)
            if run(["systemctl", "is-active", SERVICE]) != "active":
                raise ValueError("ROLLBACK_SERVICE_REQUIRES_ATTENTION")
            print("DECOMPOSITION_ROLLED_BACK_DATABASE_NOT_RESTORED", file=sys.stderr)
            raise


def rollback_last():
    if os.geteuid() != 0 or sys.argv[1:] != [RELEASE_ID + "-ROLLBACK"]:
        raise ValueError("ROOT_AND_FIXED_ROLLBACK_ID_REQUIRED")
    plain(APP, directory=True)
    plain(STATE, directory=True)
    plain(STATE / "last-success")
    archive = Path((STATE / "last-success").read_text())
    plain(archive, directory=True)
    if archive.parent != STATE:
        raise ValueError("INVALID_BACKUP_DIRECTORY")
    with open(LOCK, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_database_configuration()
        for name, sha in {**NEW, **PATCHED}.items():
            read_pinned(APP / name, sha)
        saved = {name: read_pinned(archive / name, sha) for name, sha in OLD.items()}
        plain(archive / "metadata.json")
        metadata = json.loads((archive / "metadata.json").read_text())
        if set(metadata) != set(OLD):
            raise ValueError("INVALID_BACKUP_METADATA")
        for name, raw in saved.items():
            value = metadata[name]
            info = os.stat_result((stat.S_IFREG | value["mode"], 0, 0, 1,
                                  value["uid"], value["gid"], len(raw), 0, 0, 0))
            atomic_write(APP / name, raw, info)
        for name in NEW:
            (APP / name).unlink()
        hide_rollback_catalog(DB)
        run(["systemctl", "restart", SERVICE], timeout=60)
        if run(["systemctl", "is-active", SERVICE]) != "active":
            raise ValueError("ROLLBACK_SERVICE_REQUIRES_ATTENTION")
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=10) as response:
            if response.status != 200:
                raise ValueError("ROLLBACK_HEALTH_FAILED")
        print("DECOMPOSITION_ROLLBACK_OK_DATABASE_NOT_RESTORED")


if __name__ == "__main__":
    def interrupted(_signum, _frame):
        raise RuntimeError("RELEASE_INTERRUPTED")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if sys.argv[1:] == [RELEASE_ID + "-ROLLBACK"]:
            rollback_last()
        else:
            install()
    except BaseException:
        print("DECOMPOSITION_RELEASE_STOPPED_NO_PRIVATE_LOGS", file=sys.stderr)
        raise SystemExit(1)
