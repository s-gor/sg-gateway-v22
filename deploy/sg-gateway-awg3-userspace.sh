#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG="/etc/amnezia/amneziawg/awg3.conf"
AWG3_ROOT="/opt/sg-gateway/awg3"
export PATH="$AWG3_ROOT/bin:$PATH"
AWG="$AWG3_ROOT/bin/awg"
AWG_QUICK="$AWG3_ROOT/bin/awg-quick"
AWG_GO="$AWG3_ROOT/bin/amneziawg-go"
SOCKET="/var/run/amneziawg/awg3.sock"
IFACE="awg3"

require_runtime() {
  [[ -x "$AWG" ]] || { echo "AWG3 tool missing: $AWG" >&2; return 1; }
  [[ -x "$AWG_QUICK" ]] || { echo "AWG3 tool missing: $AWG_QUICK" >&2; return 1; }
  [[ -x "$AWG_GO" ]] || { echo "AWG3 userspace daemon missing: $AWG_GO" >&2; return 1; }
  [[ -f "$CONFIG" ]] || { echo "AWG3 config missing: $CONFIG" >&2; return 1; }
}

config_values() {
  local key="$1"
  awk -F= -v wanted="$key" '
    BEGIN { iface=0 }
    /^[[:space:]]*\[Interface\][[:space:]]*$/ { iface=1; next }
    /^[[:space:]]*\[/ { iface=0 }
    iface && $1 ~ "^[[:space:]]*" wanted "[[:space:]]*$" {
      value=$0; sub(/^[^=]*=/, "", value); gsub(/^[[:space:]]+|[[:space:]]+$/, "", value); print value
    }
  ' "$CONFIG"
}

run_config_commands() {
  local key="$1" command=""
  while IFS= read -r command; do
    [[ -n "$command" ]] || continue
    /bin/bash -c "$command"
  done < <(config_values "$key")
}

stop_runtime() {
  if [[ -f "$CONFIG" ]]; then
    run_config_commands PostDown || true
  fi
  if ip link show dev "$IFACE" >/dev/null 2>&1; then
    ip link delete dev "$IFACE" >/dev/null 2>&1 || true
  fi
  rm -f "$SOCKET"
}

start_runtime() {
  require_runtime
  stop_runtime

  "$AWG_GO" "$IFACE"

  local deadline=$((SECONDS + 10))
  until [[ -S "$SOCKET" ]] && ip link show dev "$IFACE" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "AWG3 userspace interface did not appear" >&2
      stop_runtime
      return 1
    fi
    sleep 0.1
  done

  local stripped=""
  stripped="$(mktemp /run/sg-gateway-awg3.XXXXXX)"
  if ! {
    "$AWG_QUICK" strip "$CONFIG" > "$stripped"
    "$AWG" setconf "$IFACE" "$stripped"

    local address=""
    while IFS= read -r address; do
      [[ -n "$address" ]] || continue
      if [[ "$address" == *:* ]]; then
        ip -6 address add "$address" dev "$IFACE"
      else
        ip -4 address add "$address" dev "$IFACE"
      fi
    done < <(config_values Address)

    local mtu=""
    mtu="$(config_values MTU | head -n 1 || true)"
    if [[ -n "$mtu" ]]; then
      ip link set mtu "$mtu" dev "$IFACE"
    fi
    ip link set up dev "$IFACE"
    run_config_commands PostUp
    "$AWG" show "$IFACE" >/dev/null
  }; then
    rm -f "$stripped"
    stop_runtime
    return 1
  fi
  rm -f "$stripped"
}

case "${1:-}" in
  up)
    start_runtime
    ;;
  down)
    stop_runtime
    ;;
  restart)
    stop_runtime
    start_runtime
    ;;
  *)
    echo "Usage: $0 {up|down|restart}" >&2
    exit 2
    ;;
esac
