"""Runner-side transport: fixed read-only SSH command; ciphertext output only."""
import argparse
import base64
from pathlib import Path
import subprocess
import sys

import seal_decomposition_routing_copy as copy

APPROVED_HOST = "77.233.212.200"
APPROVED_USER = "ege-deploy"
EXPORTER_SHA256 = "477865d92ca35a686450945121afd959b15ef4c3a1014eb9e685746881adea02"
MAX_CIPHERTEXT = 4_000_000


def remote_payload(certificate, exporter):
    if copy.digest(certificate) != copy.RECIPIENT_CERT_SHA256:
        raise ValueError("RECIPIENT_MISMATCH")
    if copy.digest(exporter) != EXPORTER_SHA256:
        raise ValueError("EXPORTER_MISMATCH")
    check = subprocess.run(
        ["openssl", "x509", "-checkend", "0", "-noout"],
        input=certificate, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=10, check=False)
    if check.returncode:
        raise ValueError("RECIPIENT_CERTIFICATE_EXPIRED_OR_INVALID")
    # Do not execute the exporter's local CLI or create an output on VPS.
    prefix = "__name__ = 'routing_copy_remote_helper'\n"
    suffix = """
try:
    certificate = base64.b64decode(REMOTE_CERT_B64, validate=True)
    ciphertext = seal(collect(Path('/opt/bots/ege-blizko')), certificate)
except Exception:
    print('ROUTING_COPY_REMOTE_STOPPED', file=sys.stderr)
    raise SystemExit(1)
sys.stdout.buffer.write(ciphertext)
"""
    return (prefix + "REMOTE_CERT_B64 = " + repr(
        base64.b64encode(certificate).decode("ascii")) + "\n"
        + exporter.decode("utf-8") + "\n" + suffix).encode("utf-8")


def capture(certificate, exporter, *, key, known_hosts, host, user, output):
    if host != APPROVED_HOST or user != APPROVED_USER:
        raise ValueError("SSH_IDENTITY_MISMATCH")
    payload = remote_payload(certificate, exporter)
    command = [
        "ssh", "-T", "-F", "/dev/null", "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
        "-o", "UserKnownHostsFile=" + str(known_hosts),
        "-o", "ConnectTimeout=10", "-i", str(key),
        user + "@" + host, "python3 - --mode remote",
    ]
    result = subprocess.run(command, input=payload, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=90, check=False)
    if (result.returncode or not result.stdout.startswith(b"\x30")
            or len(result.stdout) > MAX_CIPHERTEXT):
        raise ValueError("SSH_CAPTURE_FAILED")
    # Parse the CMS without decrypting it; reject malformed/truncated output.
    envelope = subprocess.run(
        ["openssl", "cms", "-cmsout", "-inform", "DER", "-noout"],
        input=result.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=10, check=False)
    if envelope.returncode:
        raise ValueError("INVALID_CMS")
    copy.write_ciphertext(output, result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("certificate", "key", "known-hosts", "host", "user", "output"):
        parser.add_argument("--" + field, required=True)
    args = parser.parse_args()
    try:
        certificate = Path(args.certificate).read_bytes()
        exporter = Path(__file__).with_name("seal_decomposition_routing_copy.py").read_bytes()
        capture(certificate, exporter, key=args.key, known_hosts=args.known_hosts,
                host=args.host, user=args.user, output=args.output)
    except Exception:
        print("ROUTING_COPY_TRANSFER_STOPPED_NO_SOURCE_LOGGED", file=sys.stderr)
        return 1
    print("CIPHERTEXT_ONLY_NO_DEPLOYMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
