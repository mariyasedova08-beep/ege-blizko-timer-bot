"""Static checks for the dedicated lab-only release automation (no deployment)."""
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / "deploy/ege-blizko-lab-release").read_text()
WORKFLOW = (ROOT / ".github/workflows/ege-lab-manual-release.yml").read_text()


class LabReleaseSafety(unittest.TestCase):
    def test_release_requires_explicit_confirmation(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertNotIn("\n  push:", WORKFLOW)
        self.assertIn("DEPLOY_LAB_ONLY", WORKFLOW)
        self.assertIn('test "$GITHUB_REF" = \'refs/heads/main\'', WORKFLOW)
        self.assertIn('and .conclusion == "success"', WORKFLOW)

    def test_release_fails_closed_on_wrong_branch_or_sha(self):
        self.assertIn('[[ "$ACTION" == "$REMOTE_SHA" ]]', HELPER)
        self.assertIn('git merge-base --is-ancestor "$BASE_SHA" "$ACTION"', HELPER)
        self.assertIn("allowed_application_file()", HELPER)

    def test_working_copy_is_not_reset(self):
        operational = "\n".join(
            line for line in HELPER.splitlines()
            if not line.strip().startswith("#")
        )
        for forbidden in ("git reset", "git checkout", "git clean", "rm -rf"):
            self.assertNotIn(forbidden, operational)
        self.assertIn('git apply --check "$PATCH"', HELPER)
        self.assertIn('cp --preserve=mode,ownership,timestamps', HELPER)
        self.assertIn("LAB_ROLLED_BACK", HELPER)
        self.assertIn('flock -w 60 9', HELPER)

    def test_apply_restores_original_access_before_restart(self):
        apply_index = HELPER.index('git apply "$PATCH"')
        access_index = HELPER.index('echo "LAB_FILE_ACCESS_RESTORED"', apply_index)
        restart_index = HELPER.index('systemctl restart "$SERVICE"', access_index)
        self.assertLess(apply_index, access_index)
        self.assertLess(access_index, restart_index)
        self.assertIn('chown --reference="$BACKUP/files/$path"', HELPER)
        self.assertIn('chmod --reference="$BACKUP/files/$path"', HELPER)
        self.assertIn('chmod 0644 -- "$APP_DIR/$path"', HELPER)

    def test_git_apply_with_restrictive_umask_can_remove_read_access(self):
        # Reproduces the production failure, then verifies reference-mode
        # restoration on a disposable test file. No production data touched.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "ege_lab_webapp.py"
            saved_mode = root / "saved_mode"
            patch = root / "test.patch"
            module.write_text("BASE = 1\\n")
            module.chmod(0o644)
            saved_mode.write_text("backup\\n")
            saved_mode.chmod(module.stat().st_mode & 0o777)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "ege_lab_webapp.py"], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Lab Tester", "-c",
                 "user.email=lab@example.com", "commit", "-qm", "baseline"],
                cwd=root, check=True,
            )
            module.write_text("BASE = 2\\n")
            diff = subprocess.run(["git", "diff", "--", "ege_lab_webapp.py"],
                                  cwd=root, check=True, capture_output=True).stdout
            patch.write_bytes(diff)
            module.write_text("BASE = 1\\n")
            subprocess.run(
                ["bash", "-c", "umask 077; git apply test.patch"], cwd=root, check=True,
            )
            self.assertEqual(stat.S_IMODE(module.stat().st_mode), 0o600)
            subprocess.run(
                ["chmod", "--reference=saved_mode", "ege_lab_webapp.py"],
                cwd=root, check=True,
            )
            self.assertEqual(stat.S_IMODE(module.stat().st_mode), 0o644)

    def test_failed_postrelease_probe_is_identified_before_rollback(self):
        self.assertIn('last_failure="service_not_active"', HELPER)
        self.assertIn('last_failure="health_url_failed"', HELPER)
        self.assertIn('last_failure="lab_url_failed"', HELPER)
        self.assertIn('last_failure="lab_page_marker_missing"', HELPER)
        self.assertIn('LAB_HEALTH_RETRY attempt=$attempt reason=$last_failure', HELPER)
        self.assertIn('LAB_HEALTH_CHECK_OK', HELPER)
        self.assertIn('ERROR: post-release health check failed reason=$last_failure', HELPER)
        self.assertIn('[[ "$healthy" -eq 1 ]] || {', HELPER)
        self.assertIn('LAB_RELEASE_FAILED restoring', HELPER)
        self.assertNotIn('cat "$BACKUP/health-page.html"', HELPER)

    def test_only_lab_related_sources_are_whitelisted(self):
        self.assertIn("ege_lab_webapp.py", HELPER)
        self.assertIn("ege_lab_substances.py", HELPER)
        self.assertIn("oge_task23_bank.py", HELPER)
        self.assertNotIn("teacher_product_webapp.py", HELPER)
        self.assertNotIn("prepodmin.service", HELPER)


if __name__ == "__main__":
    unittest.main()
