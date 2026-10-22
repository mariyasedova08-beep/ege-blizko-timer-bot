"""Runner-side preparation of an encrypted Python-only snapshot; no deployment."""
import argparse
import base64
import hashlib
from pathlib import Path
import subprocess
import sys

import seal_decomposition_routing_copy as encrypted

SOURCE_PINS = {
    "seal_decomposition_routing_copy.py": "477865d92ca35a686450945121afd959b15ef4c3a1014eb9e685746881adea02",
    "ege-closed-dependency-inventory.py": "bacb4a94161095adf02b50073c93def209eec7f19048ea2697eb5ab80115aeb0",
    "seal_ege_python_snapshot.py": "93d10b21fa3d6c9436a1bfdb6a2e61a9cd3bc69ba3c7946664b9614d78e5c01b",
}


def remote_payload(certificate, sources):
    if encrypted.digest(certificate) != encrypted.RECIPIENT_CERT_SHA256:
        raise ValueError("RECIPIENT_MISMATCH")
    if set(sources) != set(SOURCE_PINS):
        raise ValueError("SCRIPT_SET_MISMATCH")
    for name, pin in SOURCE_PINS.items():
        if hashlib.sha256(sources[name]).hexdigest() != pin:
            raise ValueError("SCRIPT_MISMATCH")
    result = subprocess.run(["openssl", "x509", "-checkend", "0", "-noout"],
                            input=certificate, capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError("CERTIFICATE_EXPIRED_OR_INVALID")
    prelude = "__name__ = 'sealed_python_snapshot_helper'\nREMOTE_CERT = " + repr(
        base64.b64encode(certificate).decode("ascii")) + "\n"
    suffix = """
try:
    certificate = base64.b64decode(REMOTE_CERT, validate=True)
    report = audit()
    plaintext = collect(report, Path('/opt/bots/ege-blizko'), open_directory)
    ciphertext = seal(plaintext, certificate)
except Exception:
    print('PYTHON_SNAPSHOT_REMOTE_STOPPED', file=sys.stderr)
    raise SystemExit(1)
sys.stdout.buffer.write(ciphertext)
"""
    return (prelude + "\n".join(sources[name].decode("utf-8") for name in SOURCE_PINS)
            + "\n" + suffix).encode("utf-8")


def capture(certificate, sources, *, key, known_hosts, host, user, output):
    if host != "77.233.212.200" or user != "ege-deploy":
        raise ValueError("SSH_IDENTITY_MISMATCH")
    payload = remote_payload(certificate, sources)
    result = subprocess.run([
        "ssh", "-T", "-F", "/dev/null", "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
        "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "ConnectTimeout=10",
        "-i", str(key), user + "@" + host, "python3 - --mode remote",
    ], input=payload, capture_output=True, timeout=90)
    if result.returncode or not result.stdout.startswith(b"\x30") or len(result.stdout) > 4_500_000:
        raise ValueError("SSH_OR_SNAPSHOT_FAILED")
    parsed = subprocess.run(["openssl", "cms", "-cmsout", "-inform", "DER", "-noout"],
                            input=result.stdout, capture_output=True, timeout=10)
    if parsed.returncode:
        raise ValueError("INVALID_CMS")
    encrypted.write_ciphertext(output, result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("certificate", "key", "known-hosts", "host", "user", "output"):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    try:
        directory = Path(__file__).resolve().parent
        sources = {name: (directory / name).read_bytes() for name in SOURCE_PINS}
        capture(Path(args.certificate).read_bytes(), sources, key=args.key,
                known_hosts=args.known_hosts, host=args.host, user=args.user,
                output=args.output)
    except Exception:
        print("PYTHON_SNAPSHOT_STOPPED_NO_PLAINTEXT_LOGGED", file=sys.stderr)
        return 1
    print("PYTHON_ONLY_CIPHERTEXT_CREATED_NOT_A_RUNNABLE_BOT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
