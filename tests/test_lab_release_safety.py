"""Static checks for the dedicated lab-only release automation (no deployment)."""
from pathlib import Path
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
        self.assertIn('cp --preserve=mode,timestamps', HELPER)
        self.assertIn("LAB_ROLLED_BACK", HELPER)
        self.assertIn('flock -w 60 9', HELPER)

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
