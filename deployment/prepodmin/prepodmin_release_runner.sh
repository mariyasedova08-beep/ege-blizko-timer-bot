#!/usr/bin/env bash
# Install as root-owned /usr/local/sbin/prepodmin-release (never execute
# the checkout's mutable copy as root). Deploys PREPODMIN only.
set -Eeuo pipefail
umask 077

REPO=/opt/bots/prepodmin/current
DB=/opt/bots/prepodmin/data/teacher_product.sqlite3
BACKUP_DIR=/var/backups/prepodmin/predeploy
BRANCH=feature/prepodmin-timeweb-migration-20261013
SERVICE=prepodmin
PUBLIC_URL=https://prepodmin.77-233-212-200.sslip.io

[[ "$(id -u)" == "0" && $# -eq 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || {
  echo "Usage: root-owned prepodmin-release <40-char-git-sha>" >&2
  exit 2
}
TARGET_SHA="$1"
CHANGED=0
PREVIOUS_SHA=""

git_p() {
  runuser -u prepodmin -- git -C "$REPO" "$@"
}

on_exit() {
  local result="$?"
  trap - EXIT
  if (( result != 0 )); then
    echo "PREPODMIN_DEPLOY_FAILED (exit=$result)" >&2
    if (( CHANGED )); then
      echo "PREPODMIN_CODE_ROLLBACK_STARTED" >&2
      git_p reset --hard "$PREVIOUS_SHA" >/dev/null || true
      systemctl restart "$SERVICE" || true
      sleep 3
      systemctl is-active "$SERVICE" || true
      echo "PREPODMIN_CODE_ROLLBACK_ATTEMPTED; database snapshot retained" >&2
    fi
  fi
  exit "$result"
}
trap on_exit EXIT

# Reject if a protected shared service is not already healthy.
systemctl is-active --quiet ege-blizko
systemctl is-active --quiet "$SERVICE"
[[ "$(git_p branch --show-current)" == "$BRANCH" ]] || {
  echo "Wrong PREPODMIN branch; refusing deploy" >&2; exit 1;
}
[[ -z "$(git_p status --porcelain --untracked-files=no)" ]] || {
  echo "Dirty tracked PREPODMIN files; refusing destructive git reset" >&2; exit 1;
}
[[ -s "$DB" && ! -L "$DB" ]] || { echo "Database is missing or a symlink" >&2; exit 1; }
PREVIOUS_SHA="$(git_p rev-parse HEAD)"
[[ "$PREVIOUS_SHA" =~ ^[a-f0-9]{40}$ ]]

# Fetch exactly this PREPODMIN branch; never touch the EGE working tree.
git_p fetch --no-tags origin "refs/heads/$BRANCH"
REMOTE_SHA="$(git_p rev-parse FETCH_HEAD)"
[[ "$REMOTE_SHA" == "$TARGET_SHA" ]] || {
  echo "Target sha is not the current reviewed PREPODMIN branch tip" >&2; exit 1;
}
git_p merge-base --is-ancestor "$PREVIOUS_SHA" "$TARGET_SHA" || {
  echo "Non-fast-forward PREPODMIN release blocked" >&2; exit 1;
}
if git_p diff --name-only "$PREVIOUS_SHA" "$TARGET_SHA" -- requirements.txt | grep -q .; then
  echo "Requirements changed: manual dependency review required" >&2; exit 1
fi
while IFS= read -r path; do
  case "$path" in
    teacher_product_*.py|teacher_product_*.html|deployment/prepodmin/*|.github/workflows/prepodmin-*.yml)
      ;;
    *)
      echo "Blocked file outside PREPODMIN allowlist: $path" >&2
      exit 1
      ;;
  esac
done < <(git_p diff --name-only "$PREVIOUS_SHA" "$TARGET_SHA")

# Root-owned, private SQLite snapshot before any working-tree mutation.
install -d -o root -g root -m 0700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/prepodmin-predeploy-$STAMP.sqlite3"
python3 - "$DB" "$BACKUP" <<'PY'
import os, sqlite3, sys
from pathlib import Path
from urllib.parse import quote
src, dst = (Path(p) for p in sys.argv[1:])
if dst.exists() or not src.is_file():
    raise RuntimeError("Backup destination already exists or source is missing")
uri = "file:" + quote(str(src.resolve()), safe="/") + "?mode=ro"
try:
    with sqlite3.connect(uri, uri=True, timeout=30) as source:
        with sqlite3.connect(str(dst), timeout=30) as target:
            source.backup(target, pages=100, sleep=0.2)
    os.chmod(dst, 0o600)
    with sqlite3.connect(str(dst), timeout=30) as check:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Predeploy snapshot integrity check failed")
except BaseException:
    dst.unlink(missing_ok=True)
    raise
print("PREPODMIN_PREDEPLOY_DB_SNAPSHOT_OK")
PY

# This checkout is only /opt/bots/prepodmin/current, never /opt/bots/ege-blizko.
CHANGED=1
git_p reset --hard "$TARGET_SHA" >/dev/null

# Production restart is permitted for PREPODMIN only.
systemctl restart "$SERVICE"
HEALTHY=0
for attempt in $(seq 1 20); do
  if systemctl is-active --quiet "$SERVICE" \
     && curl --silent --show-error --fail --max-time 4 \
       http://127.0.0.1:8091/health | grep -q '"ok":true'; then
    HEALTHY=1
    break
  fi
  sleep 2
done
(( HEALTHY == 1 )) || { echo "PREPODMIN health did not recover" >&2; exit 1; }

# Check HTTPS WebApp endpoints without tokens or personal data.
curl -fsS --max-time 10 -o /dev/null "$PUBLIC_URL/webapp"
curl -fsS --max-time 10 -o /dev/null "$PUBLIC_URL/student"
systemctl is-active --quiet ege-blizko
systemctl is-active --quiet "$SERVICE"
[[ "$(git_p rev-parse HEAD)" == "$TARGET_SHA" ]]
CHANGED=0
echo "PREPODMIN_DEPLOY_OK sha=$TARGET_SHA"
echo "PREPODMIN_DB_SNAPSHOT_READY (on server only)"
echo "EGE_BLIZKO_UNTOUCHED_AND_ACTIVE"
