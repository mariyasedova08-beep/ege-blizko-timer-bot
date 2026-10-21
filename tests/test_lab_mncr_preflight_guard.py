"""Ensure read-only Timeweb preflight never mutates the bot or host."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "check-ege-lab-mncr-readonly.sh"

class TimewebPreflightGuard(unittest.TestCase):
    def test_bash_syntax(self):
        result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_readonly_commands(self):
        text = SCRIPT.read_text(encoding="utf-8")
        commands = "\n".join(line.strip() for line in text.splitlines()
                             if line.strip() and not line.lstrip().startswith("#"))
        for forbidden in (
            r"\bgit\s+(?:pull|fetch|reset|checkout|switch|clean|push|commit)\b",
            r"\bsystemctl\s+(?:restart|reload|start|stop|enable|disable|daemon-reload)\b",
            r"\b(?:rm|mv|cp|rsync|sed\s+-i|sqlite3|tar|tee|chmod|chown|touch)\b",
            r"\b(?:curl|wget)\b[^\n]*\s+(?:-X\s+(?:POST|PUT|PATCH|DELETE)|--data|--upload-file)",
        ):
            self.assertNotRegex(commands, forbidden)
        self.assertIn('export GIT_OPTIONAL_LOCKS=0', text)
        self.assertIn('git_head', text)
        self.assertIn('last_successful_release_marker', text)

if __name__ == "__main__":
    unittest.main()
