#!/usr/bin/env bash
set -euo pipefail

IFACE=awg31
CONFIG=/etc/amnezia/amneziawg/awg31/awg31.conf
RUNTIME=/opt/sg-gateway/awg31
mkdir -p /run/amneziawg
"$RUNTIME/bin/amneziawg-go" --foreground "$IFACE" &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; ip link delete "$IFACE" 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 50); do ip link show "$IFACE" >/dev/null 2>&1 && break; sleep 0.1; done
"$RUNTIME/bin/awg" setconf "$IFACE" <("$RUNTIME/bin/awg-quick" strip "$CONFIG")
ip address replace 10.131.0.1/24 dev "$IFACE"
ip link set mtu 1420 up dev "$IFACE"
wait "$PID"
