#!/usr/bin/env bash
set -euo pipefail

PREFIX=${SG_GATEWAY_PREFIX:-/opt/sg-gateway}
VENDOR="$PREFIX/vendor/cores"
RUNTIME=${SG_GATEWAY_AWG31_RUNTIME:-/opt/sg-gateway/awg31}
CONFIG_ROOT=${SG_GATEWAY_AWG31_CONFIG_ROOT:-/etc/amnezia/amneziawg/awg31}
STATE_ROOT=${SG_GATEWAY_AWG31_STATE_ROOT:-/var/lib/sg-gateway/awg31}
SYSTEMD_DIR=${SG_GATEWAY_SYSTEMD_DIR:-/etc/systemd/system}
SKIP_SYSTEMCTL=${SG_GATEWAY_SKIP_SYSTEMCTL:-0}
TOOLS=amneziawg-tools-3.1.20260812.tar.gz
GO=amneziawg-go-linux-amd64-v3.1.20260814
TOOLS_SHA=f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada
GO_SHA=375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110

printf '%s  %s\n' "$TOOLS_SHA" "$VENDOR/$TOOLS" | sha256sum -c -
printf '%s  %s\n' "$GO_SHA" "$VENDOR/$GO" | sha256sum -c -

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$VENDOR/$TOOLS" -C "$TMP"
SOURCE=$(find "$TMP" -mindepth 1 -maxdepth 1 -type d -name 'amneziawg-tools-*' -print -quit)
test -n "$SOURCE"

BUILD_INSTALL="$TMP/install"
make -C "$SOURCE/src" PLATFORM=linux clean
make -C "$SOURCE/src" PLATFORM=linux V=1
make -C "$SOURCE/src" PLATFORM=linux install \
    DESTDIR="$BUILD_INSTALL" \
    PREFIX=/usr \
    WITH_WGQUICK=yes \
    WITH_BASHCOMPLETION=no \
    WITH_SYSTEMDUNITS=no

test -x "$BUILD_INSTALL/usr/bin/awg"
test -x "$BUILD_INSTALL/usr/bin/awg-quick"
test -x "$VENDOR/$GO"

install -d -m 0755 \
    "$RUNTIME/bin" \
    "$CONFIG_ROOT/peers" \
    "$STATE_ROOT" \
    "$SYSTEMD_DIR"
install -m 0755 "$BUILD_INSTALL/usr/bin/awg" "$RUNTIME/bin/awg"
install -m 0755 "$BUILD_INSTALL/usr/bin/awg-quick" "$RUNTIME/bin/awg-quick"
install -m 0755 "$VENDOR/$GO" "$RUNTIME/bin/amneziawg-go"
install -m 0644 "$PREFIX/deploy/sg-gateway-awg31.service" "$SYSTEMD_DIR/sg-gateway-awg31.service"

if [[ "$SKIP_SYSTEMCTL" != "1" ]]; then
    systemctl daemon-reload
fi
