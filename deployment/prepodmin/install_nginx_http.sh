#!/usr/bin/env bash
# PREPODMIN only: install the HTTP-only bootstrap vhost, test and roll back on error.
# Never edits the existing EGE BLIZKO Nginx configuration.
set -euo pipefail

DOMAIN="prepodmin.77-233-212-200.sslip.io"
SITE_NAME="prepodmin"
AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" != "0" ]]; then
  echo "ERROR: run this installer as root" >&2
  exit 1
fi
if [[ -e "$AVAILABLE" || -e "$ENABLED" || -L "$ENABLED" ]]; then
  echo "ERROR: PREPODMIN Nginx site already exists. No changes made." >&2
  exit 1
fi
systemctl is-active --quiet nginx
systemctl is-active --quiet ege-blizko
systemctl is-active --quiet prepodmin
nginx -t
LOCAL="$(curl --noproxy '*' --silent --show-error --fail --max-time 5 http://127.0.0.1:8091/health)"
if [[ "$LOCAL" != *'"ok":true'* || "$LOCAL" != *'"service":"teacher-product-mvp"'* ]]; then
  echo "ERROR: PREPODMIN local /health is unexpected; no Nginx changes made." >&2
  exit 1
fi

if nginx -T 2>/dev/null | grep -Fq "server_name $DOMAIN;"; then
  echo "ERROR: this hostname is already configured in Nginx. No changes made." >&2
  exit 1
fi

COMMITTED=0
rollback() {
  if [[ "$COMMITTED" == "0" ]]; then
    rm -f -- "$ENABLED"
    rm -f -- "$AVAILABLE"
    if nginx -t >/dev/null 2>&1; then
      systemctl reload nginx >/dev/null 2>&1 || true
    fi
    echo "PREPODMIN_HTTP_PROXY_ROLLED_BACK" >&2
  fi
}
trap rollback EXIT

install -o root -g root -m 0644 "$HERE/nginx-http.conf" "$AVAILABLE"
ln -s "$AVAILABLE" "$ENABLED"
nginx -t
systemctl reload nginx

# nginx -t and systemctl reload may complete before all old worker connections
# have drained. Retry the new hostname instead of treating the first 404 as final.
# /health is the only published HTTP endpoint; WebApps remain blocked until TLS.
SUCCESS=0
LAST_RESPONSE=""
for attempt in $(seq 1 15); do
  LAST_RESPONSE="$(curl --noproxy '*' --silent --show-error --max-time 5 \
    --resolve "$DOMAIN:80:127.0.0.1" \
    --write-out '\nHTTP_STATUS:%{http_code}' \
    "http://$DOMAIN/health" 2>&1)" || true
  if [[ "$LAST_RESPONSE" == *'HTTP_STATUS:200'* && "$LAST_RESPONSE" == *'"service":"teacher-product-mvp"'* ]]; then
    SUCCESS=1
    break
  fi
  sleep 1
done
if [[ "$SUCCESS" != "1" ]]; then
  echo "ERROR: PREPODMIN hostname still fails after 15 checks: $LAST_RESPONSE" >&2
  echo "PREPODMIN access-log tail:" >&2
  tail -n 8 /var/log/nginx/prepodmin-access.log 2>/dev/null >&2 || true
  echo "PREPODMIN error-log tail:" >&2
  tail -n 8 /var/log/nginx/prepodmin-error.log 2>/dev/null >&2 || true
  exit 1
fi

# Prove that protected WebApps are NOT available without HTTPS.
WEBAPP_STATUS="$(curl --noproxy '*' --silent --max-time 5 --output /dev/null \
  --write-out '%{http_code}' --resolve "$DOMAIN:80:127.0.0.1" "http://$DOMAIN/webapp")"
if [[ "$WEBAPP_STATUS" != "404" ]]; then
  echo "ERROR: unencrypted HTTP /webapp must be blocked (status=$WEBAPP_STATUS)" >&2
  exit 1
fi

systemctl is-active --quiet ege-blizko
systemctl is-active --quiet prepodmin
COMMITTED=1
trap - EXIT
printf 'PREPODMIN_HTTP_PROXY_READY\n'
printf 'Host: http://%s/health\n' "$DOMAIN"
printf 'Response: %s\n' "$LAST_RESPONSE"
printf 'EGE_BLIZKO=active\n'
printf 'PREPODMIN=active\n'
printf 'PUBLIC_HTTP_WEBAPPS=blocked\n'
printf 'HTTPS_NOT_YET_CONFIGURED\n'
