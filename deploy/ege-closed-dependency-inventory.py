"""Read-only, confidential dependency inventory: no VPS source or student data exported."""
import argparse
import ast
import base64
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/opt/bots/ege-blizko")
SEEDS = ("run_bot_production", "run_bot_live7", "public_channel_trainers",
         "ege_lab_webapp", "oge9_trainer_notifications",
         "oge_classification_trainer", "ege11_lesson_transfer")
MAX_PYTHON_FILES = 512
MAX_FILE_BYTES = 2000000
MAX_OUTPUT_BYTES = 2000000
ALLOWED_ASSET_SUFFIXES = {".json", ".html", ".htm", ".css", ".js", ".mjs",
                          ".svg", ".png", ".jpg", ".jpeg", ".webp", ".txt",
                          ".csv", ".pdf"}
DATABASE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXCLUDE_PREFIXES = ("teacher_product_", "prepodmin", "sedova_pill", "pill_tracker")


def read_metadata(root=ROOT):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("ROOT_NOT_AVAILABLE")
    candidates = {}
    for entry in root.iterdir():
        if entry.suffix != ".py" or not NAME.fullmatch(entry.stem):
            continue
        if entry.name.startswith(EXCLUDE_PREFIXES):
            continue
        if entry.is_symlink():
            candidates[entry.stem] = None
        elif entry.is_file():
            candidates[entry.stem] = entry
    return candidates


def safe_resource(value):
    if not isinstance(value, str) or len(value) > 180 or "\x00" in value or "\n" in value:
        return None
    if "://" in value or value.startswith(("/", "~", "\\")):
        return None
    value = value.split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    parts = value.split("/")
    if not parts or any(x in ("", ".", "..") for x in parts):
        return None
    if not all(re.fullmatch(r"[\w .()\-@]+", x, flags=re.UNICODE) for x in parts):
        return None
    suffix = Path(value).suffix.lower()
    if suffix in ALLOWED_ASSET_SUFFIXES or suffix in DATABASE_SUFFIXES:
        return value, suffix in DATABASE_SUFFIXES
    return None


def imported_modules(tree):
    imports = set()
    dynamic = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
            elif node.level:
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            is_import = ((isinstance(func, ast.Name) and func.id == "__import__") or
                         (isinstance(func, ast.Attribute) and func.attr == "import_module" and
                          isinstance(func.value, ast.Name) and func.value.id == "importlib"))
            if is_import:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    imports.add(node.args[0].value.lstrip(".").split(".")[0])
                else:
                    dynamic += 1
    return sorted(x for x in imports if NAME.fullmatch(x)), dynamic


def static_resources(tree):
    assets, databases = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            result = safe_resource(node.value)
            if result:
                name, is_database = result
                (databases if is_database else assets).add(name)
    return sorted(assets), sorted(databases)


def audit(root=ROOT):
    available = read_metadata(root)
    queue = deque(SEEDS)
    inspected, modules = set(), {}
    assets_seen, databases_seen = set(), set()
    while queue:
        name = queue.popleft()
        if not NAME.fullmatch(name) or name in inspected:
            continue
        if len(inspected) >= MAX_PYTHON_FILES:
            raise ValueError("MODULE_BOUND_EXCEEDED")
        inspected.add(name)
        if name.startswith(EXCLUDE_PREFIXES):
            modules[name] = {"status": "excluded_other_product"}
            continue
        path = available.get(name)
        if path is None:
            modules[name] = {"status": "symlink" if name in available else "missing", "imports": []}
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            modules[name] = {"status": "size_limit"}
            continue
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("SOURCE_SIZE_CHANGED")
        try:
            tree = ast.parse(raw.decode("utf-8-sig"))
        except (UnicodeError, SyntaxError):
            modules[name] = {"status": "parse_failed"}
            continue
        imports, dynamic = imported_modules(tree)
        assets, databases = static_resources(tree)
        modules[name] = {"status": "present", "sha256": hashlib.sha256(raw).hexdigest(),
                         "bytes": len(raw), "imports": imports,
                         "dynamic_import_calls": dynamic, "assets": assets,
                         "databases_referenced": databases}
        assets_seen.update(assets)
        databases_seen.update(databases)
        # Inspect only immediately present .py modules reachable from the 7 seeds.
        for module in imports:
            if (module in available or module in SEEDS) and module not in inspected:
                queue.append(module)
    asset_results = {}
    for rel in sorted(assets_seen):
        parts = rel.split("/")
        parent, bad = root, False
        for part in parts[:-1]:
            parent = parent / part
            if parent.is_symlink():
                bad = True
                break
        path = root.joinpath(*parts)
        if bad or path.is_symlink():
            status, size = "symlink_skipped", None
        elif path.is_file():
            status, size = "present", path.stat().st_size
        else:
            status, size = "missing", None
        asset_results[rel] = {"status": status, "bytes": size}
    return {"format": "ege-dependencies-v1", "roots": list(SEEDS),
            "modules": modules, "assets": asset_results,
            "database_references_only": sorted(databases_seen),
            "caveats": ["static_imports_only", "root_level_local_modules_only",
                        "no_database_or_asset_content_read", "no_deployment"]}


