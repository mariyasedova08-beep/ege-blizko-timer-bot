#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/bots/ege-blizko"

install -m 0755 "$APP_DIR/deploy/timeweb-autodeploy.sh" /usr/local/sbin/ege-blizko-autodeploy
install -m 0644 "$APP_DIR/deploy/ege-blizko-autodeploy.service" /etc/systemd/system/ege-blizko-autodeploy.service
install -m 0644 "$APP_DIR/deploy/ege-blizko-autodeploy.timer" /etc/systemd/system/ege-blizko-autodeploy.timer

mkdir -p /var/lib/ege-blizko-autodeploy
systemctl daemon-reload
systemctl enable --now ege-blizko-autodeploy.timer

# Deploy the current marked release immediately, then show a compact status.
rm -f /var/lib/ege-blizko-autodeploy/release.ref /var/lib/ege-blizko-autodeploy/failed.ref
systemctl start ege-blizko-autodeploy.service
systemctl is-active ege-blizko
systemctl is-active ege-blizko-autodeploy.timer
curl -fsS https://77-233-212-200.sslip.io/health
