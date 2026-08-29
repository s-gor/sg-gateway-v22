#!/usr/bin/env bash
set -Eeuo pipefail

IFACE=awg31
CONFIG=/etc/amnezia/amneziawg/awg31/awg31.conf
RUNTIME=/opt/sg-gateway/awg31
AWG="$RUNTIME/bin/awg"
AWG_QUICK="$RUNTIME/bin/awg-quick"
AWG_GO="$RUNTIME/bin/amneziawg-go"
NFT_TABLE=sg_gateway_awg31
PID=""
STRIPPED=""

cleanup_network() {
  nft delete table ip "$NFT_TABLE" >/dev/null 2>&1 || true
  ip link delete "$IFACE" >/dev/null 2>&1 || true
}

shutdown() {
  local status="${1:-0}"
  trap - INT TERM EXIT
  if [[ -n "$STRIPPED" ]]; then
    rm -f "$STRIPPED"
    STRIPPED=""
  fi
  if [[ -n "$PID" ]]; then
    kill "$PID" >/dev/null 2>&1 || true
    wait "$PID" >/dev/null 2>&1 || true
  fi
  cleanup_network
  exit "$status"
}

trap 'shutdown 0' INT TERM
trap 'shutdown $?' EXIT

[[ -x "$AWG" ]] || { echo "AWG31 tool missing: $AWG" >&2; exit 1; }
[[ -x "$AWG_QUICK" ]] || { echo "AWG31 tool missing: $AWG_QUICK" >&2; exit 1; }
[[ -x "$AWG_GO" ]] || { echo "AWG31 userspace daemon missing: $AWG_GO" >&2; exit 1; }
[[ -f "$CONFIG" ]] || { echo "AWG31 config missing: $CONFIG" >&2; exit 1; }

cleanup_network
mkdir -p /run/amneziawg
"$AWG_GO" --foreground "$IFACE" &
PID=$!

for _ in $(seq 1 100); do
  ip link show "$IFACE" >/dev/null 2>&1 && break
  kill -0 "$PID" >/dev/null 2>&1 || { wait "$PID"; exit 1; }
  sleep 0.1
done
ip link show "$IFACE" >/dev/null 2>&1 || { echo "AWG31 interface did not appear" >&2; exit 1; }

STRIPPED=$(mktemp /run/sg-gateway-awg31.XXXXXX)
"$AWG_QUICK" strip "$CONFIG" > "$STRIPPED"
"$AWG" setconf "$IFACE" "$STRIPPED"
rm -f "$STRIPPED"
STRIPPED=""

ip address replace 10.131.0.1/24 dev "$IFACE"
ip link set mtu 1420 up dev "$IFACE"
sysctl -w net.ipv4.ip_forward=1 >/dev/null

WAN_IF=$(ip -4 route show default | awk 'NR==1 {for (i=1; i<=NF; i++) if ($i=="dev") {print $(i+1); exit}}')
[[ -n "$WAN_IF" ]] || { echo "AWG31 default interface not found" >&2; exit 1; }

nft add table ip "$NFT_TABLE"
nft 'add chain ip '"$NFT_TABLE"' forward { type filter hook forward priority filter; policy accept; }'
nft 'add chain ip '"$NFT_TABLE"' postrouting { type nat hook postrouting priority srcnat; policy accept; }'
nft add rule ip "$NFT_TABLE" postrouting oifname "$WAN_IF" ip saddr 10.131.0.0/24 masquerade

wait "$PID"
status=$?
PID=""
exit "$status"
