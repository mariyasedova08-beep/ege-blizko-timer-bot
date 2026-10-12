#!/usr/bin/env bash
# Install a reviewed, explicit allowlist of Python source files only.
# Never git checkout/pull/reset/clean in the production working tree.
set -Eeuo pipefail
umask 077
APP="/opt/bots/ege-blizko"
SERVICE="ege-blizko"
SOURCE="${1:?usage: deploy.sh /path/to/staged/files}"
BACKUPS="/root/ege-blizko-deploy-backups"
FILES=( "oge9_trainer_notifications.py" "run_bot_production.py" )
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUPS/$STAMP"
mkdir -p "$ARCHIVE"
[[ -d "$APP" ]] || { echo "Missing production app: $APP"; exit 1; }
[[ -d "$SOURCE" ]] || { echo "Missing upload staging dir"; exit 1; }
[[ "$(systemctl is-active "$SERVICE")" == active ]] || { echo "Service not active; investigate first"; exit 1; }
for f in "${FILES[@]}"; do
  [[ -s "$SOURCE/$f" ]] || { echo "Staged file is missing: $f"; exit 1; }
  [[ -e "$APP/$f" ]] && cp -a "$APP/$f" "$ARCHIVE/$f" || touch "$ARCHIVE/$f.was-absent"
done
# Compile staged code before changing production.
"$APP/.venv/bin/python" -m py_compile "${FILES[@]/#/$SOURCE/}"
# Snapshot the SQLite DB with online backup; never use cp on a busy database.
DB="$APP/data/coreapp_webhooks.db"
if [[ -f "$DB" ]]; then
  "$APP/.venv/bin/python" - "$DB" "$ARCHIVE/coreapp_webhooks.db" <<'PY'
import sqlite3,sys
src,dst=sys.argv[1:]
with sqlite3.connect("file:"+src+"?mode=ro",uri=True) as a:
    with sqlite3.connect(dst) as b:
        a.backup(b)
        if b.execute("pragma integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("SQLite backup failed integrity check")
print("SQLite snapshot: integrity ok")
PY
fi
restore() {
  echo "Deploy failed; rolling back installed code..."
  for f in "${FILES[@]}"; do
    if [[ -f "$ARCHIVE/$f" ]]; then
      cp -a "$ARCHIVE/$f" "$APP/$f"
    elif [[ -f "$ARCHIVE/$f.was-absent" ]]; then
      rm -f "$APP/$f"
    fi
  done
  systemctl restart "$SERVICE" || true
  systemctl is-active "$SERVICE" || true
}
trap restore ERR
for f in "${FILES[@]}"; do
  install -m 0644 "$SOURCE/$f" "$APP/$f"
done
"$APP/.venv/bin/python" -m py_compile "${FILES[@]/#/$APP/}"
systemctl restart "$SERVICE"
sleep 12
systemctl is-active --quiet "$SERVICE"
journalctl -u "$SERVICE" --since "-1 minute" --no-pager | grep -q 'OGE9 trainer chat scheduler installed'
trap - ERR
echo "SAFE DEPLOY SUCCESS; rollback bundle in $ARCHIVE"
