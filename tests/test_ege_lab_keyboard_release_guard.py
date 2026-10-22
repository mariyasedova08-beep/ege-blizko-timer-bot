"""Static safeguards for the keyboard-only laboratory release (no network)."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
DEPLOY=ROOT/"deploy/ege-lab-keyboard-guarded-release.sh"
BOOTSTRAP=ROOT/"deploy/bootstrap-ege-lab-keyboard-release.sh"
UPDATER=ROOT/"deploy/refresh-ege-lab-keyboard-mncr-guard.sh"
ENTRY=ROOT/"deploy/ege-lab-restricted-ssh-entry-v2.sh"
OLD=ROOT/"deploy/ege-lab-mncr-approved-release.sh"
WORKFLOW=ROOT/".github/workflows/ege-lab-keyboard-release.yml"
OLD_SHA="23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e"
NEW_SHA="cd4431d87d07edc17a31a1b2ff93752cab813064339654ec9a972738c1941a16"
PIN="fabf5fba43806cf8acc19e728f422096d17c1177"


class KeyboardGuardTests(unittest.TestCase):
    def test_bash_syntax_and_immutable_pins(self):
        for script in (DEPLOY,BOOTSTRAP,UPDATER,ENTRY,OLD):
            proc=subprocess.run(["bash","-n",str(script)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
        s=DEPLOY.read_text()
        self.assertIn("OLD_SHA256="+OLD_SHA,s)
        self.assertIn("NEW_SHA256="+NEW_SHA,s)
        self.assertIn("SOURCE_COMMIT="+PIN,s)
        self.assertIn("SOURCE_BLOB=7c0ce9916118898c959f49e81d7537ef142a5a81",s)
        self.assertIn('git hash-object "$TMP/ege_lab_webapp.py"',s)
        self.assertIn('[[ $(sha "$APP/ege_lab_webapp.py") == "$OLD_SHA256" ]]',s)
        self.assertIn('[[ $(sha "$APP/ege_lab_webapp.py") == "$NEW_SHA256" ]]',s)

    def test_lab_only_and_live_customizations(self):
        s=DEPLOY.read_text()
        self.assertIn("ege_lab_webapp.py ege_lab_substances.py ege_lab_inorganic_reactions.py public_channel_trainers.py run_bot_live7.py run_bot_production.py",s)
        self.assertIn('EXPECTED_CHANGED=', s)
        self.assertIn('[[ "$CHANGED" == "$EXPECTED_CHANGED" ]]',s)
        self.assertIn('[[ "$(git hash-object "$APP/$name")" == "$blob" ]]',s)
        self.assertIn("ege_lab_substances.py 3581b6d0d9b7cc3500f1075b2a1ea9b88db4f4aa",s)
        self.assertIn("ege_lab_inorganic_reactions.py 0910dbbeca374485944a2782dc43932cc84053a3",s)
        self.assertIn("ege_lab_mn_cr_pdf_import.py 02ee81298850aa3bb534ca7f5200d755f4c9ddbf",s)
        self.assertIn("public_channel_trainers.py run_bot_live7.py run_bot_production.py ege_lab_substances.py ege_lab_inorganic_reactions.py ege_lab_mn_cr_pdf_import.py",s)
        self.assertIn('sha256sum -c "$BACKUP/protected-files.sha256"',s)
        self.assertIn('mv -Tf "$INSTALLED" "$APP/ege_lab_webapp.py"',s)
        self.assertNotIn("git reset",s)
        self.assertNotIn("git checkout",s)
        self.assertNotIn("rm -rf $APP",s)
        self.assertIn('BACKUP=$(mktemp -d',s)
        self.assertIn('with sqlite3.connect',s)
        self.assertIn('src.backup(output)' if 'src.backup(output)' in s else 'con.backup(output)',s)
        self.assertIn("trap rollback ERR",s)
        self.assertIn("LAB_KEYBOARD_RELEASE_SUCCESS",s)

    def test_root_guard_updater_cannot_install_unreviewed_code(self):
        updater=UPDATER.read_text()
        self.assertIn('NEW_BLOB=509613762419239eb592b764a602942bb97e8870',updater)
        self.assertIn('OLD_BLOB=ddc8dfe94426708563bf752e34de6beb041b56f8',updater)
        self.assertIn('git hash-object "$TEMP"',updater)
        self.assertIn('bash -n "$TEMP"',updater)
        self.assertIn('cp -p -- "$FILE" "$BACKUP"',updater)
        self.assertIn('WORKING_BOT_UNTOUCHED',updater)
        self.assertNotIn('systemctl restart',updater)
        self.assertNotIn('git reset',updater)

    def test_forced_command_sudo_scopes_and_replay_protection(self):
        e=ENTRY.read_text()
        b=BOOTSTRAP.read_text()
        old=OLD.read_text()
        for target in ("release-ege-lab-mncr","release-ege-lab-keyboard"):
            self.assertIn(target,e)
        self.assertIn("DEPLOY_SSH_DENIED",e)
        self.assertIn("EGE-LAB-KEYBOARD-20261022-CHECKED",e)
        self.assertIn("NOPASSWD: /usr/local/sbin/ege-lab-keyboard-guarded-release.sh EGE-LAB-KEYBOARD-20261022-CHECKED",b)
        self.assertIn("visudo -cf",b)
        self.assertIn("NO_APPLICATION_DEPLOYED",b)
        self.assertNotIn('systemctl restart',b)
        self.assertIn("Old Mn/Cr release is obsolete after a later lab update",old)

    def test_owner_review_gate_and_no_regular_push_deploy(self):
        w=WORKFLOW.read_text()
        self.assertIn("environment: production-lab",w)
        self.assertIn("deploy/release-intents/ege-lab-keyboard-2.txt",w)
        self.assertNotIn("deploy/release-intents/ege-lab-keyboard-1.txt",w)
        self.assertIn("branches: [main]",w)
        self.assertIn("github.actor == 'mariyasedova08-beep'",w)
        self.assertIn('test "$changed" = "$file"',w)
        self.assertIn('release-ege-lab-keyboard',w)
        self.assertIn('StrictHostKeyChecking=yes',w)
        self.assertNotIn("root@77.233.212.200",w)
        self.assertNotIn("workflow_dispatch:",w)

if __name__=="__main__":
    unittest.main()
