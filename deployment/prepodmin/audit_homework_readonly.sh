#!/usr/bin/env bash
# PREPODMIN — production homework readiness audit (READ-ONLY).
# Never install packages, create files, change environment, restart, reload,
# snapshot, fetch repositories, read user work contents, or change EGE BLIZKO.
# Run over a trusted root SSH session by streaming stdin to "bash -s".
set -uo pipefail
export LC_ALL=C
echo "PREPODMIN_HOMEWORK_READONLY_AUDIT_V1"
report() { printf '%s=%s\n' "$1" "$2"; }
check() { local key="$1"; shift; if "$@" >/dev/null 2>&1; then report "$key" OK; else report "$key" NOT_CONFIRMED; fi; }
owner_mode() {
  local dir="$1" owner="$2" mode="$3"
  [[ -d "$dir" && ! -L "$dir" ]] || return 1
  [[ "$(stat -c %U "$dir")" == "$owner" && "$(stat -c %a "$dir")" == "$mode" ]]
}
private_db() {
  local p=/opt/bots/prepodmin/data/teacher_product.sqlite3
  [[ -f "$p" && ! -L "$p" ]] || return 1
  [[ "$(stat -c %U "$p")" == "prepodmin" ]]
}
free_space() {
  local path=/opt/bots/prepodmin/data
  [[ -d "$path" ]] || return 1
  local free
  free="$(df -PB1 "$path" | awk 'NR==2 {print $4}')"
  [[ "$free" =~ ^[0-9]+$ ]] && (( free > 2147483648 ))
}
local_backup_dir() {
  local p=/var/backups/prepodmin/daily
  [[ -d "$p" && ! -L "$p" ]] || return 1
  [[ "$(stat -c %U "$p")" == root && "$(stat -c %a "$p")" == 700 ]]
}
has_backup_files() {
  local p=/var/backups/prepodmin/daily
  [[ -d "$p" ]] || return 1
  find "$p" -maxdepth 1 -type f -name 'prepodmin-daily-*.sqlite3' -print -quit | grep -q .
}
uploads_disabled() {
  local p=/etc/prepodmin/prepodmin.env
  [[ -f "$p" ]] || return 1
  # Do not show environment contents or tokens; flag is ON only if explicit 1.
  ! grep -Eq '^[[:space:]]*TEACHER_PRODUCT_HOMEWORK_UPLOADS_ENABLED[[:space:]]*=[[:space:]]*1[[:space:]]*(#.*)?$' "$p"
}
read_nginx() {
  command -v nginx >/dev/null 2>&1 || return 1
  NGINX_TEXT="$(nginx -T 2>/dev/null)" || return 1
  return 0
}
nginx_has() { [[ "$NGINX_TEXT" == *"$1"* ]]; }
echo "-- services and database --"
check PREPODMIN_ACTIVE systemctl is-active --quiet prepodmin
check EGE_BLIZKO_ACTIVE systemctl is-active --quiet ege-blizko
check PREPODMIN_SQLITE_OWNER private_db
check PREPODMIN_HTTP_HEALTH curl --fail --silent --show-error --max-time 5 -o /dev/null http://127.0.0.1:8091/health
check PREPODMIN_HTTPS_WEBAPP curl --fail --silent --show-error --max-time 8 -o /dev/null https://prepodmin.77-233-212-200.sslip.io/webapp
echo "-- backups --"
check PREPODMIN_DAILY_BACKUP_TIMER_ACTIVE systemctl is-active --quiet prepodmin-backup.timer
check PREPODMIN_DAILY_BACKUP_DIR_PRIVATE local_backup_dir
check PREPODMIN_DAILY_SQLITE_BACKUP_PRESENT has_backup_files
report OFFSITE_ENCRYPTED_SQLITE_AND_FILE_BACKUP "NOT_VERIFIABLE_BY_THIS_AUDIT"
report OFFSITE_RESTORE_TEST "NOT_VERIFIABLE_BY_THIS_AUDIT"
echo "-- homework files --"
check HOMEWORK_PRIVATE_DIR_READY owner_mode /opt/bots/prepodmin/data/homework_uploads prepodmin 700
check PREPODMIN_DATA_DISK_FREE_OVER_2G free_space
check FILE_UPLOAD_FLAG_NOT_ENABLED uploads_disabled
echo "-- Nginx (read only; no reload) --"
check NGINX_CONFIG_SYNTAX nginx -t
NGINX_TEXT=""
if read_nginx; then
  check PREPODMIN_VHOST_PRESENT nginx_has "server_name prepodmin.77-233-212-200.sslip.io;"
  check UPLOAD_LOCATION_PRESENT nginx_has "location = /api/student/homework/upload"
  check SIGNED_FILE_LOCATION_PRESENT nginx_has "location ^~ /api/teacher/homework/file/"
  check NGINX_SIGNED_FILE_LOG_POLICY_NEEDS_MANUAL_REVIEW nginx_has "access_log off;"
else
  report NGINX_CONFIG_READ "NOT_CONFIRMED"
fi
unset NGINX_TEXT
echo "-- release safety --"
report HTTP_UPLOAD_REAL_FILE_TEST "NOT_RUN_ON_PRODUCTION"
report STUDENT_DATA_CONTENTS "NOT_READ"
report FILES_OR_SERVICES_MODIFIED "NO"
report READY_TO_ENABLE_UPLOADS "NO_MANUAL_REVIEW_AND_BACKUPS_REQUIRED"
echo "PREPODMIN_HOMEWORK_READONLY_AUDIT_COMPLETE"
