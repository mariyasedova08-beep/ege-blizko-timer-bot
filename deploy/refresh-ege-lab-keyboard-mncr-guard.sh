#!/usr/bin/env bash
# One-time, no-deployment replacement of ONLY the root-owned keyboard guard.
# Use in Timeweb serial console with an immutable reviewed GitHub commit SHA.
set -Eeuo pipefail
umask 077
fail(){ echo "KEYBOARD_GUARD_UPDATE_ABORTED: $*" >&2; exit 1; }
[[ $(id -u) == 0 ]] || fail "Root serial console required"
[[ $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || fail "Immutable GitHub commit SHA required"
REV="$1"
APP=/opt/bots/ege-blizko
FILE=/usr/local/sbin/ege-lab-keyboard-guarded-release.sh
OLD_BLOB=ddc8dfe94426708563bf752e34de6beb041b56f8
NEW_BLOB=509613762419239eb592b764a602942bb97e8870
[[ -f "$FILE" && ! -L "$FILE" ]] || fail "Existing guarded release missing"
[[ $(git hash-object "$FILE") == "$OLD_BLOB" ]] || fail "Existing installed guard differs from approved baseline"
[[ $(systemctl is-active ege-blizko) == active ]] || fail "Bot not running"
[[ $(git -C "$APP" rev-parse HEAD) == d95b80eb423a6295eac080f66d1707ac1e92e789 ]] || fail "Unexpected app git revision"
[[ -f /usr/local/libexec/ege-lab-release-entry && -f /etc/sudoers.d/ege-lab-deploy ]] || fail "Restricted SSH account changed"
grep -Fq 'release-ege-lab-keyboard' /usr/local/libexec/ege-lab-release-entry || fail "Keyboard forced command missing"
grep -Fq 'ege-lab-keyboard-guarded-release.sh EGE-LAB-KEYBOARD-20261022-CHECKED' /etc/sudoers.d/ege-lab-deploy || fail "Keyboard sudo command missing"

TEMP="$(mktemp /root/ege-keyboard-fixed-XXXXXXXX)"
trap 'rm -f -- "$TEMP"' EXIT
curl --fail --silent --show-error --location --max-time 35 \
  "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$REV/deploy/ege-lab-keyboard-guarded-release.sh" -o "$TEMP"
[[ $(git hash-object "$TEMP") == "$NEW_BLOB" ]] || fail "Downloaded candidate does not match the vetted Git blob"
bash -n "$TEMP"
grep -Fq 'ege_lab_substances.py 3581b6d0d9b7cc3500f1075b2a1ea9b88db4f4aa' "$TEMP" || fail "MnCr substance hash guard missing"
grep -Fq 'ege_lab_inorganic_reactions.py 0910dbbeca374485944a2782dc43932cc84053a3' "$TEMP" || fail "MnCr reactions hash guard missing"
grep -Fq 'ege_lab_mn_cr_pdf_import.py 02ee81298850aa3bb534ca7f5200d755f4c9ddbf' "$TEMP" || fail "MnCr imported file hash guard missing"
grep -Fq 'OLD_SHA256=23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e' "$TEMP" || fail "Wrong old UI pin"
grep -Fq 'NEW_SHA256=cd4431d87d07edc17a31a1b2ff93752cab813064339654ec9a972738c1941a16' "$TEMP" || fail "Wrong candidate UI pin"
BACKUP="$FILE.before-mncr-guard-fix-20261022"
[[ ! -e "$BACKUP" ]] || fail "Backup already present — refuse repeated setup"
cp -p -- "$FILE" "$BACKUP"
install -m 0700 -o root -g root "$TEMP" "$FILE"
if ! cmp -s "$TEMP" "$FILE" || ! bash -n "$FILE";then
  cp -p -- "$BACKUP" "$FILE"
  fail "Install check failed and original restored"
fi
[[ $(systemctl is-active ege-blizko) == active ]] || fail "Bot status changed"
echo "KEYBOARD_MNCR_HASH_GUARD_READY"
echo "WORKING_BOT_UNTOUCHED"
echo "NO_DEPLOYMENT_PERFORMED"
