#!/bin/bash
# One-time root setup: installs only a fixed helper; does not patch/restart the bot.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]]
[[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]
id ege-deploy >/dev/null
systemctl is-active --quiet ege-blizko
setup_dir=$(mktemp -d /root/ege-november-theme-setup.XXXXXX)
trap 'rm -rf "$setup_dir"' EXIT
curl -fsSL --max-time 30 "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$1/deploy/install_november_theme.py" -o "$setup_dir/helper"
printf '%s  %s\n' '93c617a0d40ff98c2c8d5d6887b4b8ccb8988db7ecc82bb40c4441fea1f92edb' "$setup_dir/helper" | sha256sum -c -
helper=/usr/local/sbin/ege-november-theme-release
rule=/etc/sudoers.d/ege-november-theme-release
cat > "$setup_dir/rule" <<'RULE'
ege-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-november-theme-release EGE-NOVEMBER-THEME-20261101-REVIEWED, /usr/local/sbin/ege-november-theme-release EGE-NOVEMBER-THEME-20261101-REVIEWED-ROLLBACK
RULE
visudo -cf "$setup_dir/rule" >/dev/null
if [[ -e "$helper" || -L "$helper" ]]; then
  [[ -f "$helper" && ! -L "$helper" ]]
  [[ "$(stat -c %u "$helper")" == 0 ]]
  current_helper_sha=$(sha256sum "$helper")
  current_helper_sha=${current_helper_sha%% *}
  case "$current_helper_sha" in
    93c617a0d40ff98c2c8d5d6887b4b8ccb8988db7ecc82bb40c4441fea1f92edb) ;;
    *) printf '%s\n' 'UNREVIEWED_NOVEMBER_HELPER'; exit 1 ;;
  esac
fi
if [[ -e "$rule" || -L "$rule" ]]; then
  [[ -f "$rule" && ! -L "$rule" ]]
  cmp -s "$rule" "$setup_dir/rule"
fi
install -o root -g root -m 0750 "$setup_dir/helper" "$helper"
install -o root -g root -m 0440 "$setup_dir/rule" "$rule"
visudo -c >/dev/null
printf '%s\n' 'NOVEMBER_THEME_PERMISSION_READY_BOT_NOT_CHANGED'
