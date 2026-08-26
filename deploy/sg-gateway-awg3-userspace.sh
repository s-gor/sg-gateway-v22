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
DAEMON_PID=""
STRIPPED=""

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

cleanup_runtime() {
  set +e
  if [[ -n "$DAEMON_PID" ]]; then
    kill "$DAEMON_PID" >/dev/null 2>&1 || true
    wait "$DAEMON_PID" >/dev/null 2>&1 || true
  fi
  if [[ -f "$CONFIG" ]]; then
    run_config_commands PostDown || true
  fi
  ip link delete dev "$IFACE" >/dev/null 2>&1 || true
  rm -f "$SOCKET"
  [[ -z "$STRIPPED" ]] || rm -f "$STRIPPED"
}

start_runtime() {
  require_runtime
  cleanup_runtime

  "$AWG_GO" --foreground "$IFACE" &
  DAEMON_PID=$!
  trap 'rc=$?; trap - EXIT INT TERM; cleanup_runtime; exit "$rc"' EXIT INT TERM

  local deadline=$((SECONDS + 10))
  until [[ -S "$SOCKET" ]] && ip link show dev "$IFACE" >/dev/null 2>&1; do
    kill -0 "$DAEMON_PID" >/dev/null 2>&1 || {
      echo "AWG3 userspace daemon exited before interface creation" >&2
      return 1
    }
    if (( SECONDS >= deadline )); then
      echo "AWG3 userspace interface did not appear" >&2
      return 1
    fi
    sleep 0.1
  done

  STRIPPED="$(mktemp /run/sg-gateway-awg3.XXXXXX)"
  "$AWG_QUICK" strip "$CONFIG" > "$STRIPPED"
  "$AWG" setconf "$IFACE" "$STRIPPED"

  local address_line="" address=""
  local -a addresses=()
  while IFS= read -r address_line; do
    [[ -n "$address_line" ]] || continue
    IFS=',' read -r -a addresses <<< "$address_line"
    for address in "${addresses[@]}"; do
      address="${address#"${address%%[![:space:]]*}"}"
      address="${address%"${address##*[![:space:]]}"}"
      [[ -n "$address" ]] || continue
      if [[ "$address" == *:* ]]; then
        ip -6 address add "$address" dev "$IFACE"
      else
        ip -4 address add "$address" dev "$IFACE"
      fi
    done
  done < <(config_values Address)

  local mtu=""
  mtu="$(config_values MTU | head -n 1 || true)"
  if [[ -n "$mtu" ]]; then
    ip link set mtu "$mtu" dev "$IFACE"
  fi
  ip link set up dev "$IFACE"
  run_config_commands PostUp
  "$AWG" show "$IFACE" >/dev/null
  rm -f "$STRIPPED"
  STRIPPED=""

  wait "$DAEMON_PID"
}

case "${1:-}" in
  up)
    start_runtime
    ;;
  down)
    cleanup_runtime
    ;;
  restart)
    cleanup_runtime
    start_runtime
    ;;
  *)
    echo "Usage: $0 {up|down|restart}" >&2
    exit 2
    ;;
esac
