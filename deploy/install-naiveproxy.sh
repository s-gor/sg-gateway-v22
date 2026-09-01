#!/usr/bin/env bash
set -Eeuo pipefail

RUNTIME_VERSION="v2.11.2-naive"
RUNTIME_SHA256="19eccb7321dd877a5fb4a3dba6ef1b745185188b616c96cc6201f1a1fc0380a8"
RUNTIME_URL="https://github.com/klzgrad/forwardproxy/releases/download/${RUNTIME_VERSION}/caddy-forwardproxy-naive.tar.xz"
PREFIX="/opt/sg-gateway/naiveproxy"
CONFIG_DIR="/etc/sg-gateway/naiveproxy"
STATE_DIR="/var/lib/sg-gateway/naiveproxy"
SERVICE="sg-gateway-naiveproxy.service"
SOURCE_ROOT="${SG_GATEWAY_SOURCE_ROOT:-/opt/sg-gateway}"

log() { printf '[SG-Gateway] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
rollback_binary() {
  if [[ -x "$PREFIX/bin/caddy.previous" ]]; then
    mv -f "$PREFIX/bin/caddy.previous" "$PREFIX/bin/caddy"
    systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  fi
}
[[ ${EUID:-$(id -u)} -eq 0 ]] || die "install-naiveproxy.sh requires root"
[[ "$(uname -m)" == "x86_64" ]] || die "Pinned NaiveProxy runtime currently supports x86_64 only"
for tool in curl tar sha256sum systemctl; do command -v "$tool" >/dev/null 2>&1 || die "$tool is required"; done

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

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
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
if [[ -x "$PREFIX/bin/caddy" ]]; then cp -a "$PREFIX/bin/caddy" "$PREFIX/bin/caddy.previous"; fi
mv -f "$PREFIX/bin/caddy.new" "$PREFIX/bin/caddy"
sha256sum "$PREFIX/bin/caddy" > "$PREFIX/CADDY-SHA256"
cat > "$PREFIX/VERSIONS.env" <<EOF
RUNTIME_VERSION=$RUNTIME_VERSION
RUNTIME_SHA256=$RUNTIME_SHA256
RUNTIME_URL=$RUNTIME_URL
EOF

install -m 0644 "$SOURCE_ROOT/deploy/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
if systemctl is-active --quiet "$SERVICE"; then
  systemctl restart "$SERVICE" || { rollback_binary; die "NaiveProxy restart failed; previous binary restored"; }
fi
log "NaiveProxy runtime ${RUNTIME_VERSION} installed. Configure domain/users, validate, then enable $SERVICE."
