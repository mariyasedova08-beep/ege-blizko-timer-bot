#!/usr/bin/env bash
# PREPODMIN only. Install daily SQLite backup timer on Timeweb.
# Existing backups are never overwritten or deleted by this installer.
set -euo pipefail

BASE="/opt/bots/prepodmin/current/deployment/prepodmin"
SERVICE="/etc/systemd/system/prepodmin-backup.service"
TIMER="/etc/systemd/system/prepodmin-backup.timer"

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: run as root" >&2; exit 1
fi
if [[ -e "$SERVICE" || -e "$TIMER" ]]; then
  echo "ERROR: PREPODMIN backup unit or timer already exists; refusing to replace." >&2
  exit 1
fi
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
test -s /opt/bots/prepodmin/data/teacher_product.sqlite3
test -r "$BASE/daily_backup.py"
test -r "$BASE/sqlite_snapshot.py"
test -r "$BASE/prepodmin-backup.service.example"
test -r "$BASE/prepodmin-backup.timer.example"
systemd-analyze calendar '*-*-* 01:30:00 UTC' >/dev/null
install -d -o root -g root -m 0700 /var/backups/prepodmin /var/backups/prepodmin/daily
install -o root -g root -m 0644 "$BASE/prepodmin-backup.service.example" "$SERVICE"
install -o root -g root -m 0644 "$BASE/prepodmin-backup.timer.example" "$TIMER"
systemctl daemon-reload

# Validate the first daily snapshot before activating future automatic runs.
systemctl start prepodmin-backup.service
systemctl enable --now prepodmin-backup.timer

systemctl is-active --quiet prepodmin-backup.timer
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
echo PREPODMIN_DAILY_BACKUP_READY
echo BACKUP_DIR=/var/backups/prepodmin/daily
echo LOCAL_RETENTION=30_days
echo SCHEDULE='01:30 UTC daily (04:30 Moscow)'
echo OFFSITE_SYNC=not_configured
systemctl list-timers prepodmin-backup.timer --no-pager --no-legend
echo PREPODMIN=active
echo EGE_BLIZKO=active
