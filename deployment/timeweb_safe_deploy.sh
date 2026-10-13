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
FILES=(oge9_trainer_notifications.py run_bot_production.py special_salts_trainer.py special_salts_trainer_bank.py)
ARCHIVE="$BACKUPS/$(date -u +%Y%m%dT%H%M%SZ)-$$"
ROOT_STAGE="$ARCHIVE/incoming"

[[ -d "$APP" && -f "$APP/run_bot_production.py" ]] || { echo "Production app missing" >&2; exit 1; }
[[ -d "$STAGING" && ! -L "$STAGING" ]] || { echo "Staging directory invalid" >&2; exit 1; }
[[ "$(stat -c %U "$STAGING")" == "ege-deploy" ]] || { echo "Staging owner mismatch" >&2; exit 1; }
[[ "$(systemctl is-active "$SERVICE")" == "active" ]] || { echo "Bot not active" >&2; exit 1; }
SERVICE_USER="$(systemctl show -p User --value "$SERVICE")"
if [[ "$SERVICE_USER" != "ege-bot" ]]; then
  echo "Unsafe: bot must run as dedicated ege-bot, got: $SERVICE_USER" >&2
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
"$PY" -m py_compile "${FILES[@]/#/$ROOT_STAGE/}"
"$PY" - "$ROOT_STAGE/run_bot_production.py" "$ROOT_STAGE/special_salts_trainer_bank.py" <<'PY'
import ast, sys
source = open(sys.argv[1], encoding="utf-8").read()
assert source.count("oge9_trainer_notifications.install()") == 1, "OGE9 hook missing or duplicate"
assert source.count("special_salts_trainer.install()") == 1, "Special salts hook missing or duplicate"
tree = ast.parse(open(sys.argv[2], encoding="utf-8").read(), filename=sys.argv[2])
rows = None
for item in tree.body:
    if isinstance(item, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DATA_ROWS" for t in item.targets):
        rows = ast.literal_eval(item.value)
        break
assert isinstance(rows, list) and len(rows) == 50, "Expected 50 salt questions"
prompts = set()
for row in rows:
    assert len(row) == 8, "Malformed salt question"
    topic, page, prompt, correct, a, b, c, explanation = row
    assert all(isinstance(x, str) and x.strip() for x in row), "Empty question field"
    assert len({correct, a, b, c}) == 4, "Duplicate answers"
    prompts.add(prompt)
assert len(prompts) == 50, "Duplicate salt questions"
print("Special salts bank: 50 distinct questions validated")
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
"$PY" -m py_compile "${FILES[@]/#/$APP/}"
START="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
systemctl restart "$SERVICE"
sleep 12
systemctl is-active --quiet "$SERVICE"
[[ "$(systemctl show "$SERVICE" -p User --value)" == "ege-bot" ]]
curl --fail --silent --max-time 10 http://127.0.0.1:8080/health > /dev/null
LOG="$(journalctl -u "$SERVICE" --since "$START" --no-pager -o cat)"
[[ "$LOG" == *"OGE9 trainer chat scheduler installed"* ]] || { echo "OGE9 startup marker missing" >&2; false; }
[[ "$LOG" == *"Special salts trainer installed: questions=50"* ]] || { echo "Special salts startup marker missing" >&2; false; }
trap - ERR
echo "DEPLOY SUCCESS; rollback files and DB snapshot at $ARCHIVE"
