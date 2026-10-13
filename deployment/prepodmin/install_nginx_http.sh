#!/usr/bin/env bash
# PREPODMIN only: install its own HTTP vhost, test Nginx and roll back on errors.
# This script never edits the existing EGE BLIZKO Nginx configuration.
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
curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:8091/health | grep -Fq '"ok":true'

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
RESPONSE="$(curl --noproxy '*' -fsS --max-time 10 --resolve "$DOMAIN:80:127.0.0.1" "http://$DOMAIN/health")"
if [[ "$RESPONSE" != *'"ok":true'* ]]; then
  echo "ERROR: PREPODMIN /health failed behind Nginx" >&2
  exit 1
fi
systemctl is-active --quiet ege-blizko
systemctl is-active --quiet prepodmin
COMMITTED=1
trap - EXIT
printf 'PREPODMIN_HTTP_PROXY_READY\n'
printf 'Host: http://%s/health\n' "$DOMAIN"
printf 'Response: %s\n' "$RESPONSE"
printf 'EGE_BLIZKO=active\n'
printf 'PREPODMIN=active\n'
printf 'HTTPS_NOT_YET_CONFIGURED\n'
