#!/usr/bin/env bash
# Read-only Timeweb preflight for EGE BLIZKO laboratory.
# No deployment, backups, commits, secrets, database access or restarts.
set -u
export GIT_OPTIONAL_LOCKS=0
APP_DIR="${EGE_APP_DIR:-/opt/bots/ege-blizko}"
BOT_SERVICE="${EGE_SERVICE:-ege-blizko}"
AUTODEPLOY_SERVICE="ege-blizko-autodeploy.service"
AUTODEPLOY_TIMER="ege-blizko-autodeploy.timer"
AUTODEPLOY_STATE="/var/lib/ege-blizko-autodeploy"
HEALTH_URL="https://77-233-212-200.sslip.io/health"

line() { printf '%s=%s\n' "$1" "$2"; }
service_property() {
  local name="$1" property="$2" value
  value="$(systemctl show "$name" --property="$property" --value 2>/dev/null)" || value="unavailable"
  line "$name.$property" "${value:-unavailable}"
}

echo "=== EGE BLIZKO READ-ONLY SERVER PREFLIGHT ==="
line "preflight_mode" "READ_ONLY"
line "timestamp_utc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
line "application_exists" "$([ -d "$APP_DIR" ] && echo yes || echo no)"
line "service" "$BOT_SERVICE"
service_property "$BOT_SERVICE" "ActiveState"
service_property "$BOT_SERVICE" "SubState"
service_property "$BOT_SERVICE" "UnitFileState"
service_property "$AUTODEPLOY_SERVICE" "ActiveState"
service_property "$AUTODEPLOY_TIMER" "ActiveState"
service_property "$AUTODEPLOY_TIMER" "UnitFileState"

if [ -d "$APP_DIR/.git" ] || [ -f "$APP_DIR/.git" ]; then
  line "git_head" "$(git -C "$APP_DIR" rev-parse --verify HEAD 2>/dev/null || echo unavailable)"
  line "git_branch" "$(git -C "$APP_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || echo detached)"
  dirty="$(git -C "$APP_DIR" -c core.fsmonitor=false status --porcelain=v1 --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')" || dirty="unavailable"
  line "tracked_modified_files_count" "$dirty"
  # Never print .git/config, any remote credential, or a secrets file.
else
  line "git_head" "not_a_git_checkout"
fi

if [ -r "$AUTODEPLOY_STATE/release.ref" ]; then
  line "last_successful_release_marker" "$(head -c 256 "$AUTODEPLOY_STATE/release.ref" | tr -d '\r\n')"
else
  line "last_successful_release_marker" "missing_or_unreadable"
fi
if [ -r "$AUTODEPLOY_STATE/failed.ref" ]; then
  line "last_failed_release_marker" "$(head -c 256 "$AUTODEPLOY_STATE/failed.ref" | tr -d '\r\n')"
else
  line "last_failed_release_marker" "none_or_unreadable"
fi

if [ -f "$APP_DIR/deploy/timeweb-autodeploy.sh" ]; then
  line "auto_deploy_script_present" "yes"
else
  line "auto_deploy_script_present" "no"
fi
# Health request is GET-only; capture HTTP status, not response body or auth info.
health_status="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 "$HEALTH_URL" 2>/dev/null)" || health_status="unavailable"
line "public_health_http" "$health_status"
# Disk/free space are only informational. No files are written.
if [ -d "$APP_DIR" ]; then
  line "available_disk_kb" "$(df -Pk "$APP_DIR" 2>/dev/null | awk 'NR==2{print $4}' | head -n 1)"
fi
echo "=== END READ-ONLY PREFLIGHT ==="
