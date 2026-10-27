#!/bin/bash
# One-time root setup: installs only a fixed helper; does not patch/restart the bot.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]]
[[ "${1:-}" =~ ^[0-9a-f]{40}$ ]]
id ege-deploy >/dev/null
systemctl is-active --quiet ege-blizko
setup_dir=$(mktemp -d /root/ege-cabinet-snapshot-setup.XXXXXX)
trap 'rm -rf "$setup_dir"' EXIT
curl -fsSL --max-time 30 "https://raw.githubusercontent.com/mariyasedova08-beep/ege-blizko-timer-bot/$1/deploy/install_cabinet_snapshot.py" -o "$setup_dir/helper"
printf '%s  %s\n' 'f7235be4e17fb7d81dbe074db0c345e390a4cf8ce64848ba6006d6012985f824' "$setup_dir/helper" | sha256sum -c -
helper=/usr/local/sbin/ege-cabinet-snapshot-release
rule=/etc/sudoers.d/ege-cabinet-snapshot-release
cat > "$setup_dir/rule" <<'RULE'
ege-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-cabinet-snapshot-release EGE-CABINET-SNAPSHOT-20261027-REVIEWED, /usr/local/sbin/ege-cabinet-snapshot-release EGE-CABINET-SNAPSHOT-20261027-REVIEWED-ROLLBACK
RULE
visudo -cf "$setup_dir/rule" >/dev/null
if [[ -e "$helper" || -L "$helper" ]]; then
  [[ -f "$helper" && ! -L "$helper" ]]
  [[ "$(stat -c %u "$helper")" == 0 ]]
  current_helper_sha=$(sha256sum "$helper")
  current_helper_sha=${current_helper_sha%% *}
  case "$current_helper_sha" in
    f7235be4e17fb7d81dbe074db0c345e390a4cf8ce64848ba6006d6012985f824) ;;
    *) printf '%s\n' 'UNREVIEWED_CABINET_HELPER'; exit 1 ;;
  esac
fi
if [[ -e "$rule" || -L "$rule" ]]; then
  [[ -f "$rule" && ! -L "$rule" ]]
  cmp -s "$rule" "$setup_dir/rule"
fi
install -o root -g root -m 0750 "$setup_dir/helper" "$helper"
install -o root -g root -m 0440 "$setup_dir/rule" "$rule"
visudo -c >/dev/null
printf '%s\n' 'CABINET_SNAPSHOT_FIXED_PERMISSION_READY_BOT_NOT_CHANGED'
