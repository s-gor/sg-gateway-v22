#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'root required' >&2; exit 1; }
systemctl disable --now sg-gateway-naiveproxy.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/sg-gateway-naiveproxy.service
systemctl daemon-reload
rm -rf /opt/sg-gateway/naiveproxy /etc/sg-gateway/naiveproxy
# State is intentionally retained for backup/restore and explicit recovery.
echo '[SG-Gateway] NaiveProxy runtime removed; state retained in /var/lib/sg-gateway/naiveproxy'
