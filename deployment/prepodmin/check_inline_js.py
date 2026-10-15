"""Fail CI if an inline Telegram WebApp script has invalid JavaScript syntax.

Python's py_compile can't catch broken JavaScript embedded in HTML; a single
unescaped quote can otherwise leave a production WebApp stuck at its initial
loading screen. Uses Node's parse-only --check, never evaluates the script.
"""
import re
import subprocess
from pathlib import Path

FILES = (Path("teacher_product_webapp.html"), Path("teacher_product_student_webapp.html"))
SCRIPT = re.compile(r"<script(?:\s[^>]*)?>([\s\S]*?)</script\s*>", re.IGNORECASE)


def check():
    checked = 0
    for file in FILES:
        if not file.is_file():
            raise RuntimeError(f"Missing WebApp HTML: {file}")
        content = file.read_text(encoding="utf-8")
        scripts = [m.group(1) for m in SCRIPT.finditer(content) if m.group(1).strip()]
        if not scripts:
            raise RuntimeError(f"No inline WebApp JavaScript found: {file}")
        for n, script in enumerate(scripts, 1):
            result = subprocess.run(
                ["node", "--check"], input=script, text=True, capture_output=True, check=False,
            )
            if result.returncode:
                raise RuntimeError(
                    f"JavaScript syntax invalid in {file} inline script {n}:\n{result.stderr}"
                )
            print(f"PREPODMIN_JS_SYNTAX_OK {file} script={n}", flush=True)
            checked += 1
    if checked < 2:
        raise RuntimeError(f"Too few scripts checked: {checked}")


if __name__ == "__main__":
    check()
