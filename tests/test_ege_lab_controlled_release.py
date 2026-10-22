"""Static safety gate for the unattended (but owner-approved) lab-only release.

This test NEVER contacts Timeweb, never reads secrets and never deploys.
"""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "deploy/bootstrap-ege-lab-deploy.sh"
ENTRY = ROOT / "deploy/ege-lab-restricted-ssh-entry.sh"
RELEASE = ROOT / "deploy/ege-lab-mncr-approved-release.sh"
WORKFLOW = ROOT / ".github/workflows/ege-lab-controlled-release.yml"
SSH_PROBE = ROOT / ".github/workflows/ege-lab-ssh-connectivity-test.yml"
EXPECTED_SHA = "23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e"
EXPECTED_COMMIT = "7b31b039c7dcc6d3ae2f31e5f241f747f17f5d17"
EXPECTED_LIVE = "d95b80eb423a6295eac080f66d1707ac1e92e789"

class ControlledReleaseGuard(unittest.TestCase):
    def test_shell_syntax_only(self):
        p = subprocess.run(["bash", "-n", str(RELEASE)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_release_requires_pinned_source_and_live_version(self):
        s = RELEASE.read_text(encoding="utf-8")
        for required in (EXPECTED_SHA, EXPECTED_COMMIT, EXPECTED_LIVE,
                         "Requires exact pinned release ID", "Must run as the restricted sudo target",
                         "flock -w 30 9", "CONSISTENT_DATABASE_BACKUP_OK",
                         "PRE_DEPLOY_BACKUP_OK", "ROLLING_BACK_LAB_ONLY"):
            self.assertIn(required, s)
        self.assertIn("trap rollback ERR", s)
        self.assertIn("return 1; }", s)
        self.assertIn("sha256sum -c", s)
        self.assertIn("STAGING_DIAGNOSTIC:", s)

    def test_limited_ssh_has_forced_command_and_exact_sudo_scope(self):
        entry = ENTRY.read_text(encoding="utf-8")
        setup = BOOTSTRAP.read_text(encoding="utf-8")
        for path in (ENTRY, BOOTSTRAP):
            check = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn('SSH_ORIGINAL_COMMAND:-', entry)
        self.assertIn('"release-ege-lab-mncr"', entry)
        self.assertIn('sudo -n /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED', entry)
        self.assertIn('command="/usr/local/libexec/ege-lab-release-entry",restrict', setup)
        self.assertIn('useradd --create-home --user-group', setup)
        self.assertIn('passwd -l "$USER"', setup)
        self.assertIn("visudo -cf", setup)
        self.assertNotIn("root@77.233.212.200", entry)
        self.assertNotIn('git reset', setup)

    def test_ssh_probe_never_calls_release_or_sudo(self):
        p = SSH_PROBE.read_text(encoding="utf-8")
        self.assertIn("environment: production-lab", p)
        self.assertIn("deploy/connectivity-probes/ege-lab-ssh.txt", p)
        self.assertIn("verify-ege-lab-connection", p)
        self.assertIn("DEPLOY_SSH_DENIED: unrecognized command", p)
        self.assertIn("NO_RELEASE_EXECUTED", p)
        self.assertIn("StrictHostKeyChecking=yes", p)
        self.assertNotIn("release-ege-lab-mncr", p)
        self.assertNotIn("systemctl", p)
        self.assertNotIn("sudo -n", p)
        self.assertNotIn("workflow_dispatch:", p)
        self.assertNotIn("pull_request:", p)
        self.assertIn("branches: [main]", p)

    def test_does_not_reset_live_git_or_change_bot_data(self):
        s = RELEASE.read_text(encoding="utf-8")
        self.assertNotRegex(s, r"\bgit\s+(?:reset|clean|pull|checkout|switch|push)\b")
        self.assertNotRegex(s, r"\bsystemctl\s+(?:disable|enable|stop)\b")
        self.assertNotRegex(s, r"\b(?:sqlite3|rm)\b[^\n]*coreapp_webhooks")
        self.assertNotIn("deploy/release.ref\n", s)
        self.assertIn("LIVE_ONLY_FILES=(public_channel_trainers.py run_bot_production.py)", s)
        self.assertIn("LAB_FILES=(ege_lab_webapp.py ege_lab_substances.py ege_lab_inorganic_reactions.py ege_lab_mn_cr_pdf_import.py)", s)

    def test_workflow_does_not_deploy_on_pr_or_regular_push(self):
        w = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", w)
        self.assertIn("push:", w)
        self.assertIn("deploy/release-intents/ege-lab-mncr.txt", w)
        self.assertIn("environment: production-lab", w)
        self.assertIn("github.actor == 'mariyasedova08-beep'", w)
        self.assertIn("refs/heads/main", w)
        self.assertIn("EXPLICIT_RELEASE_INTENT_VERIFIED", w)
        self.assertIn("StrictHostKeyChecking=yes", w)
        self.assertIn("EGE_LAB_DEPLOY_SSH_KEY", w)
        self.assertIn("EGE_LAB_DEPLOY_KNOWN_HOSTS", w)
        self.assertIn("ege-lab-deploy@77.233.212.200", w)
        self.assertNotIn("root@77.233.212.200", w)
        self.assertNotIn("workflow_dispatch:", w)
        self.assertNotRegex(w, r"(?m)^\s+cancel-in-progress:\s+true\s*$")

if __name__ == "__main__":
    unittest.main()
