#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="s-gor/sg-gateway-v22"
SOURCE_SHA="${SG_GATEWAY_SOURCE_COMMIT:-${1:-}}"
BRANCH="${SG_GATEWAY_UPDATE_BRANCH:-feature/sg-infosec-complete-ui}"
RAW_BASE="${SG_GATEWAY_RAW_BASE_URL:-https://raw.githubusercontent.com/${REPOSITORY}}"
PREFIX="${SG_GATEWAY_PREFIX:-/opt/sg-gateway}"
PANEL_UNIT="/etc/systemd/system/sg-gateway.service"
PANEL_SERVICE="sg-gateway.service"
BRIDGE_SERVICE="sg-infosec-management-bridge.service"
BRIDGE_SOURCE="/etc/sg-infosec/sources.d/sg-gateway-management.yaml"
BRIDGE_UNIT="/etc/systemd/system/sg-infosec-management-bridge.service"
BRIDGE_TMPFILES="/usr/lib/tmpfiles.d/sg-infosec-management-bridge.conf"
TEMP_DIR=""
BACKUP_DIR=""
INTEGRATION_STARTED=0
INTEGRATION_FINISHED=0

fail() {
    printf '[SG-Gateway + SG InfoSec] ERROR: %s\n' "$*" >&2
    exit 1
}

restore_path() {
    local absolute="$1" relative="${1#/}"
    rm -rf -- "$absolute"
    if grep -Fxq "$relative" "$BACKUP_DIR/existing-paths.txt"; then
        tar -C / -xpf "$BACKUP_DIR/integration-state.tar" "$relative"
    fi
}

rollback_integration() {
    (( INTEGRATION_STARTED == 1 && INTEGRATION_FINISHED == 0 )) || return 0
    printf '[SG-Gateway + SG InfoSec] Restoring pre-integration service state...\n' >&2
    systemctl stop "$PANEL_SERVICE" "$BRIDGE_SERVICE" >/dev/null 2>&1 || true
    restore_path "$PANEL_UNIT"
    restore_path "$BRIDGE_SOURCE"
    restore_path "$BRIDGE_UNIT"
    restore_path "$BRIDGE_TMPFILES"
    systemctl daemon-reload >/dev/null 2>&1 || true
    if systemctl is-active --quiet sg-infosec.service; then
        systemctl restart sg-infosec.service >/dev/null 2>&1 || true
    fi
    systemctl start "$PANEL_SERVICE" >/dev/null 2>&1 || true
}

cleanup() {
    local status=$?
    set +e
    if (( status != 0 )); then
        rollback_integration
    fi
    [[ -z "$TEMP_DIR" ]] || rm -rf -- "$TEMP_DIR"
    exit "$status"
}
trap cleanup EXIT

[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || \
    fail "source commit must be a full lowercase 40-character SHA"
(( EUID == 0 )) || fail "run as root"
for command in curl bash python3 tar systemctl; do
    command -v "$command" >/dev/null 2>&1 || fail "required command is missing: $command"
done
[[ -f "$PREFIX/VERSION" && -f "$PANEL_UNIT" ]] || \
    fail "SG-Gateway is not installed"

TEMP_DIR="$(mktemp -d /tmp/sg-gateway-infosec-update.XXXXXX)"
CORE="$TEMP_DIR/update-from-github-core.sh"

printf '[SG-Gateway + SG InfoSec] Updating pinned SG-Gateway source: %s\n' "$SOURCE_SHA"
curl -4 -fL --retry 6 --retry-all-errors --retry-delay 2 --connect-timeout 20 \
    "$RAW_BASE/$SOURCE_SHA/deploy/update-from-github-core.sh" -o "$CORE"
[[ -s "$CORE" ]] || fail "downloaded core updater is empty"
grep -Fq 'SG_GATEWAY_UPDATE_CORE' "$CORE" || fail "downloaded file is not the SG-Gateway core updater"
bash -n "$CORE" || fail "downloaded core updater failed syntax validation"

SG_GATEWAY_SOURCE_COMMIT="$SOURCE_SHA" \
SG_GATEWAY_UPDATE_BRANCH="$BRANCH" \
    bash "$CORE"

[[ -x "$PREFIX/deploy/install-sg-infosec-management-bridge.sh" ]] || \
    fail "deployed SG InfoSec bridge installer is missing"
[[ -f "$PREFIX/app/security/sg_infosec_unit_migration.py" ]] || \
    fail "deployed panel unit migration is missing"
[[ -S /run/sg-infosec/control.sock ]] || \
    fail "SG InfoSec control socket is unavailable; install SG InfoSec first"

BACKUP_DIR="$(mktemp -d /root/sg-gateway-update-safety/$(date -u +%Y%m%d-%H%M%S)-before-infosec-integration.XXXXXX)"
chmod 0700 "$BACKUP_DIR"
: > "$BACKUP_DIR/existing-paths.txt"
existing=()
for path in "$PANEL_UNIT" "$BRIDGE_SOURCE" "$BRIDGE_UNIT" "$BRIDGE_TMPFILES"; do
    if [[ -e "$path" || -L "$path" ]]; then
        relative="${path#/}"
        printf '%s\n' "$relative" >> "$BACKUP_DIR/existing-paths.txt"
        existing+=("$relative")
    fi
done
if (( ${#existing[@]} > 0 )); then
    tar -C / -cpf "$BACKUP_DIR/integration-state.tar" "${existing[@]}"
else
    tar -C / -cpf "$BACKUP_DIR/integration-state.tar" --files-from /dev/null
fi
INTEGRATION_STARTED=1

printf '[SG-Gateway + SG InfoSec] Activating management bridge and web guard...\n'
systemctl stop "$PANEL_SERVICE"
PYTHONPATH="$PREFIX" \
    "$PREFIX/.venv/bin/python" -B -m app.security.sg_infosec_unit_migration \
    "$PANEL_UNIT"
systemctl daemon-reload
"$PREFIX/deploy/install-sg-infosec-management-bridge.sh"
systemctl restart "$PANEL_SERVICE"

for _attempt in $(seq 1 60); do
    if systemctl is-active --quiet "$PANEL_SERVICE" && \
       curl -fsS --max-time 2 http://127.0.0.1:18080/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done
systemctl is-active --quiet "$PANEL_SERVICE" || fail "panel did not restart"
curl -fsS --max-time 3 http://127.0.0.1:18080/health >/dev/null || \
    fail "panel health check failed"
systemctl is-active --quiet "$BRIDGE_SERVICE" || fail "SG InfoSec management bridge is not active"
[[ -S /run/sg-infosec-bridge/management.sock ]] || \
    fail "SG InfoSec management socket was not created"

environment="$(systemctl show -p Environment --value "$PANEL_SERVICE")"
for expected in \
    SG_INFOSEC_GUARD_SETTINGS=/var/lib/sg-gateway/infosec/guard.json \
    SG_INFOSEC_REPUTATION_FILE=/var/lib/sg-gateway/infosec/reputation.json \
    SG_INFOSEC_ALERTS_FILE=/var/lib/sg-gateway/infosec/alerts.jsonl; do
    [[ " $environment " == *" $expected "* ]] || \
        fail "panel did not load $expected"
done

INTEGRATION_FINISHED=1
printf '[SG-Gateway + SG InfoSec] Complete integration installed.\n'
printf '[SG-Gateway + SG InfoSec] SG-Gateway commit: %s\n' "$SOURCE_SHA"
printf '[SG-Gateway + SG InfoSec] Integration backup: %s\n' "$BACKUP_DIR"
