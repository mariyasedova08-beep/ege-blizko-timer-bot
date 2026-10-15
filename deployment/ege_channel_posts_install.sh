#!/usr/bin/env bash
# One-time, independently reviewable EGE BLIZKO channel post installer.
# NEVER resets/pulls a working tree, touches PREPODMIN, or sends a post.
# Fetch source first: git fetch origin feature/ege-channel-posts-20261015
set -Eeuo pipefail
umask 077

APP=/opt/bots/ege-blizko
SERVICE=ege-blizko
# Pin the code module to a reviewed commit rather than mutable FETCH_HEAD.
# Other Git operations on this checkout may overwrite FETCH_HEAD while the
# install is running; the object ID itself is immutable.
REF=96a0ddd5499c7b5fd3817829e5acddc68f724944
BACKUP_ROOT=/root/ege-channel-posts-install-backups
# Share the lock with the existing Timeweb autodeploy service so it cannot
# race with this one-off installer on the same checkout.
install -d -m 0755 /run/lock
exec 9>/run/lock/ege-blizko-autodeploy.lock
flock -w 20 9 || { echo "EGE deploy lock busy; stop and inspect" >&2; exit 1; }
DB=$APP/data/coreapp_webhooks.db

if [[ "$(id -u)" != "0" || "$#" -ne 0 ]]; then
  echo "Install must run as root with no arguments" >&2; exit 2
fi
[[ -f "$APP/run_bot_production.py" && -f "$APP/public_channel_trainers.py" && -f "$APP/ege_lab_webapp.py" ]] || {
  echo "Required EGE production code missing; no changes made" >&2; exit 1;
}
[[ "$(systemctl show "$SERVICE" -p User --value)" == "ege-bot" ]] || {
  echo "Unexpected EGE systemd service owner" >&2; exit 1;
}
systemctl is-active --quiet "$SERVICE"
systemctl is-active --quiet prepodmin
[[ -f "$DB" && ! -L "$DB" ]] || {
  echo "Expected EGE SQLite database missing; no changes made" >&2; exit 1;
}
# public_channel_trainers has an old one-time startup announcement. Do not
# restart production if the previous announcement state is unknown: enabling
# channel posting rights must not accidentally publish an old hydroxides post.
"$APP/.venv/bin/python" - "$DB" <<'PY'
import sqlite3, sys
with sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True) as db:
    found = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='channel_trainer_announcements'"
    ).fetchone()
    recorded = (db.execute(
        "SELECT 1 FROM channel_trainer_announcements WHERE announcement_key=?",
        ("hydroxides-100-launch-2026-10-06",),
    ).fetchone() if found else None)
    if not recorded:
        raise SystemExit("STOP: legacy hydroxides startup post not recorded; manual review before restart")
print("EGE_LEGACY_STARTUP_ANNOUNCEMENT_ALREADY_RECORDED")
PY
[[ ! -e "$APP/ege_channel_posts.py" ]] || {
  echo "Channel publisher already installed or needs manual review" >&2; exit 1;
}
if grep -Fq 'ege_channel_posts.install()' "$APP/run_bot_production.py"; then
  echo "Channel publisher hook already exists; no changes made" >&2; exit 1;
fi
git -C "$APP" cat-file -e "$REF^{commit}" || {
  echo "Pinned EGE release commit is not available locally; fetch branch first" >&2; exit 1;
}
git -C "$APP" cat-file -e "$REF:ege_channel_posts.py" || {
  echo "Pinned commit does not contain EGE channel module" >&2; exit 1;
}
echo "EGE_CHANNEL_SOURCE_PINNED sha=$REF"
[[ -x "$APP/.venv/bin/python" ]] || { echo "EGE Python venv missing" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
ARCHIVE="$BACKUP_ROOT/$STAMP"
install -d -o root -g root -m 0700 "$ARCHIVE"
git -C "$APP" show "$REF:ege_channel_posts.py" > "$ARCHIVE/ege_channel_posts.py"
"$APP/.venv/bin/python" -m py_compile "$ARCHIVE/ege_channel_posts.py"
cp -a "$APP/run_bot_production.py" "$ARCHIVE/run_bot_production.py.before"
"$APP/.venv/bin/python" - "$APP/run_bot_production.py" "$ARCHIVE/run_bot_production.py.new" <<'PY'
from pathlib import Path
import sys
src, dst = [Path(arg) for arg in sys.argv[1:]]
text = src.read_text(encoding="utf-8")
marker = "    import ege_lab_webapp\n    ege_lab_webapp.install()\n"
if text.count(marker) != 1 or "ege_channel_posts.install()" in text:
    raise RuntimeError("Runtime integration anchor missing or already installed")
insert = (marker + "\n"
          "    # Posts are previewed first; nothing publishes during startup.\n"
          "    import ege_channel_posts\n"
          "    ege_channel_posts.install()\n")
dst.write_text(text.replace(marker, insert), encoding="utf-8")
PY
"$APP/.venv/bin/python" -m py_compile "$ARCHIVE/run_bot_production.py.new"

# Consistent SQLite snapshot before any production code changes.
"$APP/.venv/bin/python" - "$DB" "$ARCHIVE/coreapp_webhooks.db" <<'PY'
import sqlite3, sys
src, dest = sys.argv[1:]
with sqlite3.connect("file:" + src + "?mode=ro", uri=True, timeout=30) as a:
    with sqlite3.connect(dest, timeout=30) as b:
        a.backup(b)
        if b.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite snapshot verification failed")
print("EGE_CHANNEL_SQLITE_SNAPSHOT_OK", flush=True)
PY
# Do not restart or touch PREPODMIN at any point.
CHANGED=0
rollback() {
  result=$?
  trap - ERR
  if (( result != 0 )) && (( CHANGED )); then
    echo "EGE_CHANNEL_INSTALL_FAILED; attempting code rollback" >&2
    cp -a "$ARCHIVE/run_bot_production.py.before" "$APP/run_bot_production.py"
    rm -f "$APP/ege_channel_posts.py"
    systemctl restart "$SERVICE" || true
    systemctl is-active "$SERVICE" || true
  fi
  exit "$result"
}
trap rollback ERR

CHANGED=1
install -o root -g root -m 0644 "$ARCHIVE/ege_channel_posts.py" "$APP/ege_channel_posts.py"
install -o root -g root -m 0644 "$ARCHIVE/run_bot_production.py.new" "$APP/run_bot_production.py"
"$APP/.venv/bin/python" -m py_compile "$APP/run_bot_production.py" "$APP/ege_channel_posts.py"
START="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
systemctl restart "$SERVICE"
HEALTH_OK=0
for _ in $(seq 1 20); do
  if systemctl is-active --quiet "$SERVICE" \
     && curl -fsS --max-time 3 http://127.0.0.1:8080/health >/dev/null; then
    HEALTH_OK=1
    break
  fi
  sleep 2
done
(( HEALTH_OK == 1 )) || { echo "EGE health failed after restart" >&2; exit 1; }
LOG="$(journalctl -u "$SERVICE" --since "$START" --no-pager -o cat)"
[[ "$LOG" == *"EGE_CHANNEL_POSTS_READY preview_only=1 requires_admin_confirmation=1"* ]] || {
  echo "Channel publisher startup marker missing" >&2; exit 1;
}
systemctl is-active --quiet prepodmin
CHANGED=0
trap - ERR
echo EGE_CHANNEL_POSTS_INSTALLED_OK
echo EGE_HEALTH=200
echo PREPODMIN=active
echo STARTUP_AUTOPOST=disabled
echo "ROLLBACK_BACKUP=$ARCHIVE"
