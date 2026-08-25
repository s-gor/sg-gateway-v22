#!/usr/bin/env bash
set -euo pipefail

PREFIX=${SG_GATEWAY_PREFIX:-/opt/sg-gateway}
VENDOR="$PREFIX/vendor/cores"
RUNTIME=${SG_GATEWAY_AWG31_RUNTIME:-/opt/sg-gateway/awg31}
TOOLS=amneziawg-tools-3.1.20260812.tar.gz
GO=amneziawg-go-linux-amd64-v3.1.20260814
TOOLS_SHA=f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada
GO_SHA=375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110

printf '%s  %s\n' "$TOOLS_SHA" "$VENDOR/$TOOLS" | sha256sum -c -
printf '%s  %s\n' "$GO_SHA" "$VENDOR/$GO" | sha256sum -c -
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$VENDOR/$TOOLS" -C "$TMP"
AWG=$(find "$TMP" -type f -path "*/src/wg" -perm -u+x | head -1)
AWG_QUICK=$(find "$TMP" -type f -path "*/src/wg-quick/linux.bash" | head -1)
test -n "$AWG" && test -n "$AWG_QUICK"
install -d -m 0755 "$RUNTIME/bin" /etc/amnezia/amneziawg/awg31/peers /var/lib/sg-gateway/awg31
install -m 0755 "$AWG" "$RUNTIME/bin/awg"
install -m 0755 "$AWG_QUICK" "$RUNTIME/bin/awg-quick"
install -m 0755 "$VENDOR/$GO" "$RUNTIME/bin/amneziawg-go"
install -m 0644 "$PREFIX/deploy/sg-gateway-awg31.service" /etc/systemd/system/sg-gateway-awg31.service
systemctl daemon-reload
