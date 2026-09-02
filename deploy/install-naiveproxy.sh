#!/usr/bin/env bash
set -Eeuo pipefail

RUNTIME_VERSION="v2.11.2-naive"
RUNTIME_ARCHIVE_SHA256="19eccb7321dd877a5fb4a3dba6ef1b745185188b616c96cc6201f1a1fc0380a8"
RUNTIME_URL="https://github.com/klzgrad/forwardproxy/releases/download/${RUNTIME_VERSION}/caddy-forwardproxy-naive.tar.xz"
PREFIX="/opt/sg-gateway/naiveproxy"
CONFIG_DIR="/etc/sg-gateway/naiveproxy"
PANEL_CONFIG_DIR="/etc/sg-gateway"
STATE_DIR="/var/lib/sg-gateway/naiveproxy"
SERVICE="sg-gateway-naiveproxy.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE"
HOSTD_SERVICE="sg-hostd.service"
HOSTD_SERVICE_PATH="/etc/systemd/system/$HOSTD_SERVICE"
PANEL_SERVICE="sg-gateway.service"
PANEL_ENV="/etc/sg-gateway/sg-gateway.env"
UPDATE_BRANCH="${SG_GATEWAY_UPDATE_BRANCH:-}"
SOURCE_ROOT="${SG_GATEWAY_SOURCE_ROOT:-/opt/sg-gateway}"
TX_DIR=""
PANEL_CONFIG_MODE=""
INSTALL_OK=0
HAD_PREFIX=0
HAD_CONFIG=0
HAD_STATE=0
HAD_UNIT=0
HAD_HOSTD_UNIT=0
HAD_PANEL_ENV=0
HAD_USER=0
HAD_GROUP=0
WAS_ACTIVE=0
WAS_ENABLED=0
HOSTD_WAS_ACTIVE=0
HOSTD_WAS_ENABLED=0
PANEL_WAS_ACTIVE=0
PANEL_WAS_ENABLED=0

