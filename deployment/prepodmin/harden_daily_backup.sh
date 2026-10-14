#!/usr/bin/env bash
# One-time: harden the existing PREPODMIN daily backup service.
# Keep data, timer schedule and both bot processes unchanged.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo "Must run as root" >&2; exit 1; }
SRC=/opt/bots/prepodmin/current/deployment/prepodmin
DEST=/usr/local/lib/prepodmin-backup
UNIT=/etc/systemd/system/prepodmin-backup.service
RESTORE=/var/backups/prepodmin/prepodmin-backup.service.before-hardening
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
systemctl is-active --quiet prepodmin-backup.timer
[[ -f "$SRC/daily_backup.py" && -f "$SRC/sqlite_snapshot.py" && -f "$SRC/prepodmin-backup-hardened.service" ]]
[[ -f "$UNIT" && ! -L "$UNIT" && ! -e "$RESTORE" ]] || {
  echo "Backup unit missing, symlinked or already migrated; stop" >&2; exit 1;
}
install -d -o root -g root -m 0700 "$DEST"
install -o root -g root -m 0600 "$SRC/daily_backup.py" "$DEST/daily_backup.py"
install -o root -g root -m 0600 "$SRC/sqlite_snapshot.py" "$DEST/sqlite_snapshot.py"
cp -p "$UNIT" "$RESTORE"
chmod 0600 "$RESTORE"
rollback() {
  result=$?
  trap - ERR
  if (( result != 0 )); then
    cp -p "$RESTORE" "$UNIT"
    systemctl daemon-reload
    echo "PREPODMIN_BACKUP_UNIT_RESTORED" >&2
  fi
  exit "$result"
}
trap rollback ERR
install -o root -g root -m 0644 "$SRC/prepodmin-backup-hardened.service" "$UNIT"
systemctl daemon-reload
systemd-analyze verify prepodmin-backup.service
systemctl start prepodmin-backup.service
systemctl is-active --quiet prepodmin-backup.timer
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
echo PREPODMIN_BACKUP_HARDENED_OK
echo BACKUP_SCRIPT_ROOT_OWNED=yes
echo PREPODMIN_AND_EGE_RUNNING=yes
