#!/usr/bin/env bash
# One-time setup of conservative, approval-gated Timeweb pull-deploy.
# No production bot restart; no git checkout/merge/pull/reset; no chat messages.
set -euo pipefail

REPO=/opt/bots/ege-blizko
OPS=refs/remotes/origin/ops/ege-timeweb-autodeploy-20261012
RELEASE=refs/remotes/origin/release/ege-blizko-prod

if [[ $(id -u) -ne 0 ]]; then
  echo "ERROR: run as root on the Timeweb VPS" >&2
  exit 1
fi
if [[ ! -d "$REPO/.git" || ! -f "$REPO/data/coreapp_webhooks.db" ]]; then
  echo "ERROR: existing EGE BLIZKO repository/database not found" >&2
  exit 1
fi
if [[ $(systemctl is-active ege-blizko) != active ]]; then
  echo "ERROR: existing bot is not active, refusing to install" >&2
  exit 1
fi
cd "$REPO"
git fetch --no-tags origin \
  refs/heads/ops/ege-timeweb-autodeploy-20261012:"$OPS" \
  refs/heads/release/ege-blizko-prod:"$RELEASE"
HEAD_SHA=$(git rev-parse HEAD)
REL_SHA=$(git rev-parse "$RELEASE")
if [[ "$HEAD_SHA" != "$REL_SHA" ]]; then
  echo "ERROR: release baseline differs from live Git HEAD. No changes made." >&2
  echo "Live: $HEAD_SHA; Release: $REL_SHA" >&2
  exit 1
fi
umask 077
mkdir -p /usr/local/libexec /var/lib/ege-blizko-deploy /var/backups/ege-blizko-deploy
chmod 700 /var/lib/ege-blizko-deploy /var/backups/ege-blizko-deploy
if [[ -e /var/lib/ege-blizko-deploy/deployed_commit ]]; then
  echo "ERROR: deployment marker exists; refusing to reset history" >&2
  exit 1
fi
# Installing from the selected ops Git branch, not from any untrusted website.
git show "$OPS":deploy/ege_timeweb_pull_deploy.py > /usr/local/libexec/ege-timeweb-pull-deploy.py
python3 -m py_compile /usr/local/libexec/ege-timeweb-pull-deploy.py
chmod 700 /usr/local/libexec/ege-timeweb-pull-deploy.py
git show "$OPS":deploy/ege-blizko-poll.service > /etc/systemd/system/ege-blizko-poll.service
git show "$OPS":deploy/ege-blizko-poll.timer > /etc/systemd/system/ege-blizko-poll.timer
chmod 644 /etc/systemd/system/ege-blizko-poll.service /etc/systemd/system/ege-blizko-poll.timer
printf '%s\n' "$HEAD_SHA" > /var/lib/ege-blizko-deploy/deployed_commit
chmod 600 /var/lib/ege-blizko-deploy/deployed_commit
systemctl daemon-reload
systemctl enable --now ege-blizko-poll.timer
echo "EGE BLIZKO AUTO-DEPLOY READY"
echo "Baseline release SHA: $REL_SHA"
systemctl list-timers --all --no-pager | grep ege-blizko-poll || true
echo "Bot status: $(systemctl is-active ege-blizko)"
echo "No code deployment or bot restart performed during installation."