log() { printf '[SG-Gateway] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; return 1; }

snapshot_path() {
  local source="$1" name="$2" flag="$3"
  if [[ -e "$source" || -L "$source" ]]; then
    cp -a -- "$source" "$TX_DIR/$name"
    printf -v "$flag" '%s' 1
  fi
}

restore_path() {
  local target="$1" name="$2" existed="$3"
  rm -rf -- "$target"
  if (( existed == 1 )); then
    mkdir -p -- "$(dirname "$target")"
    cp -a -- "$TX_DIR/$name" "$target"
  fi
}

restore_service_state() {
  local service="$1" enabled="$2" active="$3"
  if (( enabled == 1 )); then
    systemctl enable "$service" >/dev/null 2>&1 || true
  else
    systemctl disable "$service" >/dev/null 2>&1 || true
  fi
  if (( active == 1 )); then
    systemctl restart "$service" >/dev/null 2>&1 || true
  else
    systemctl stop "$service" >/dev/null 2>&1 || true
  fi
}

persist_update_channel() {
  [[ -n "$UPDATE_BRANCH" ]] || return 0
  [[ "$UPDATE_BRANCH" == "dev-02207" || "$UPDATE_BRANCH" == feature/02207-* ]] || \
    die "Refusing invalid 22.07 update channel: $UPDATE_BRANCH"
  [[ -f "$PANEL_ENV" ]] || die "Panel environment is missing: $PANEL_ENV"
  python3 - "$PANEL_ENV" "$UPDATE_BRANCH" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
branch = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
key = "SG_GATEWAY_UPDATE_BRANCH"
replacement = f"{key}={branch}"
updated = []
found = False
for line in lines:
    raw_key, separator, _value = line.partition("=")
    if separator and raw_key.strip() == key:
        if not found:
            updated.append(replacement)
            found = True
        continue
    updated.append(line)
if not found:
    updated.append(replacement)
stat = path.stat()
fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
temporary = Path(raw)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("\n".join(updated) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
    os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
PY
}

cleanup() {
  [[ -z "$TX_DIR" ]] || rm -rf -- "$TX_DIR"
}

rollback_install() {
  local rc=$?
  trap - ERR
  if (( INSTALL_OK == 0 )) && [[ -n "$TX_DIR" ]]; then
    log "NaiveProxy install failed; restoring previous runtime state"
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    restore_path "$PREFIX" prefix "$HAD_PREFIX"
    restore_path "$CONFIG_DIR" config "$HAD_CONFIG"
    restore_path "$STATE_DIR" state "$HAD_STATE"
    restore_path "$SERVICE_PATH" unit "$HAD_UNIT"
    restore_path "$HOSTD_SERVICE_PATH" hostd-unit "$HAD_HOSTD_UNIT"
    restore_path "$PANEL_ENV" panel-env "$HAD_PANEL_ENV"
    if [[ -n "$PANEL_CONFIG_MODE" && -d "$PANEL_CONFIG_DIR" ]]; then
      chmod "$PANEL_CONFIG_MODE" "$PANEL_CONFIG_DIR" || true
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
    restore_service_state "$HOSTD_SERVICE" "$HOSTD_WAS_ENABLED" "$HOSTD_WAS_ACTIVE"
    restore_service_state "$PANEL_SERVICE" "$PANEL_WAS_ENABLED" "$PANEL_WAS_ACTIVE"
    restore_service_state "$SERVICE" "$WAS_ENABLED" "$WAS_ACTIVE"
    if (( HAD_USER == 0 )); then
      userdel sg-naiveproxy >/dev/null 2>&1 || true
    fi
    if (( HAD_GROUP == 0 )); then
      groupdel sg-naiveproxy >/dev/null 2>&1 || true
    fi
  fi
  exit "$rc"
}

trap rollback_install ERR
trap cleanup EXIT

[[ ${EUID:-$(id -u)} -eq 0 ]] || die "install-naiveproxy.sh requires root"
[[ "$(uname -m)" == "x86_64" ]] || die "Pinned NaiveProxy runtime currently supports x86_64 only"
for tool in curl tar sha256sum systemctl python3 stat; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done
[[ -f "$SOURCE_ROOT/deploy/$SERVICE" ]] || die "NaiveProxy systemd unit is missing"
[[ -f "$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE" ]] || die "NaiveProxy-capable hostd unit is missing"
[[ -d "$PANEL_CONFIG_DIR" ]] || die "Panel config directory is missing: $PANEL_CONFIG_DIR"

TX_DIR="$(mktemp -d /root/sg-gateway-naiveproxy-install.XXXXXX)"
snapshot_path "$PREFIX" prefix HAD_PREFIX
snapshot_path "$CONFIG_DIR" config HAD_CONFIG
snapshot_path "$STATE_DIR" state HAD_STATE
snapshot_path "$SERVICE_PATH" unit HAD_UNIT
snapshot_path "$HOSTD_SERVICE_PATH" hostd-unit HAD_HOSTD_UNIT
snapshot_path "$PANEL_ENV" panel-env HAD_PANEL_ENV
PANEL_CONFIG_MODE="$(stat -c '%a' "$PANEL_CONFIG_DIR")"
id -u sg-naiveproxy >/dev/null 2>&1 && HAD_USER=1
getent group sg-naiveproxy >/dev/null 2>&1 && HAD_GROUP=1
systemctl is-active --quiet "$SERVICE" 2>/dev/null && WAS_ACTIVE=1
systemctl is-enabled --quiet "$SERVICE" 2>/dev/null && WAS_ENABLED=1
systemctl is-active --quiet "$HOSTD_SERVICE" 2>/dev/null && HOSTD_WAS_ACTIVE=1
systemctl is-enabled --quiet "$HOSTD_SERVICE" 2>/dev/null && HOSTD_WAS_ENABLED=1
systemctl is-active --quiet "$PANEL_SERVICE" 2>/dev/null && PANEL_WAS_ACTIVE=1
systemctl is-enabled --quiet "$PANEL_SERVICE" 2>/dev/null && PANEL_WAS_ENABLED=1

install -d -m 0755 "$PREFIX/bin"
if ! getent group sg-naiveproxy >/dev/null; then groupadd --system sg-naiveproxy; fi
if ! id -u sg-naiveproxy >/dev/null 2>&1; then
  useradd --system --gid sg-naiveproxy --home-dir "$STATE_DIR" --shell /usr/sbin/nologin sg-naiveproxy
fi
chmod o+x "$PANEL_CONFIG_DIR"
install -d -o root -g sg-naiveproxy -m 0750 "$CONFIG_DIR"
install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 "$STATE_DIR"
install -d -o sg-naiveproxy -g sg-naiveproxy -m 0750 "$STATE_DIR/site"
if [[ -f "$CONFIG_DIR/Caddyfile" ]]; then
  chown root:sg-naiveproxy "$CONFIG_DIR/Caddyfile"
  chmod 0640 "$CONFIG_DIR/Caddyfile"
fi

work="$TX_DIR/download"
mkdir -p "$work"
archive="$work/caddy-forwardproxy-naive.tar.xz"
curl -fL --retry 3 --connect-timeout 15 -o "$archive" "$RUNTIME_URL"
printf '%s  %s\n' "$RUNTIME_ARCHIVE_SHA256" "$archive" | sha256sum -c - >/dev/null
tar -xJf "$archive" -C "$work"
candidate="$work/caddy-forwardproxy-naive/caddy"
[[ -x "$candidate" ]] || die "Pinned archive does not contain executable caddy"
"$candidate" list-modules | grep -qx 'http.handlers.forward_proxy' || die "forward_proxy module missing"
if [[ -f "$CONFIG_DIR/Caddyfile" ]]; then
  "$candidate" validate --config "$CONFIG_DIR/Caddyfile" --adapter caddyfile >/dev/null
fi

install -m 0755 "$candidate" "$PREFIX/bin/caddy.new"
mv -f "$PREFIX/bin/caddy.new" "$PREFIX/bin/caddy"
binary_sha256="$(sha256sum "$PREFIX/bin/caddy" | awk '{print $1}')"
[[ "$binary_sha256" =~ ^[0-9a-f]{64}$ ]] || die "Cannot calculate installed Caddy SHA-256"
printf '%s  %s\n' "$binary_sha256" "$PREFIX/bin/caddy" > "$PREFIX/CADDY-SHA256"
cat > "$PREFIX/VERSIONS.env" <<EOF
RUNTIME_VERSION=$RUNTIME_VERSION
RUNTIME_ARCHIVE_SHA256=$RUNTIME_ARCHIVE_SHA256
RUNTIME_BINARY_SHA256=$binary_sha256
RUNTIME_URL=$RUNTIME_URL
EOF

install -m 0644 "$SOURCE_ROOT/deploy/$SERVICE" "$SERVICE_PATH"
install -m 0644 "$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE" "$HOSTD_SERVICE_PATH"
persist_update_channel
systemctl daemon-reload
if (( HOSTD_WAS_ACTIVE == 1 )); then
  systemctl restart "$HOSTD_SERVICE"
  systemctl is-active --quiet "$HOSTD_SERVICE" || die "sg-hostd failed after NaiveProxy sandbox update"
fi
if (( PANEL_WAS_ACTIVE == 1 )); then
  systemctl restart "$PANEL_SERVICE"
  systemctl is-active --quiet "$PANEL_SERVICE" || die "SG-Gateway panel failed after update-channel migration"
fi
if (( WAS_ACTIVE == 1 )); then
  systemctl restart "$SERVICE"
  systemctl is-active --quiet "$SERVICE" || die "NaiveProxy service failed after runtime update"
fi
INSTALL_OK=1
log "NaiveProxy runtime ${RUNTIME_VERSION} installed. Configure domain/users, validate, then enable $SERVICE."
