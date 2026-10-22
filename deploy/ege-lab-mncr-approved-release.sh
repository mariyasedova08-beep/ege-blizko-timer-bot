#!/usr/bin/env bash
# EGE BLIZKO Mn/Cr: lab-only release from the ALREADY VALIDATED Timeweb staging.
# Never run directly: caller must pass the protected GitHub approval gate.
# Does NOT change git branch, deploy/release.ref, Telegram bot token, student DB,
# local trainer or run_bot_production.py customizations.
set -Eeuo pipefail
umask 077
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1

APP=/opt/bots/ege-blizko
STAGING_ROOT=/root/ege-blizko-staging
CHECKED="$STAGING_ROOT/ege_lab_webapp_checked.py"
BACKUP_ROOT=/root/ege-blizko-backups
SERVICE=ege-blizko
TIMER=ege-blizko-autodeploy.timer
LOCK=/run/lock/ege-blizko-autodeploy.lock
HEALTH=https://77-233-212-200.sslip.io/health
EXPECTED_LIVE=d95b80eb423a6295eac080f66d1707ac1e92e789
EXPECTED_STAGE=7b31b039c7dcc6d3ae2f31e5f241f747f17f5d17
EXPECTED_FILE=23153dd715d2277d437e35c63b8345c53fb59d46c6b908f02ee0b0094656d58e
RELEASE_ID=EGE-LAB-MNCR-20261021-CHECKED

# Only these four lab files can be installed. Live teacher/admin code stays intact.
LAB_FILES=(ege_lab_webapp.py ege_lab_substances.py ege_lab_inorganic_reactions.py ege_lab_mn_cr_pdf_import.py)
LIVE_ONLY_FILES=(public_channel_trainers.py run_bot_live7.py run_bot_production.py)

fatal() { echo "RELEASE_ABORTED: $*" >&2; return 1; }
sha_of() { sha256sum "$1" | awk '{print $1}'; }

[[ "$#" == 1 && "$1" == "$RELEASE_ID" ]] || fatal "Requires exact pinned release ID"
[[ "$(id -u)" == "0" ]] || fatal "Must run as the restricted sudo target"
[[ -f /usr/local/libexec/ege-lab-release-entry && -f /etc/sudoers.d/ege-lab-deploy ]] || fatal "Restricted SSH entry not installed"
[[ -d "$APP/.git" && -d "$STAGING_ROOT" ]] || fatal "Production or staging folder missing"
[[ "$(git -C "$APP" rev-parse HEAD)" == "$EXPECTED_LIVE" ]] || fatal "Unexpected production git head"
[[ "$(systemctl is-active "$SERVICE")" == "active" ]] || fatal "Bot service not healthy"
[[ "$(systemctl is-active "$TIMER")" == "active" ]] || fatal "Unexpected autodeploy timer state"

# Hold the SAME exclusive lock as the legacy git-reset autodeploy watcher.
exec 9>"$LOCK"
flock -w 30 9 || fatal "Autodeploy lock is busy"
[[ "$(git -C "$APP" rev-parse HEAD)" == "$EXPECTED_LIVE" ]] || fatal "Git head changed during lock"

[[ -f "$CHECKED" && ! -L "$CHECKED" ]] || fatal "Checked file missing"
[[ "$(sha_of "$CHECKED")" == "$EXPECTED_FILE" ]] || fatal "Unexpected checked file SHA256"

