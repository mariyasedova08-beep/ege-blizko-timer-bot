#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${EGE_APP_DIR:-/opt/bots/ege-blizko}"
BRANCH="${EGE_DEPLOY_BRANCH:-hotfix/ege-middle-salts-66-facts-20261007}"
SERVICE="${EGE_SERVICE:-ege-blizko}"
HEALTH_URL="${EGE_HEALTH_URL:-https://77-233-212-200.sslip.io/health}"
STATE_DIR="${EGE_DEPLOY_STATE_DIR:-/var/lib/ege-blizko-autodeploy}"
LOCK_FILE="/run/lock/ege-blizko-autodeploy.lock"

mkdir -p "$STATE_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

cd "$APP_DIR"

git fetch -q origin "$BRANCH"
REMOTE_REF="origin/$BRANCH"
REMOTE_HEAD="$(git rev-parse "$REMOTE_REF")"
RELEASE_MARKER="$(git show "$REMOTE_REF:deploy/release.ref" 2>/dev/null | tr -d '\r\n' || true)"
[ -n "$RELEASE_MARKER" ] || { echo "autodeploy: release marker missing"; exit 1; }

LAST_MARKER="$(cat "$STATE_DIR/release.ref" 2>/dev/null || true)"
FAILED_MARKER="$(cat "$STATE_DIR/failed.ref" 2>/dev/null || true)"

if [ "${1:-}" != "--force" ]; then
  [ "$RELEASE_MARKER" = "$LAST_MARKER" ] && exit 0
  if [ "$RELEASE_MARKER" = "$FAILED_MARKER" ]; then
    echo "autodeploy: release $RELEASE_MARKER already failed; waiting for a new release marker"
    exit 0
  fi
fi

OLD_HEAD="$(git rev-parse HEAD)"
echo "autodeploy: deploying $REMOTE_HEAD marker=$RELEASE_MARKER from $OLD_HEAD"

rollback() {
  echo "autodeploy: deployment failed, rolling back to $OLD_HEAD"
  git reset --hard -q "$OLD_HEAD"
  systemctl restart "$SERVICE" || true
  sleep 5
  curl -fsS "$HEALTH_URL" >/dev/null || true
  printf '%s\n' "$RELEASE_MARKER" > "$STATE_DIR/failed.ref"
}
trap rollback ERR

git reset --hard -q "$REMOTE_HEAD"
"$APP_DIR/.venv/bin/python" -m compileall -q "$APP_DIR"

systemctl restart "$SERVICE"

healthy=0
for _ in $(seq 1 15); do
  sleep 2
  if curl -fsS "$HEALTH_URL" >/dev/null; then
    healthy=1
    break
  fi
done
[ "$healthy" -eq 1 ]

printf '%s\n' "$RELEASE_MARKER" > "$STATE_DIR/release.ref"
rm -f "$STATE_DIR/failed.ref"
trap - ERR

echo "autodeploy: success marker=$RELEASE_MARKER head=$REMOTE_HEAD"
