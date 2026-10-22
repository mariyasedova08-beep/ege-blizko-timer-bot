"""Hash-pinned PYTHON-ONLY snapshot preparation. Never import the application."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat

EXPECTED_MODULE_MANIFEST = "fea1c68c048704a55a20906f9e5e62288de95b1c283c58f3009f459566ce257c"
EXPECTED_MODULE_COUNT = 167
MAX_SOURCE_BYTES = 3_000_000
MAX_FILE_BYTES = 2_000_000


def manifest(report):
    result = {}
    for name, record in report["modules"].items():
        if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                or record.get("status") != "present"
                or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", ""))
                or type(record.get("bytes")) is not int
                or not 0 <= record["bytes"] <= MAX_FILE_BYTES):
            raise ValueError("MODULE_REPORT_REJECTED")
        result[name] = {"sha256": record["sha256"], "bytes": record["bytes"]}
    return result


def collect(report, root, open_directory, *, expected_digest=EXPECTED_MODULE_MANIFEST,
            expected_count=EXPECTED_MODULE_COUNT):
    modules = manifest(report)
    encoded = json.dumps(modules, sort_keys=True, separators=(",", ":")).encode()
    if (hashlib.sha256(encoded).hexdigest() != expected_digest
            or len(modules) != expected_count
            or sum(r["bytes"] for r in modules.values()) > MAX_SOURCE_BYTES):
        raise ValueError("INVENTORY_DRIFT")
    root_fd = open_directory(root)
    records = {}
    try:
        for name, record in sorted(modules.items()):
            fd = os.open(name + ".py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=root_fd)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or before.st_size != record["bytes"]:
                    raise ValueError("SOURCE_CHANGED")
                chunks, remaining = [], record["bytes"] + 1
                while remaining:
                    part = os.read(fd, min(65536, remaining))
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                raw = b"".join(chunks)
                after = os.fstat(fd)
                stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if (stamp(before) != stamp(after) or len(raw) != record["bytes"]
                        or hashlib.sha256(raw).hexdigest() != record["sha256"]):
                    raise ValueError("SOURCE_CHANGED")
                records[name + ".py"] = {**record, "content_b64": base64.b64encode(raw).decode("ascii")}
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)
    return json.dumps({
        "format": "ege-python-only-snapshot-v1", "modules": records,
        "module_manifest_sha256": expected_digest,
        "application_executed": False, "complete_runnable_snapshot": False,
        "assets_included": False, "databases_included": False,
    }, sort_keys=True, separators=(",", ":")).encode()


def load_inventory_and_copy_helpers():
    directory = Path(__file__).resolve().parent
    loaded = []
    for name in ("ege-closed-dependency-inventory", "seal_decomposition_routing_copy"):
        spec = importlib.util.spec_from_file_location(name, directory / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded
