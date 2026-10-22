#!/usr/bin/env bash
# One-time root-console setup: fixed helper + two literal sudo commands only.
# Does NOT install trainer files, open databases or restart the bot.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 && "$#" == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || {
  echo SETUP_REQUIRES_ROOT_AND_EXACT_COMMIT >&2; exit 1;
}
pin="$1"
expected=9a1740378fcb942f45c7e44b99eeda17d7b3ff5a6027eafa3db7dbcbde0adc3b
target=/usr/local/sbin/ege-decomposition-release
rule=/etc/sudoers.d/ege-decomposition-release
id ege-deploy >/dev/null
[[ "$(systemctl is-active ege-blizko)" == active ]]
[[ ! -L "$target" && ! -L "$rule" ]]
setup_dir="$(mktemp -d /root/ege-decomposition-setup.XXXXXXXX)"
trap 'rm -rf "$setup_dir"' EXIT
curl --fail --silent --show-error --location --max-time 30 \
  "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$pin/deploy/install_decomposition_release.py" \
  -o "$setup_dir/installer.py"
printf '%s  %s\n' "$expected" "$setup_dir/installer.py" | sha256sum --check --status
python3 -m py_compile "$setup_dir/installer.py"
python3 -c 'import sqlite3,fcntl,urllib.request'
printf '%s\n' \
  'ege-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-decomposition-release EGE-DECOMPOSITION-20261022-REVIEWED, /usr/local/sbin/ege-decomposition-release EGE-DECOMPOSITION-20261022-REVIEWED-ROLLBACK' \
  > "$setup_dir/sudoers"
visudo -cf "$setup_dir/sudoers" >/dev/null
if [[ -e "$target" ]]; then
  printf '%s  %s\n' "$expected" "$target" | sha256sum --check --status
fi
if [[ -e "$rule" ]]; then
  cmp --silent "$setup_dir/sudoers" "$rule"
fi
install -o root -g root -m 0750 "$setup_dir/installer.py" "$target"
install -o root -g root -m 0440 "$setup_dir/sudoers" "$rule"
visudo -cf /etc/sudoers >/dev/null
echo DECOMPOSITION_FIXED_RELEASE_PERMISSION_READY
echo TRAINER_NOT_INSTALLED_SERVICE_NOT_RESTARTED
