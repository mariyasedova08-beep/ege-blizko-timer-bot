#!/usr/bin/env bash
# One-time setup: read a SINGLE dedicated SSH PUBLIC key via standard input.
# Appends it with a forced PREPODMIN-only command; never accepts private keys.
set -euo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "Must be run by root" >&2; exit 1; }
[[ -x /usr/local/sbin/prepodmin-ssh-gate ]] || {
  echo "Run install_deploy_access.sh first" >&2; exit 1;
}
IFS= read -r KEY || { echo "Missing SSH public key" >&2; exit 1; }
[[ "${#KEY}" -le 1024 ]] || { echo "Public key too long" >&2; exit 1; }
[[ "$KEY" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [A-Za-z0-9@._-]+)?$ ]] || {
  echo "Expected a single ed25519 PUBLIC key line, not a private key" >&2
  exit 1
}
KEY_FILE=/home/prepodmin-deploy/.ssh/authorized_keys
[[ -f "$KEY_FILE" && ! -L "$KEY_FILE" ]] || exit 1
if [[ -s "$KEY_FILE" ]]; then
  echo "A deployment key is already installed. Refusing to append automatically." >&2
  exit 1
fi
printf 'restrict,command="/usr/local/sbin/prepodmin-ssh-gate" %s\n' "$KEY" > "$KEY_FILE"
chown prepodmin-deploy:prepodmin-deploy "$KEY_FILE"
chmod 0600 "$KEY_FILE"
echo PREPODMIN_RESTRICTED_PUBLIC_KEY_INSTALLED