# The *actual checkout* in merge-check-* was created at 7b31b039.
# A later FETCH_HEAD update to fcfcac8 did NOT move its working tree/HEAD.
# GitHub compare confirmed fcfcac8 only adds test/CI scripts; no chemistry/UI
# sources differ between these two commits. Keep the exact checkout pin.
CANDIDATE=""
STAGING_FOUND=0
STAGING_HEAD_MISMATCH=0
STAGING_HASH_MISMATCH=0
while IFS= read -r -d '' file; do
  STAGING_FOUND=$((STAGING_FOUND + 1))
  dir="$(dirname "$file")"
  if [[ ! -d "$dir/.git" ]] || [[ "$(git -C "$dir" rev-parse HEAD)" != "$EXPECTED_STAGE" ]]; then
    STAGING_HEAD_MISMATCH=$((STAGING_HEAD_MISMATCH + 1))
    continue
  fi
  if ! cmp -s "$CHECKED" "$file"; then
    STAGING_HASH_MISMATCH=$((STAGING_HASH_MISMATCH + 1))
    continue
  fi
  [[ -z "$CANDIDATE" ]] || fatal "Multiple matching staging repos"
  CANDIDATE="$dir"
done < <(find "$STAGING_ROOT" -type f -path '*/merge-check-*/repo/ege_lab_webapp.py' -print0)
if [[ -z "$CANDIDATE" ]]; then
  echo "STAGING_DIAGNOSTIC: found=$STAGING_FOUND head_mismatch=$STAGING_HEAD_MISMATCH checked_ui_mismatch=$STAGING_HASH_MISMATCH" >&2
  fatal "Verified candidate not found"
fi
for name in "${LAB_FILES[@]}"; do
  [[ -f "$CANDIDATE/$name" && ! -L "$CANDIDATE/$name" ]] || fatal "Missing candidate $name"
done

# Check exactly the 3 tracked local customizations that were backed up and merged.
CHANGED="$(git -C "$APP" diff HEAD --name-only | LC_ALL=C sort)"
EXPECTED_CHANGED="$(printf '%s\n' ege_lab_webapp.py public_channel_trainers.py run_bot_live7.py run_bot_production.py | LC_ALL=C sort)"
[[ "$CHANGED" == "$EXPECTED_CHANGED" ]] || fatal "Production has unexpected local modifications"

# Must not modify the legacy automatic release marker or its tracked branch.
LIVE_MARKER="$(cat /var/lib/ege-blizko-autodeploy/release.ref 2>/dev/null || true)"
[[ "$LIVE_MARKER" == "release-20261009-task6-full-trainer-v3-fix1" ]] ||
  fatal "Legacy deployment marker changed; revisit release plan"

echo "PREFLIGHT_OK: $RELEASE_ID"
(
  cd "$CANDIDATE"
  python3 -m unittest discover -s tests -p 'test_lab_redox_exchange_expansion.py' -q
  python3 -m unittest discover -s tests -p 'test_lab_mncr_preflight_guard.py' -q
)
echo "CHEMISTRY_AND_GUARDS_OK"

# Backup immediately before any mutation. The SQLite online-backup API is used
# while the bot is running; a raw copy of a changing .db would be unsafe.
mkdir -p -m 0700 "$BACKUP_ROOT"
BACKUP="$(mktemp -d "$BACKUP_ROOT/lab-release-XXXXXXXX")"
mkdir -m 0700 "$BACKUP/code" "$BACKUP/data" "$BACKUP/service" "$BACKUP/protected-code"
for name in "${LAB_FILES[@]}"; do
  if [[ -f "$APP/$name" ]]; then
    cp -p -- "$APP/$name" "$BACKUP/code/$name"
  else
    touch "$BACKUP/code/$name.NOT_PRESENT"
  fi
done
for name in "${LIVE_ONLY_FILES[@]}"; do
  [[ -f "$APP/$name" ]] || fatal "Protected application file missing: $name"
  cp -p -- "$APP/$name" "$BACKUP/protected-code/$name"
  cmp -s -- "$APP/$name" "$BACKUP/protected-code/$name" || fatal "Protected code backup differs: $name"
  sha256sum "$APP/$name" >> "$BACKUP/protected-files.sha256"
done
cp -p /etc/systemd/system/ege-blizko.service "$BACKUP/service/ege-blizko.service"
if [[ -f /etc/systemd/system/ege-blizko.service.d/70-ege-bot.conf ]]; then
  cp -p /etc/systemd/system/ege-blizko.service.d/70-ege-bot.conf "$BACKUP/service/70-ege-bot.conf"
