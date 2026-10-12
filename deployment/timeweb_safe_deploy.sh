#!/usr/bin/env bash
# Install as root-owned /usr/local/sbin/ege-blizko-deploy (0755).
# Never run CI-uploaded scripts as root or git pull/reset/clean production.
set -Eeuo pipefail
umask 077
if [[ "${EUID}" -ne 0 || "${#}" -ne 0 ]]; then
  echo "Must be root with no arguments" >&2; exit 2
fi
APP="/opt/bots/ege-blizko"
SERVICE="ege-blizko"
STAGING="/home/ege-deploy/ege-blizko-staging"
BACKUPS="/root/ege-blizko-deploy-backups"
FILES=(oge9_trainer_notifications.py run_bot_production.py)
ARCHIVE="$BACKUPS/$(date -u +%Y%m%dT%H%M%SZ)-$$"
ROOT_STAGE="$ARCHIVE/incoming"

[[ -d "$APP" && -f "$APP/run_bot_production.py" ]] || { echo "Production app missing" >&2; exit 1; }
[[ -d "$STAGING" && ! -L "$STAGING" ]] || { echo "Staging directory invalid" >&2; exit 1; }
[[ "$(stat -c %U "$STAGING")" == "ege-deploy" ]] || { echo "Staging owner mismatch" >&2; exit 1; }
[[ "$(systemctl is-active "$SERVICE")" == "active" ]] || { echo "Bot not active" >&2; exit 1; }
SERVICE_USER="$(systemctl show -p User --value "$SERVICE")"
if [[ -z "$SERVICE_USER" || "$SERVICE_USER" == "root" ]]; then
  echo "Unsafe: bot still runs as root; migrate to dedicated service account before enabling deploy." >&2
  exit 1
fi
install -d -m 0700 "$ARCHIVE" "$ROOT_STAGE"
for file in "${FILES[@]}"; do
  [[ -f "$STAGING/$file" && ! -L "$STAGING/$file" && -s "$STAGING/$file" ]] || {
    echo "Missing or invalid staging file: $file" >&2; exit 1
  }
  install -m 0600 "$STAGING/$file" "$ROOT_STAGE/$file"
done

PY="$APP/.venv/bin/python"
"$PY" -m py_compile "$ROOT_STAGE/oge9_trainer_notifications.py" "$ROOT_STAGE/run_bot_production.py"
"$PY" - "$ROOT_STAGE/run_bot_production.py" <<'PY'
import sys
s=open(sys.argv[1],encoding="utf-8").read()
assert s.count("oge9_trainer_notifications.install()")==1, "OGE9 hook missing or duplicate"
PY
for file in "${FILES[@]}"; do
  if [[ -e "$APP/$file" ]]; then
    cp -a "$APP/$file" "$ARCHIVE/$file"
  else
    touch "$ARCHIVE/$file.was-absent"
  fi
done

# Consistent online SQLite backup, including committed WAL data.
DB="$APP/data/coreapp_webhooks.db"
[[ -f "$DB" ]] || { echo "Expected production DB missing" >&2; exit 1; }
"$PY" - "$DB" "$ARCHIVE/coreapp_webhooks.db" <<'PY'
import sqlite3,sys
src,dst=sys.argv[1:]
with sqlite3.connect("file:"+src+"?mode=ro",uri=True,timeout=30) as a:
    with sqlite3.connect(dst,timeout=30) as b:
        a.backup(b)
        result=b.execute("PRAGMA integrity_check").fetchone()[0]
        if result!="ok": raise RuntimeError("Integrity check: "+str(result))
print("SQLite snapshot integrity: ok")
PY

rollback() {
  trap - ERR; set +e
  echo "DEPLOY FAILED; restoring original code. DB is NOT overwritten." >&2
  for file in "${FILES[@]}"; do
    if [[ -f "$ARCHIVE/$file" ]]; then
      cp -a "$ARCHIVE/$file" "$APP/$file"
    elif [[ -f "$ARCHIVE/$file.was-absent" ]]; then
      rm -f "$APP/$file"
    fi
  done
  systemctl restart "$SERVICE"
  systemctl is-active "$SERVICE"
}
trap 'rollback' ERR

for file in "${FILES[@]}"; do
  install -m 0644 "$ROOT_STAGE/$file" "$APP/$file"
done
"$PY" -m py_compile "$APP/oge9_trainer_notifications.py" "$APP/run_bot_production.py"
START="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
systemctl restart "$SERVICE"
sleep 12
systemctl is-active --quiet "$SERVICE"
journalctl -u "$SERVICE" --since "$START" --no-pager | grep -q 'OGE9 trainer chat scheduler installed'
trap - ERR
echo "DEPLOY SUCCESS; rollback files and DB snapshot at $ARCHIVE"
