#!/usr/bin/env bash
# Run once from the Timeweb ROOT serial console, using an IMMUTABLE GitHub commit.
# This only adds a 2nd forced SSH command; it DOES NOT deploy or restart the bot.
set -Eeuo pipefail
umask 077
fail(){ echo "KEYBOARD_ACCESS_SETUP_ABORTED: $*" >&2; exit 1; }
[[ $(id -u) == 0 ]] || fail "Root serial console required"
[[ $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || fail "Provide immutable 40-digit commit SHA"
REV="$1"
URL="https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$REV"
APP=/opt/bots/ege-blizko
ENTRY=/usr/local/libexec/ege-lab-release-entry
OLD=/usr/local/sbin/ege-lab-mncr-approved-release.sh
NEW=/usr/local/sbin/ege-lab-keyboard-guarded-release.sh
SUDOERS=/etc/sudoers.d/ege-lab-deploy
[[ -f "$ENTRY" && -f "$OLD" && -f "$SUDOERS" ]] || fail "Existing restricted SSH configuration missing"
[[ ! -e "$NEW" ]] || fail "Keyboard release command already installed"
[[ $(systemctl is-active ege-blizko) == active ]] || fail "Bot not active"
[[ $(git -C "$APP" rev-parse HEAD) == d95b80eb423a6295eac080f66d1707ac1e92e789 ]] || fail "Production version changed"
[[ $(sha256sum "$APP/ege_lab_webapp.py" | cut -d' ' -f1) == 23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e ]] || fail "Published Mn/Cr UI changed"
grep -Fqx 'LIVE_ONLY_FILES=(public_channel_trainers.py run_bot_live7.py run_bot_production.py)' "$OLD" || fail "Unexpected existing MnCr script"
grep -Fqx 'ege-lab-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED' "$SUDOERS" || fail "Existing sudoer grant missing"
[[ $(grep -cv '^[[:space:]]*$' "$SUDOERS") == 1 ]] || fail "Sudo file contains unexpected extra lines"

TMP=$(mktemp -d /root/ege-lab-keyboard-access-XXXXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
curl --fail --silent --show-error --location --max-time 35 "$URL/deploy/ege-lab-keyboard-guarded-release.sh" -o "$TMP/release"
curl --fail --silent --show-error --location --max-time 35 "$URL/deploy/ege-lab-restricted-ssh-entry-v2.sh" -o "$TMP/entry"
curl --fail --silent --show-error --location --max-time 35 "$URL/deploy/ege-lab-mncr-approved-release.sh" -o "$TMP/old"
for part in "$TMP/release" "$TMP/entry" "$TMP/old";do bash -n "$part";done
grep -Fq 'NEW_SHA256=cd4431d87d07edc17a31a1b2ff93752cab813064339654ec9a972738c1941a16' "$TMP/release" || fail "Keyboard release not pinned"
grep -Fq 'SOURCE_COMMIT=fabf5fba43806cf8acc19e728f422096d17c1177' "$TMP/release" || fail "Wrong source commit"
grep -Fq 'OLD_SHA256=23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e' "$TMP/release" || fail "Wrong old UI checksum"
grep -Fq 'LAB_KEYBOARD_RELEASE_SUCCESS:' "$TMP/release" || fail "No postrelease confirmation"
grep -Fq '"release-ege-lab-keyboard")' "$TMP/entry" || fail "Missing keyboard forced entry"
grep -Fq '"release-ege-lab-mncr")' "$TMP/entry" || fail "Missing original forced entry"
grep -Fq 'Old Mn/Cr release is obsolete' "$TMP/old" || fail "Old command not replay-safe"

# Save three configuration files, validate the new sudoers BEFORE modifying server.
SAVE=$(mktemp -d /root/ege-lab-keyboard-config-backup-XXXXXXXX)
cp -p -- "$ENTRY" "$SAVE/entry"
cp -p -- "$OLD" "$SAVE/mncr"
cp -p -- "$SUDOERS" "$SAVE/sudoers"
cp -p -- "$SUDOERS" "$TMP/new-sudoers"
printf '%s\n' 'ege-lab-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-lab-keyboard-guarded-release.sh EGE-LAB-KEYBOARD-20261022-CHECKED' >> "$TMP/new-sudoers"
chmod 0440 "$TMP/new-sudoers"
visudo -cf "$TMP/new-sudoers" >/dev/null || fail "Invalid restricted sudoer configuration"
STARTED=0
revert(){
 code=$?
 trap - ERR INT TERM HUP
 if [[ "$STARTED" == 1 ]];then
   cp -p -- "$SAVE/entry" "$ENTRY" || true
   cp -p -- "$SAVE/mncr" "$OLD" || true
   cp -p -- "$SAVE/sudoers" "$SUDOERS" || true
   rm -f -- "$NEW"
 fi
 echo "KEYBOARD_ACCESS_SETUP_FAILED: $code; backup=$SAVE" >&2
 exit "$code"
}
trap revert ERR
trap 'false' INT TERM HUP
STARTED=1
install -m 0700 -o root -g root "$TMP/release" "$NEW"
install -m 0755 -o root -g root "$TMP/entry" "$ENTRY"
install -m 0700 -o root -g root "$TMP/old" "$OLD"
install -m 0440 -o root -g root "$TMP/new-sudoers" "$SUDOERS"
visudo -cf "$SUDOERS" >/dev/null
bash -n "$NEW";bash -n "$OLD";bash -n "$ENTRY"
[[ $(systemctl is-active ege-blizko) == active ]] || false
[[ $(sha256sum "$APP/ege_lab_webapp.py" | cut -d' ' -f1) == 23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e ]] || false
trap - ERR INT TERM HUP
STARTED=0
echo "KEYBOARD_RESTRICTED_COMMAND_INSTALLED"
echo "PRIOR_MNCR_REPLAY_PROTECTED"
echo "BOT_STILL_ACTIVE"
echo "NO_APPLICATION_DEPLOYED"
echo "DO_NOT_RUN_RELEASE_YET"
