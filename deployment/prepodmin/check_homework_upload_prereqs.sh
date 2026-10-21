#!/usr/bin/env bash
# PREPODMIN homework storage preflight. READ ONLY: does not modify services,
# Nginx, users, data, backup, flags or the EGE BLIZKO working tree.
set -Eeuo pipefail
STORAGE_DIR="/opt/bots/prepodmin/data/homework_uploads"
if (( $# >= 1 )); then STORAGE_DIR="$1"; fi
ERRORS=0
check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK %s\n' "$label"
  else
    printf 'BLOCKED %s\n' "$label"
    ERRORS=$((ERRORS+1))
  fi
}
check_active() { systemctl is-active --quiet "$1"; }
check_dir() {
  [[ "$STORAGE_DIR" == /* && -d "$STORAGE_DIR" && ! -L "$STORAGE_DIR" ]] || return 1
  [[ "$(stat -c %U "$STORAGE_DIR")" == "prepodmin" ]] || return 1
  [[ "$(stat -c %a "$STORAGE_DIR")" == "700" ]] || return 1
}
check_free() {
  [[ -d "$STORAGE_DIR" ]] || return 1
  local free
  free="$(df -PB1 "$STORAGE_DIR" | awk 'NR==2{print $4}')"
  [[ "$free" =~ ^[0-9]+$ ]] && (( free >= 2147483648 ))
}
check_nginx() { nginx -t >/dev/null 2>&1; }
check_routes() {
  # Avoid printing the contents of loaded Nginx config (potential secrets).
  local config
  config="$(nginx -T 2>/dev/null)" || return 1
  grep -Fq 'server_name prepodmin.77-233-212-200.sslip.io;' <<<"$config" &&
  grep -Fq 'location = /api/student/homework/upload' <<<"$config" &&
  grep -Fq 'location ^~ /api/teacher/homework/file/' <<<"$config"
}
check "PREPODMIN service active" check_active prepodmin
check "EGE BLIZKO untouched and active" check_active ege-blizko
check "Private upload directory: owner prepodmin, mode 0700" check_dir
check "At least 2 GiB free disk space" check_free
check "Nginx syntax valid (no reload)" check_nginx
check "Homework routes in active Nginx configuration" check_routes
if (( ERRORS )); then
  echo "PREPODMIN_HOMEWORK_FILES_NOT_READY failures=$ERRORS"
  exit 2
fi
echo "PREPODMIN_HOMEWORK_BASIC_READONLY_CHECK_OK"
echo "STILL REQUIRED: off-server encrypted backup & real restore test;"
echo "manual vhost review (access_log off on signed file URLs); privacy review;"
echo "real uploads tested on staging; and separate owner release approval."
# A successful preflight is NOT authorization to enable uploads or deploy.
