#!/usr/bin/env bash
set -Eeuo pipefail

RUNTIME_VERSION="v2.11.2-naive"
RUNTIME_SHA256="19eccb7321dd877a5fb4a3dba6ef1b745185188b616c96cc6201f1a1fc0380a8"
RUNTIME_URL="https://github.com/klzgrad/forwardproxy/releases/download/${RUNTIME_VERSION}/caddy-forwardproxy-naive.tar.xz"
PREFIX="/opt/sg-gateway/naiveproxy"
CONFIG_DIR="/etc/sg-gateway/naiveproxy"
STATE_DIR="/var/lib/sg-gateway/naiveproxy"
SERVICE="sg-gateway-naiveproxy.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE"
SOURCE_ROOT="${SG_GATEWAY_SOURCE_ROOT:-/opt/sg-gateway}"
TX_DIR=""
INSTALL_OK=0
HAD_PREFIX=0
HAD_CONFIG=0
HAD_STATE=0
HAD_UNIT=0
HAD_USER=0
HAD_GROUP=0
WAS_ACTIVE=0
WAS_ENABLED=0

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
    systemctl daemon-reload >/dev/null 2>&1 || true
    if (( WAS_ENABLED == 1 )); then
      systemctl enable "$SERVICE" >/dev/null 2>&1 || true
    else
      systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    fi
    if (( WAS_ACTIVE == 1 )); then
      systemctl start "$SERVICE" >/dev/null 2>&1 || true
    else
      systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    fi
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
for tool in curl tar sha256sum systemctl; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required"
done
[[ -f "$SOURCE_ROOT/deploy/$SERVICE" ]] || die "NaiveProxy systemd unit is missing"

TX_DIR="$(mktemp -d /root/sg-gateway-naiveproxy-install.XXXXXX)"
snapshot_path "$PREFIX" prefix HAD_PREFIX
snapshot_path "$CONFIG_DIR" config HAD_CONFIG
snapshot_path "$STATE_DIR" state HAD_STATE
snapshot_path "$SERVICE_PATH" unit HAD_UNIT
id -u sg-naiveproxy >/dev/null 2>&1 && HAD_USER=1
getent group sg-naiveproxy >/dev/null 2>&1 && HAD_GROUP=1
systemctl is-active --quiet "$SERVICE" 2>/dev/null && WAS_ACTIVE=1
systemctl is-enabled --quiet "$SERVICE" 2>/dev/null && WAS_ENABLED=1

install -d -m 0755 "$PREFIX/bin"
if ! getent group sg-naiveproxy >/dev/null; then groupadd --system sg-naiveproxy; fi
if ! id -u sg-naiveproxy >/dev/null 2>&1; then
  useradd --system --gid sg-naiveproxy --home-dir "$STATE_DIR" --shell /usr/sbin/nologin sg-naiveproxy
fi
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
printf '%s  %s\n' "$RUNTIME_SHA256" "$archive" | sha256sum -c - >/dev/null
tar -xJf "$archive" -C "$work"
candidate="$work/caddy-forwardproxy-naive/caddy"
[[ -x "$candidate" ]] || die "Pinned archive does not contain executable caddy"
"$candidate" list-modules | grep -qx 'http.handlers.forward_proxy' || die "forward_proxy module missing"
if [[ -f "$CONFIG_DIR/Caddyfile" ]]; then
  "$candidate" validate --config "$CONFIG_DIR/Caddyfile" --adapter caddyfile >/dev/null
fi

install -m 0755 "$candidate" "$PREFIX/bin/caddy.new"
mv -f "$PREFIX/bin/caddy.new" "$PREFIX/bin/caddy"
sha256sum "$PREFIX/bin/caddy" > "$PREFIX/CADDY-SHA256"
cat > "$PREFIX/VERSIONS.env" <<EOF
RUNTIME_VERSION=$RUNTIME_VERSION
RUNTIME_SHA256=$RUNTIME_SHA256
RUNTIME_URL=$RUNTIME_URL
EOF

install -m 0644 "$SOURCE_ROOT/deploy/$SERVICE" "$SERVICE_PATH"
systemctl daemon-reload
if (( WAS_ACTIVE == 1 )); then
  systemctl restart "$SERVICE"
fi
INSTALL_OK=1
log "NaiveProxy runtime ${RUNTIME_VERSION} installed. Configure domain/users, validate, then enable $SERVICE."
