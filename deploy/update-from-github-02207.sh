#!/usr/bin/env bash
set -Eeuo pipefail
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo 'run through sudo' >&2; exit 1; }
[[ "$BRANCH" == "dev-02207" || "$BRANCH" == feature/02207-* ]] || { echo "22.07 updater refuses branch $BRANCH" >&2; exit 1; }
SG_GATEWAY_GITHUB_BRANCH="$BRANCH" bash /opt/sg-gateway/deploy/update-from-github.sh
SG_GATEWAY_SOURCE_ROOT=/opt/sg-gateway bash /opt/sg-gateway/deploy/install-naiveproxy.sh
if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then ufw allow 8447/tcp; fi
printf '[SG-Gateway 22.07] Update and NaiveProxy runtime transaction completed.\n'
