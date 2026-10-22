"""Read-only closed diff. No VPS source is written to disk or printed in GitHub."""
import argparse
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib

FILES = (
    "run_bot_production.py", "run_bot_live7.py", "public_channel_trainers.py",
    "ege_lab_webapp.py", "oge9_trainer_notifications.py",
    "oge_classification_trainer.py", "ege11_lesson_transfer.py",
)
ROOT = Path("/opt/bots/ege-blizko")
LIMIT = 1_048_576
MAX_REPORT = 6_000_000


def read_limited(directory, name):
    path = directory / name
    if path.is_symlink():
        raise ValueError("SYMLINK_DENIED")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError("UNEXPECTED_FILE")
    value = path.read_bytes()
    if len(value) > LIMIT:
        raise ValueError("OVERSIZE_FILE")
    return value


def local_payload():
    result = {}
    for name in FILES:
        value = read_limited(Path.cwd(), name)
        result[name] = None if value is None else base64.b64encode(value).decode("ascii")
    return result


def encrypt_in_memory(cleartext, certificate):
    if not hasattr(os, "memfd_create"):
        raise ValueError("MEMORY_ENCRYPTION_UNAVAILABLE")
    fd = os.memfd_create("recipient-cert", 0)
    try:
        os.write(fd, certificate)
        os.lseek(fd, 0, 0)
        completed = subprocess.run(
            ["openssl", "cms", "-encrypt", "-aes-256-gcm", "-binary",
             "-outform", "DER", "-recip", "/proc/self/fd/" + str(fd)],
            input=cleartext, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            pass_fds=(fd,), check=False, timeout=40)
        if completed.returncode != 0 or not completed.stdout.startswith(b"\x30"):
            raise ValueError("ENCRYPTION_FAILED")
        return completed.stdout
    finally:
        os.close(fd)


def remote():
    # Values injected by the client are ONLY public GitHub files and public certificate.
    packed = base64.b64decode(AUDIT_DATA_B64, validate=True)
    github_files = json.loads(zlib.decompress(packed))
    if set(github_files) != set(FILES) or not ROOT.is_dir():
        raise ValueError("BAD_ALLOWLIST_OR_DIRECTORY")
    report = {"format": "ege-closed-diff-v1", "files": {}}
    for name in FILES:
        item = github_files[name]
        github = None if item is None else base64.b64decode(item, validate=True)
        server = read_limited(ROOT, name)
        if github is not None and len(github) > LIMIT:
            raise ValueError("GITHUB_OVERSIZE")
        left = "" if github is None else github.decode("utf-8-sig")
        right = "" if server is None else server.decode("utf-8-sig")
        changes = "".join(difflib.unified_diff(
            left.splitlines(keepends=True), right.splitlines(keepends=True),
            fromfile="github/" + name, tofile="vps/" + name))
        report["files"][name] = {
            "github_exists": github is not None,
            "server_exists": server is not None,
            "github_sha256": hashlib.sha256(github).hexdigest() if github is not None else None,
            "server_sha256": hashlib.sha256(server).hexdigest() if server is not None else None,
            "diff": changes,
        }
    message = json.dumps(report, ensure_ascii=False).encode("utf-8")
    if len(message) > MAX_REPORT:
        raise ValueError("REPORT_TOO_LARGE")
    cert = base64.b64decode(AUDIT_CERT_B64, validate=True)
    sys.stdout.buffer.write(encrypt_in_memory(message, cert))


def runner(args):
    if args.host != "77.233.212.200" or args.user != "ege-deploy":
        raise ValueError("UNAPPROVED_SERVER")
    source = Path(__file__).read_text(encoding="utf-8")
    compressed = zlib.compress(json.dumps(local_payload()).encode("utf-8"), 9)
    data_b64 = base64.b64encode(compressed).decode("ascii")
    cert_b64 = base64.b64encode(Path(args.cert).read_bytes()).decode("ascii")
    remote_script = ("AUDIT_DATA_B64=" + repr(data_b64) + "\n"
                     + "AUDIT_CERT_B64=" + repr(cert_b64) + "\n" + source)
    cmd = [
        "ssh", "-T", "-F", "/dev/null", "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
        "-o", "UserKnownHostsFile=" + args.known_hosts,
        "-o", "ConnectTimeout=10", "-i", args.ssh_key,
        args.user + "@" + args.host, "python3 - --mode remote",
    ]
    process = subprocess.run(cmd, input=remote_script.encode("utf-8"),
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             check=False, timeout=90)
    if process.returncode or not process.stdout.startswith(b"\x30"):
        raise ValueError("SSH_OR_ENCRYPTION_FAILED")
    if len(process.stdout) > MAX_REPORT + 32768:
        raise ValueError("ENCRYPTED_REPORT_TOO_LARGE")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(process.stdout)
    print("ENCRYPTED_DIFF_ONLY")
    print("AES_256_GCM_CMS")
    print("FILES_CONSIDERED=7")
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
    except Exception as exc:
        # Never print exception values, remote source, or decrypted data.
        print("SEALED_AUDIT_STOPPED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
