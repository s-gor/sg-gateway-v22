#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX="${SG_GATEWAY_PREFIX:-/opt/sg-gateway}"
UNIT_NAME="sg-infosec-management-bridge.service"
UNIT_SOURCE="$PREFIX/deploy/systemd/$UNIT_NAME"
UNIT_LINK="/etc/systemd/system/$UNIT_NAME"
TMPFILES_SOURCE="$PREFIX/deploy/tmpfiles/sg-infosec-management-bridge.conf"
TMPFILES_TARGET="/usr/lib/tmpfiles.d/sg-infosec-management-bridge.conf"
SOURCE_DIR="/etc/sg-infosec/sources.d"
SOURCE_FILE="$SOURCE_DIR/sg-gateway-management.yaml"
CONFIG_FILE="/etc/sg-infosec/sg-infosec.yaml"
CONTROL_SOCKET="/run/sg-infosec/control.sock"
MANAGEMENT_SOCKET="/run/sg-infosec-bridge/management.sock"
BRIDGE_USER="sg-infosec-bridge"
BRIDGE_GROUP="sg-infosec-bridge"
SOURCE_CHANGED=0
SOURCE_BACKUP=""

log() {
  printf '[SG-InfoSec bridge] %s\n' "$*"
}

fail() {
  printf '[SG-InfoSec bridge] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$SOURCE_BACKUP" ]]; then
    rm -f -- "$SOURCE_BACKUP"
  fi
}
trap cleanup EXIT

(( EUID == 0 )) || fail "run as root"
[[ -f "$UNIT_SOURCE" ]] || fail "bridge unit is missing from the deployed release"
[[ -f "$TMPFILES_SOURCE" ]] || fail "bridge tmpfiles contract is missing from the deployed release"
[[ -f "$PREFIX/app/security/sg_infosec_bridge.py" ]] || fail "bridge module is missing from the deployed release"
[[ -x "$PREFIX/.venv/bin/python" ]] || fail "SG-Gateway Python runtime is missing"

if ! getent group sg-gateway >/dev/null; then
  log "sg-gateway group is absent; bridge remains disabled"
  exit 0
fi
if ! getent group sg-infosec >/dev/null || [[ ! -d /etc/sg-infosec ]]; then
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1 || true
  log "SG-InfoSec is not installed; panel will run without management controls"
  exit 0
fi

if ! getent group "$BRIDGE_GROUP" >/dev/null; then
  groupadd --system "$BRIDGE_GROUP"
fi
if ! id -u "$BRIDGE_USER" >/dev/null 2>&1; then
  useradd --system \
    --gid "$BRIDGE_GROUP" \
    --groups sg-infosec,sg-gateway \
    --home-dir /nonexistent \
    --no-create-home \
    --shell /usr/sbin/nologin \
    "$BRIDGE_USER"
else
  usermod -a -G sg-infosec,sg-gateway "$BRIDGE_USER"
fi

install -d -m 0750 -o root -g sg-infosec "$SOURCE_DIR"
SOURCE_CANDIDATE="$(mktemp "$SOURCE_DIR/.sg-gateway-management.XXXXXX")"
cat >"$SOURCE_CANDIDATE" <<'YAML'
source_id: sg-gateway-management
user: sg-infosec-bridge
group: sg-infosec-bridge
allowed_events:
  - auth.failed
allowed_scopes:
  - admin-login
  - admin-api
  - ssh
permissions:
  - read_admin
  - write_admin
YAML
chown root:sg-infosec "$SOURCE_CANDIDATE"
chmod 0640 "$SOURCE_CANDIDATE"

if [[ ! -f "$SOURCE_FILE" ]] || ! cmp -s "$SOURCE_CANDIDATE" "$SOURCE_FILE"; then
  if [[ -f "$SOURCE_FILE" ]]; then
    SOURCE_BACKUP="$(mktemp)"
    cp -a "$SOURCE_FILE" "$SOURCE_BACKUP"
  fi
  mv -f "$SOURCE_CANDIDATE" "$SOURCE_FILE"
  SOURCE_CANDIDATE=""
  SOURCE_CHANGED=1
else
  rm -f -- "$SOURCE_CANDIDATE"
  SOURCE_CANDIDATE=""
fi

restore_source() {
  if [[ -n "$SOURCE_BACKUP" && -f "$SOURCE_BACKUP" ]]; then
    cp -a "$SOURCE_BACKUP" "$SOURCE_FILE"
  else
    rm -f -- "$SOURCE_FILE"
  fi
}

if (( SOURCE_CHANGED )) && [[ -x /usr/local/sbin/sg-infosecd && -f "$CONFIG_FILE" ]]; then
  if ! /usr/local/sbin/sg-infosecd --config "$CONFIG_FILE" --check-config; then
    restore_source
    fail "SG-InfoSec rejected the management source configuration"
  fi
fi

install -m 0644 -o root -g root "$TMPFILES_SOURCE" "$TMPFILES_TARGET"
systemd-tmpfiles --create "$TMPFILES_TARGET"

CURRENT_LINK="$(readlink -f "$UNIT_LINK" 2>/dev/null || true)"
EXPECTED_LINK="$(readlink -f "$UNIT_SOURCE")"
if [[ "$CURRENT_LINK" != "$EXPECTED_LINK" ]]; then
  rm -f -- "$UNIT_LINK"
  systemctl link "$UNIT_SOURCE"
fi
systemctl daemon-reload

if (( SOURCE_CHANGED )) && systemctl is-active --quiet sg-infosec.service; then
  systemctl restart sg-infosec.service
fi

for _attempt in $(seq 1 50); do
  [[ -S "$CONTROL_SOCKET" ]] && break
  sleep 0.1
done
if [[ ! -S "$CONTROL_SOCKET" ]]; then
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1 || true
  log "SG-InfoSec control socket is unavailable; bridge remains stopped"
  exit 0
fi

systemctl restart "$UNIT_NAME"
for _attempt in $(seq 1 50); do
  if systemctl is-active --quiet "$UNIT_NAME" && [[ -S "$MANAGEMENT_SOCKET" ]]; then
    log "management bridge is active"
    exit 0
  fi
  sleep 0.1
done

systemctl --no-pager --full status "$UNIT_NAME" >&2 || true
fail "management bridge did not create its Unix socket"
