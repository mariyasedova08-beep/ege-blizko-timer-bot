#!/usr/bin/env bash
# One-time MINIMAL bootstrap, launched manually from Timeweb's ROOT serial console.
# It creates ONLY the locked ege-lab-deploy account, forced SSH key, root-owned
# pinned release scripts, and its one-command sudo permission.
# It neither edits /opt/bots nor restarts/stops any service.
set -Eeuo pipefail
umask 077

[[ "$(id -u)" == 0 ]] || { echo "BOOTSTRAP_ABORTED: root console required" >&2; exit 1; }
PIN="${1:-}"
[[ "$PIN" =~ ^[0-9a-f]{40}$ ]] || { echo "BOOTSTRAP_ABORTED: pass exact trusted 40-hex GitHub commit" >&2; exit 1; }
USER=ege-lab-deploy
ACCOUNT_HOME=/home/ege-lab-deploy
REPO_URL="https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$PIN"
for cmd in curl sudo visudo ssh-keygen useradd passwd install chown chmod systemctl git; do
  command -v "$cmd" >/dev/null || { echo "BOOTSTRAP_ABORTED: missing $cmd" >&2; exit 1; }
done
id "$USER" >/dev/null 2>&1 && { echo "BOOTSTRAP_ABORTED: account already exists" >&2; exit 1; }
[[ ! -e /etc/sudoers.d/ege-lab-deploy ]] || { echo "BOOTSTRAP_ABORTED: sudoers already exists" >&2; exit 1; }
[[ ! -e /usr/local/sbin/ege-lab-mncr-approved-release.sh ]] || { echo "BOOTSTRAP_ABORTED: release script already exists" >&2; exit 1; }
[[ ! -e /usr/local/libexec/ege-lab-release-entry ]] || { echo "BOOTSTRAP_ABORTED: forced command already exists" >&2; exit 1; }
[[ "$(systemctl is-active ege-blizko)" == "active" ]] || { echo "BOOTSTRAP_ABORTED: bot not active" >&2; exit 1; }

TMP="$(mktemp -d /root/ege-lab-setup.XXXXXXXX)"
trap 'rm -rf "$TMP"' EXIT
curl --fail --silent --show-error --location --max-time 30 \
  "$REPO_URL/deploy/ege-lab-mncr-approved-release.sh" -o "$TMP/release.sh"
curl --fail --silent --show-error --location --max-time 30 \
  "$REPO_URL/deploy/ege-lab-restricted-ssh-entry.sh" -o "$TMP/entry.sh"
bash -n "$TMP/release.sh"
bash -n "$TMP/entry.sh"
grep -Fq 'EXPECTED_FILE=23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e' "$TMP/release.sh" || {
 echo "BOOTSTRAP_ABORTED: wrong lab package" >&2; exit 1;
}
grep -Fq 'exec sudo -n /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED' "$TMP/entry.sh" || {
 echo "BOOTSTRAP_ABORTED: SSH entry is not pinned" >&2; exit 1;
}

echo
echo "Copy the public key from PuTTYgen's top text box:"
echo "Public key for pasting into OpenSSH authorized_keys file."
echo "It starts with ssh-ed25519. NEVER paste a private key here."
IFS= read -r -p "Paste PUBLIC SSH key then press Enter: " PUBKEY
[[ "$PUBKEY" =~ ^ssh-ed25519[[:space:]]+([A-Za-z0-9+/]+={0,3})([[:space:]]+[^[:cntrl:]]+)?$ ]] || {
 echo "BOOTSTRAP_ABORTED: expected one ssh-ed25519 PUBLIC key" >&2; exit 1;
}
printf '%s\n' "$PUBKEY" > "$TMP/public_key"
ssh-keygen -lf "$TMP/public_key" >/dev/null || {
 echo "BOOTSTRAP_ABORTED: invalid public SSH key" >&2; exit 1;
}

# All validation finished: now create the limited, password-locked account.
useradd --create-home --user-group --shell /bin/bash "$USER"
passwd -l "$USER" >/dev/null
install -d -m 0700 -o "$USER" -g "$USER" "$ACCOUNT_HOME/.ssh"
printf 'command="/usr/local/libexec/ege-lab-release-entry",restrict %s\n' "$PUBKEY" \
  > "$ACCOUNT_HOME/.ssh/authorized_keys"
chown "$USER:$USER" "$ACCOUNT_HOME/.ssh/authorized_keys"
chmod 0600 "$ACCOUNT_HOME/.ssh/authorized_keys"

install -d -m 0755 /usr/local/libexec
install -m 0755 -o root -g root "$TMP/entry.sh" /usr/local/libexec/ege-lab-release-entry
install -m 0700 -o root -g root "$TMP/release.sh" /usr/local/sbin/ege-lab-mncr-approved-release.sh
printf '%s\n' \
  'ege-lab-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-lab-mncr-approved-release.sh EGE-LAB-MNCR-20261021-CHECKED' \
  > /etc/sudoers.d/ege-lab-deploy
chmod 0440 /etc/sudoers.d/ege-lab-deploy
visudo -cf /etc/sudoers.d/ege-lab-deploy >/dev/null
echo "RESTRICTED_DEPLOY_ACCOUNT_OK"
echo "ROOT_OWNED_DEPLOY_SCRIPT_OK"
echo "FORCED_SSH_COMMAND_OK"
echo "BOT_STILL_$(systemctl is-active ege-blizko)"
echo "PRODUCTION_APPLICATION_UNTOUCHED"
echo "DO_NOT_RUN_RELEASE_YET"
