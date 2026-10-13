#!/usr/bin/env bash
# PREPODMIN-only HTTPS installer. Keeps the EGE BLIZKO vhost unchanged.
# Adds a new vhost file and rolls it back on any verification failure.
set -euo pipefail

DOMAIN="prepodmin.77-233-212-200.sslip.io"
AVAILABLE="/etc/nginx/sites-available/prepodmin-https"
ENABLED="/etc/nginx/sites-enabled/prepodmin-https"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: must run as root" >&2
    exit 1
fi
if [[ -e "$AVAILABLE" || -L "$AVAILABLE" || -e "$ENABLED" || -L "$ENABLED" ]]; then
    echo "ERROR: PREPODMIN HTTPS site already exists. No changes made." >&2
    exit 1
fi
test -s "/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
test -s "/etc/letsencrypt/live/$DOMAIN/privkey.pem"
systemctl is-active --quiet nginx
systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
nginx -t

LOCAL_RESPONSE="$(curl --noproxy '*' --silent --show-error --fail --max-time 5 http://127.0.0.1:8091/health)"
if [[ "$LOCAL_RESPONSE" != *'"service":"teacher-product-mvp"'* || "$LOCAL_RESPONSE" != *'"ok":true'* ]]; then
    echo "ERROR: local PREPODMIN health response unexpected; no Nginx changes made." >&2
    exit 1
fi

COMMITTED=0
rollback() {
    if [[ "$COMMITTED" == 0 ]]; then
        rm -f -- "$ENABLED" "$AVAILABLE"
        if nginx -t >/dev/null 2>&1; then
            systemctl reload nginx >/dev/null 2>&1 || true
        fi
        echo "PREPODMIN_HTTPS_ROLLED_BACK" >&2
    fi
}
trap rollback EXIT

install -o root -g root -m 0644 "$HERE/nginx-https.conf" "$AVAILABLE"
ln -s "$AVAILABLE" "$ENABLED"
nginx -t
systemctl reload nginx

SUCCESS=0
LAST_RESPONSE=""
for attempt in $(seq 1 15); do
    LAST_RESPONSE="$(curl --noproxy '*' --silent --show-error --max-time 5 \
        --resolve "$DOMAIN:443:127.0.0.1" \
        --write-out '\nHTTP_STATUS:%{http_code}' \
        "https://$DOMAIN/health" 2>&1)" || true
    if [[ "$LAST_RESPONSE" == *'HTTP_STATUS:200'* && "$LAST_RESPONSE" == *'"service":"teacher-product-mvp"'* ]]; then
        SUCCESS=1
        break
    fi
    sleep 1
done
if [[ "$SUCCESS" != 1 ]]; then
    echo "ERROR: HTTPS health failed after retry: $LAST_RESPONSE" >&2
    tail -n 15 /var/log/nginx/prepodmin-https-error.log 2>/dev/null >&2 || true
    exit 1
fi

for path in /webapp /student; do
    CODE="$(curl --noproxy '*' --silent --show-error --max-time 8 \
        --resolve "$DOMAIN:443:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' \
        "https://$DOMAIN$path")"
    if [[ "$CODE" != "200" ]]; then
        echo "ERROR: HTTPS $path returned status $CODE" >&2
        exit 1
    fi
done

# HTTP must not serve either of the sensitive front-end endpoints.
for path in /webapp /student; do
    CODE="$(curl --noproxy '*' --silent --show-error --max-time 8 \
        --resolve "$DOMAIN:80:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' \
        "http://$DOMAIN$path")"
    if [[ "$CODE" != "404" ]]; then
        echo "ERROR: insecure HTTP $path returned $CODE, expected 404" >&2
        exit 1
    fi
done

systemctl is-active --quiet prepodmin
systemctl is-active --quiet ege-blizko
COMMITTED=1
trap - EXIT
printf 'PREPODMIN_HTTPS_READY\n'
printf 'URL=https://%s\n' "$DOMAIN"
printf 'HTTPS_HEALTH=200\n'
printf 'HTTPS_TEACHER_CABINET=200\n'
printf 'HTTPS_STUDENT_CABINET=200\n'
printf 'PUBLIC_HTTP_WEBAPPS=blocked\n'
printf 'PREPODMIN=active\n'
printf 'EGE_BLIZKO=active\n'
printf 'TELEGRAM_POLLING=unchanged\n'
