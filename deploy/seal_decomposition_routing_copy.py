"""Prepare an encrypted, hash-pinned copy for OFFLINE routing review.

No SSH, app imports, database, deployment or decryption. This is not a runnable
bot snapshot: only two routing modules are included. Plaintext stays in memory.
"""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

PINNED_FILES = {
    "run_bot_live7.py": "d61df65fd87e52a5ae852a28b5edbc1a026af4cbb5998ae3a542f793070415da",
    "public_channel_trainers.py": "be7b8d058da8cfd90ed57f9dae1f9e7769b448763ef56a8a18bdbebeab8c9a53",
}
RECIPIENT_CERT_SHA256 = "fe1f46e8f15ae494bef7280ab5491bf3a243a9e5c7c124bbc294bdf462754d6b"
MAX_BYTES = 1_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def open_directory(path):
    """Walk an absolute path through directory descriptors; reject all symlinks."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("INVALID_DIRECTORY")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def collect(source_root, expected=None):
    """Read exactly the pinned names, never scan or traverse source directories."""
    expected = PINNED_FILES if expected is None else expected
    if set(expected) != set(PINNED_FILES):
        raise ValueError("INVALID_ALLOWLIST")
    root_fd = open_directory(source_root)
    records = {}
    try:
        for name, sha in expected.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                    raise ValueError("INVALID_SOURCE_FILE")
                chunks = []
                remaining = MAX_BYTES + 1
                while remaining:
                    part = os.read(fd, min(65536, remaining))
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                raw = b"".join(chunks)
                after = os.fstat(fd)
                stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if (stamp(before) != stamp(after) or len(raw) != before.st_size
                        or len(raw) > MAX_BYTES or digest(raw) != sha):
                    raise ValueError("SOURCE_DRIFT")
                # Parse only: never execute top-level module code.
                ast.parse(raw)
                records[name] = {"sha256": sha, "content_b64": base64.b64encode(raw).decode("ascii")}
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)
    return json.dumps({
        "schema": 1, "purpose": "OFFLINE_ROUTING_REVIEW_ONLY",
        "complete_bot_snapshot": False, "files": records,
    }, sort_keys=True, separators=(",", ":")).encode()


def seal(payload, certificate, expected_cert_sha=RECIPIENT_CERT_SHA256):
    if len(certificate) > 65536 or digest(certificate) != expected_cert_sha:
        raise ValueError("RECIPIENT_MISMATCH")
    # memfd avoids putting even the public certificate in a temporary disk file.
    if not hasattr(os, "memfd_create"):
        raise ValueError("MEMORY_ENCRYPTION_UNAVAILABLE")
    fd = os.memfd_create("routing-copy-recipient", os.MFD_CLOEXEC)
    try:
        with os.fdopen(os.dup(fd), "wb") as handle:
            handle.write(certificate)
        os.lseek(fd, 0, os.SEEK_SET)
        result = subprocess.run([
            "openssl", "cms", "-encrypt", "-binary", "-aes-256-gcm",
            "-outform", "DER", "-recip", "/proc/self/fd/" + str(fd),
        ], input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            pass_fds=(fd,), timeout=30, check=False)
        if result.returncode or not result.stdout.startswith(b"\x30"):
            raise ValueError("ENCRYPTION_FAILED")
        return result.stdout
    finally:
        os.close(fd)


def write_ciphertext(output, ciphertext):
    output = Path(output)
    parent = open_directory(output.parent)
    fd = None
    created = False
    try:
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        created = True
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(ciphertext)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        if created:
            os.unlink(output.name, dir_fd=parent)
        raise
    finally:
        os.close(parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        with open(args.certificate, "rb") as cert_file:
            certificate = cert_file.read(65537)
        # Verify recipient before reading application source.
        if digest(certificate) != RECIPIENT_CERT_SHA256:
            raise ValueError("RECIPIENT_MISMATCH")
        ciphertext = seal(collect(args.source_root), certificate)
        write_ciphertext(args.output, ciphertext)
    except Exception:
        # Exception text can contain source lines, paths or OpenSSL diagnostics.
        print("ROUTING_COPY_STOPPED_NO_PLAINTEXT_OUTPUT", file=sys.stderr)
        return 1
    print("ENCRYPTED_COPY_CREATED_NOT_READY_FOR_RELEASE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