def encrypt_in_memory(content, cert):
    if not hasattr(os, "memfd_create"):
        raise ValueError("MEMORY_ONLY_ENCRYPTION_UNAVAILABLE")
    fd = os.memfd_create("audit-public-cert", 0)
    try:
        os.write(fd, cert)
        os.lseek(fd, 0, 0)
        p = subprocess.run(["openssl", "cms", "-encrypt", "-aes-256-gcm",
                            "-binary", "-outform", "DER", "-recip",
                            "/proc/self/fd/" + str(fd)],
                           input=content, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, pass_fds=(fd,),
                           timeout=45, check=False)
        if p.returncode != 0 or not p.stdout.startswith(b"\x30"):
            raise ValueError("CANNOT_ENCRYPT")
        return p.stdout
    finally:
        os.close(fd)


def remote():
    cert = base64.b64decode(AUDIT_CERT_B64, validate=True)
    report = json.dumps(audit(), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(report) > MAX_OUTPUT_BYTES:
        raise ValueError("REPORT_SIZE_EXCEEDED")
    sys.stdout.buffer.write(encrypt_in_memory(report, cert))


def runner(args):
    if args.user != "ege-deploy" or args.host != "77.233.212.200":
        raise ValueError("INVALID_TARGET")
    source = Path(__file__).read_text(encoding="utf-8")
    cert_b64 = base64.b64encode(Path(args.cert).read_bytes()).decode("ascii")
    stdin = ("AUDIT_CERT_B64=" + repr(cert_b64) + "\n" + source).encode("utf-8")
    cmd = ["ssh", "-T", "-F", "/dev/null", "-o", "BatchMode=yes",
           "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes",
           "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
           "-o", "UserKnownHostsFile=" + args.known_hosts,
           "-o", "ConnectTimeout=10", "-i", args.ssh_key,
           args.user + "@" + args.host, "python3 - --mode remote"]
    response = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, check=False, timeout=110)
    if response.returncode != 0 or not response.stdout.startswith(b"\x30"):
        raise ValueError("SSH_OR_ENCRYPTION_FAILED")
    if len(response.stdout) > MAX_OUTPUT_BYTES + 65536:
        raise ValueError("CIPHERTEXT_SIZE_EXCEEDED")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(output), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(response.stdout)
    print("DEPENDENCY_INVENTORY_CIPHERTEXT_ONLY")
    print("NO_PYTHON_SOURCE_EXPORTED")
    print("NO_ASSET_OR_DATABASE_CONTENT_READ")
    print("NO_SERVER_WRITES_NO_DEPLOYMENT")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("runner", "remote"), required=True)
    for field in ("cert", "ssh-key", "known-hosts", "host", "user", "output"):
        parser.add_argument("--" + field)
    args = parser.parse_args()
    try:
        if args.mode == "remote":
            remote()
        else:
            runner(args)
    except Exception:
        print("PRIVATE_INVENTORY_STOPPED", file=sys.stderr)
        raise SystemExit(1) from None

if __name__ == "__main__":
    main()
