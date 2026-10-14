#!/usr/bin/env bash
# ONE-TIME bootstrap run via trusted root SSH on Timeweb.
# This sets up ONLY an unprivileged PREPODMIN deployment identity.
# No keys/secrets are generated, no existing bot is restarted.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
SRC=/opt/bots/prepodmin/current/deployment/prepodmin
RUNNER=/usr/local/sbin/prepodmin-release
GATE=/usr/local/sbin/prepodmin-ssh-gate
USER=prepodmin-deploy
SUDO_FILE=/etc/sudoers.d/prepodmin-deploy
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
[[ -f "$SRC/prepodmin_release_runner.sh" && -f "$SRC/prepodmin_ssh_gate.sh" ]]
[[ ! -e "$RUNNER" && ! -e "$GATE" && ! -e "$SUDO_FILE" ]] || {
  echo "PREPODMIN_DEPLOY_BOOTSTRAP_EXISTS; inspect manually before modifications" >&2
  exit 1
}
if ! id "$USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$USER"
  passwd -l "$USER" >/dev/null
fi
install -d -o root -g root -m 0755 /usr/local/sbin
install -o root -g root -m 0750 "$SRC/prepodmin_release_runner.sh" "$RUNNER"
install -o root -g root -m 0755 "$SRC/prepodmin_ssh_gate.sh" "$GATE"
install -d -o "$USER" -g "$USER" -m 0700 "/home/$USER/.ssh"
if [[ ! -e "/home/$USER/.ssh/authorized_keys" ]]; then
  install -o "$USER" -g "$USER" -m 0600 /dev/null "/home/$USER/.ssh/authorized_keys"
fi
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
printf '%s\n' "prepodmin-deploy ALL=(root) NOPASSWD: /usr/local/sbin/prepodmin-release *" > "$TMP"
chmod 0440 "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" "$SUDO_FILE"
visudo -cf /etc/sudoers >/dev/null
echo PREPODMIN_DEPLOY_ACCESS_PREPARED
echo SSH_KEY_STILL_REQUIRED=yes
echo GITHUB_ENV_SECRETS_STILL_REQUIRED=yes
echo NO_BOT_RESTART