fi
APP="$APP" BACKUP="$BACKUP" python3 - <<'PY'
import os, sqlite3
from pathlib import Path
source = Path(os.environ["APP"])/"data"
target = Path(os.environ["BACKUP"])/"data"
dbs = sorted(source.glob("*.db"))
assert dbs, "Missing database for backup"
for p in dbs:
    with sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30) as src:
        with sqlite3.connect(str(target/p.name)) as dest:
            src.backup(dest)
            assert dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("CONSISTENT_DATABASE_BACKUP_OK")
PY
sha256sum "$BACKUP/code/"* > "$BACKUP/lab-code.sha256"
echo "PRE_DEPLOY_BACKUP_OK: $BACKUP"

# Keep rollback inside the same lock. DB and ALL THREE protected live-only files remain untouched.
DEPLOY_STARTED=0
rollback() {
  local status=$?
  trap - ERR INT TERM HUP
  if [[ "$DEPLOY_STARTED" == 1 ]]; then
    echo "ROLLING_BACK_LAB_ONLY: $BACKUP" >&2
    for name in "${LAB_FILES[@]}"; do
      if [[ -f "$BACKUP/code/$name.NOT_PRESENT" ]]; then
        rm -f -- "$APP/$name"
      else
        cp -p -- "$BACKUP/code/$name" "$APP/$name" || true
      fi
    done
    systemctl restart "$SERVICE" || true
    curl --fail --silent --show-error --max-time 10 "$HEALTH" >/dev/null || true
  fi
  echo "RELEASE_FAILED: exit=$status; backup=$BACKUP" >&2
  exit "$status"
}
trap rollback ERR
trap 'false' INT TERM HUP

# Install only pinned chemistry modules and validated merged UI.
DEPLOY_STARTED=1
OWNER_ID="$(stat -c '%u' "$APP/ege_lab_webapp.py")"
GROUP_ID="$(stat -c '%g' "$APP/ege_lab_webapp.py")"
for name in "${LAB_FILES[@]}"; do
  tmp="$(mktemp "$APP/.${name}.XXXXXXXX")"
  install -m 0644 -o "$OWNER_ID" -g "$GROUP_ID" "$CANDIDATE/$name" "$tmp"
  mv -Tf "$tmp" "$APP/$name"
done

# Syntax compilation without starting a second Telegram bot.
APP="$APP" python3 - <<'PY'
import ast, os
from pathlib import Path
for name in ("ege_lab_webapp.py", "ege_lab_substances.py",
             "ege_lab_inorganic_reactions.py", "ege_lab_mn_cr_pdf_import.py"):
    ast.parse((Path(os.environ["APP"])/name).read_text(encoding="utf-8"))
print("LAB_PYTHON_SYNTAX_OK")
PY
systemctl restart "$SERVICE"
ok=0
for attempt in $(seq 1 15); do
  if curl --fail --silent --show-error --max-time 5 "$HEALTH" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
[[ "$ok" == 1 ]] || fatal "HTTP health failed after restart"

# Service still healthy, protected scripts unchanged, and expected staging hash.
(
  cd "$APP"
  sha256sum -c "$BACKUP/protected-files.sha256" >/dev/null
)
[[ "$(sha_of "$APP/ege_lab_webapp.py")" == "$EXPECTED_FILE" ]] ||
  fatal "Installed lab UI checksum mismatch"
[[ "$(cat /var/lib/ege-blizko-autodeploy/release.ref 2>/dev/null || true)" == "$LIVE_MARKER" ]] ||
  fatal "Legacy autodeploy marker unexpectedly changed"
trap - ERR INT TERM HUP
DEPLOY_STARTED=0
echo "LAB_RELEASE_SUCCESS: $RELEASE_ID"
echo "ROLLBACK_BUNDLE: $BACKUP"
echo "PROTECTED_TRAINER_AND_LAUNCHER_UNCHANGED"
