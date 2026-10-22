#!/usr/bin/env bash
# EGE BLIZKO: guarded update of ONLY the lesson UI with typed reagent search.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1 GIT_OPTIONAL_LOCKS=0
APP=/opt/bots/ege-blizko
SERVICE=ege-blizko
TIMER=ege-blizko-autodeploy.timer
LOCK=/run/lock/ege-blizko-autodeploy.lock
HEALTH=https://77-233-212-200.sslip.io/health
BACKUPS=/root/ege-blizko-backups
LIVE_HEAD=d95b80eb423a6295eac080f66d1707ac1e92e789
OLD_SHA256=23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e
NEW_SHA256=cd4431d87d07edc17a31a1b2ff93752cab813064339654ec9a972738c1941a16
SOURCE_COMMIT=fabf5fba43806cf8acc19e728f422096d17c1177
SOURCE_BLOB=7c0ce9916118898c959f49e81d7537ef142a5a81
RELEASE_ID=EGE-LAB-KEYBOARD-20261022-CHECKED
URL="https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$SOURCE_COMMIT/ege_lab_webapp.py"
fail(){ echo "KEYBOARD_RELEASE_ABORTED: $*" >&2; exit 1; }
sha(){ sha256sum "$1" | cut -d' ' -f1; }
[[ $# == 1 && "$1" == "$RELEASE_ID" ]] || fail "Wrong release ID"
[[ $(id -u) == 0 ]] || fail "Root-only restricted sudo target"
[[ -f /usr/local/libexec/ege-lab-release-entry && -f /etc/sudoers.d/ege-lab-deploy ]] || fail "Missing SSH guard"
[[ -d "$APP/.git" ]] || fail "App missing"
[[ $(git -C "$APP" rev-parse HEAD) == "$LIVE_HEAD" ]] || fail "Live git revision changed"
[[ $(systemctl is-active "$SERVICE") == active ]] || fail "Bot stopped"
[[ $(systemctl is-active "$TIMER") == active ]] || fail "Autodeploy timer changed"

exec 9>"$LOCK"
flock -w 30 9 || fail "Autodeploy lock busy"
[[ $(git -C "$APP" rev-parse HEAD) == "$LIVE_HEAD" ]] || fail "Live git changed during lock"
CHANGED="$(git -C "$APP" diff HEAD --name-only | LC_ALL=C sort)"
EXPECTED_CHANGED="$(printf '%s\n' ege_lab_webapp.py public_channel_trainers.py run_bot_live7.py run_bot_production.py | LC_ALL=C sort)"
[[ "$CHANGED" == "$EXPECTED_CHANGED" ]] || fail "Unrecognized live modifications"
MARKER=$(cat /var/lib/ege-blizko-autodeploy/release.ref 2>/dev/null || true)
[[ "$MARKER" == release-20261009-task6-full-trainer-v3-fix1 ]] || fail "Legacy release marker changed"
[[ -f "$APP/ege_lab_webapp.py" && ! -L "$APP/ege_lab_webapp.py" ]] || fail "Lab UI missing or symlink"
[[ $(sha "$APP/ege_lab_webapp.py") == "$OLD_SHA256" ]] || fail "Expected released Mn/Cr UI not present"
curl --fail --silent --show-error --max-time 10 "$HEALTH" >/dev/null || fail "Live health check failed"

TMP=$(mktemp -d /root/ege-lab-keyboard-candidate.XXXXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
curl --fail --silent --show-error --location --max-time 40 "$URL" -o "$TMP/ege_lab_webapp.py"
[[ $(git hash-object "$TMP/ege_lab_webapp.py") == "$SOURCE_BLOB" ]] || fail "Candidate git blob mismatch"
[[ $(sha "$TMP/ege_lab_webapp.py") == "$NEW_SHA256" ]] || fail "Candidate SHA256 mismatch"
python3 - "$TMP/ege_lab_webapp.py" <<'PY'
import ast,sys
from pathlib import Path
s=Path(sys.argv[1]).read_text(encoding="utf-8")
ast.parse(s)
for sign in ('id="lessonReagentA" type="search"',
             'id="lessonReagentB" type="search"',
             'id="lessonSuggestionsA"','id="lessonSuggestionsB"',
             'function lessonSearchMatches(raw)',
             'function lessonSetReagent(slot,id)',
             'function lessonExportPDF()',
             'id="lessonPDFInput"','id="lessonMedium"'):
    assert sign in s, sign
assert '<select id="lessonReagentA"' not in s
print("KEYBOARD_CANDIDATE_VALIDATED")
PY

mkdir -p -m 0700 "$BACKUPS"
BACKUP=$(mktemp -d "$BACKUPS/lab-keyboard-XXXXXXXX")
mkdir -m 0700 "$BACKUP/code" "$BACKUP/data" "$BACKUP/protected-code" "$BACKUP/service"
cp -p -- "$APP/ege_lab_webapp.py" "$BACKUP/code/ege_lab_webapp.py"
for name in public_channel_trainers.py run_bot_live7.py run_bot_production.py ege_lab_substances.py ege_lab_inorganic_reactions.py ege_lab_mn_cr_pdf_import.py;do
 [[ -f "$APP/$name" && ! -L "$APP/$name" ]] || fail "Protected file missing: $name"
 cp -p -- "$APP/$name" "$BACKUP/protected-code/$name"
 sha256sum "$APP/$name" >> "$BACKUP/protected-files.sha256"
done
cp -p -- /etc/systemd/system/ege-blizko.service "$BACKUP/service/ege-blizko.service"
if [[ -f /etc/systemd/system/ege-blizko.service.d/70-ege-bot.conf ]];then
 cp -p -- /etc/systemd/system/ege-blizko.service.d/70-ege-bot.conf "$BACKUP/service/70-ege-bot.conf"
fi
APP="$APP" BACKUP="$BACKUP" python3 - <<'PY'
import os,sqlite3
from pathlib import Path
src=Path(os.environ["APP"])/"data"
dst=Path(os.environ["BACKUP"])/"data"
dbs=sorted(src.glob("*.db"))
assert dbs,"No SQLite databases to back up"
for db in dbs:
    with sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=30) as con:
        with sqlite3.connect(dst/db.name) as output:
            con.backup(output)
            assert output.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
print("KEYBOARD_DATABASE_BACKUP_OK")
PY
[[ $(sha "$BACKUP/code/ege_lab_webapp.py") == "$OLD_SHA256" ]] || fail "UI backup checksum mismatch"
echo "KEYBOARD_PRE_DEPLOY_BACKUP_OK: $BACKUP"
STARTED=0
rollback(){
 local result=$?
 trap - ERR INT TERM HUP
 if [[ "$STARTED" == 1 ]];then
   echo "KEYBOARD_ROLLBACK_STARTED: $BACKUP" >&2
   cp -p -- "$BACKUP/code/ege_lab_webapp.py" "$APP/ege_lab_webapp.py" || true
   systemctl restart "$SERVICE" || true
   curl --fail --silent --max-time 10 "$HEALTH" >/dev/null 2>&1 || true
 fi
 echo "KEYBOARD_RELEASE_FAILED: exit=$result backup=$BACKUP" >&2
 exit "$result"
}
trap rollback ERR
trap 'false' INT TERM HUP
OWNER=$(stat -c '%u' "$APP/ege_lab_webapp.py")
GROUP=$(stat -c '%g' "$APP/ege_lab_webapp.py")
INSTALLED=$(mktemp "$APP/.ege_lab_webapp.py.XXXXXXXX")
install -m 0644 -o "$OWNER" -g "$GROUP" "$TMP/ege_lab_webapp.py" "$INSTALLED"
STARTED=1
mv -Tf "$INSTALLED" "$APP/ege_lab_webapp.py"
systemctl restart "$SERVICE"
ready=0
for n in $(seq 1 15);do
 if [[ $(systemctl is-active "$SERVICE") == active ]] && curl --fail --silent --max-time 5 "$HEALTH" >/dev/null 2>&1;then ready=1;break;fi
 sleep 2
done
[[ "$ready" == 1 ]] || false
[[ $(sha "$APP/ege_lab_webapp.py") == "$NEW_SHA256" ]] || false
(cd "$APP"; sha256sum -c "$BACKUP/protected-files.sha256" >/dev/null)
[[ $(git -C "$APP" rev-parse HEAD) == "$LIVE_HEAD" ]] || false
[[ $(cat /var/lib/ege-blizko-autodeploy/release.ref) == "$MARKER" ]] || false
trap - ERR INT TERM HUP
STARTED=0
echo "LAB_KEYBOARD_RELEASE_SUCCESS: $RELEASE_ID"
echo "LAB_KEYBOARD_ROLLBACK_BUNDLE: $BACKUP"
echo "LIVE_TRAINERS_AND_MNCR_UNCHANGED"
