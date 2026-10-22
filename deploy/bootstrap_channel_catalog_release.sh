#!/bin/bash
# One-time root setup: installs only a fixed helper; does not patch/restart the bot.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]]
[[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]
id ege-deploy >/dev/null
systemctl is-active --quiet ege-blizko
setup_dir=$(mktemp -d /root/ege-channel-catalog-setup.XXXXXX)
trap 'rm -rf "$setup_dir"' EXIT
curl -fsSL --max-time 30 "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$1/deploy/channel_catalog_bridge_patch.py" -o "$setup_dir/helper"
printf '%s  %s\n' 'a98bb58d29b9c32615eac3f53c4e4a103eefae503f15cd17e2ce7e0f2c70f113' "$setup_dir/helper" | sha256sum -c -
helper=/usr/local/sbin/ege-channel-catalog-release
rule=/etc/sudoers.d/ege-channel-catalog-release
cat > "$setup_dir/rule" <<'RULE'
ege-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-channel-catalog-release EGE-CHANNEL-CATALOG-20261022-REVIEWED, /usr/local/sbin/ege-channel-catalog-release EGE-CHANNEL-CATALOG-20261022-REVIEWED-ROLLBACK
RULE
visudo -cf "$setup_dir/rule" >/dev/null
if [[ -e "$helper" || -L "$helper" ]]; then
  [[ -f "$helper" && ! -L "$helper" ]]
  cmp -s "$helper" "$setup_dir/helper"
fi
if [[ -e "$rule" || -L "$rule" ]]; then
  [[ -f "$rule" && ! -L "$rule" ]]
  cmp -s "$rule" "$setup_dir/rule"
fi
install -o root -g root -m 0750 "$setup_dir/helper" "$helper"
install -o root -g root -m 0440 "$setup_dir/rule" "$rule"
visudo -c >/dev/null
printf '%s\n' 'CHANNEL_CATALOG_FIXED_PERMISSION_READY_BOT_NOT_CHANGED'
