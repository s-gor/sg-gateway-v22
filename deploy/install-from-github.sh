#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="s-gor/sg-gateway-v22"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02204}}"
ARCHIVE_URL="https://github.com/${REPOSITORY}/archive/refs/heads/${BRANCH}.tar.gz"
TEMP_DIR=""

fail() {
  printf '[SG-Gateway] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT INT TERM

[[ "$(id -u)" -eq 0 ]] || fail "run this installer through sudo"

# SG_GATEWAY_02112_INSTALL_UPDATE_SPLIT
# The public clean-install command must never mutate an existing SG-Gateway.
if [[ -f /opt/sg-gateway/VERSION && -f /etc/sg-gateway/runtime.env && -f /etc/sg-gateway/sg-gateway.env ]]; then
  installed_version="$(tr -d '\r\n' < /opt/sg-gateway/VERSION 2>/dev/null || true)"
  printf '[SG-Gateway] SG-Gateway %s is already installed.\n' "${installed_version:-unknown}"
  printf '[SG-Gateway] Clean Install is blocked on an existing server.\n'
  printf '[SG-Gateway] Use the dedicated Update command:\n'
  printf 'curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/stable-02204/deploy/update-from-github.sh | sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02204 bash\n'
  exit 2
fi

missing_packages=()
command -v curl >/dev/null 2>&1 || missing_packages+=(curl)
command -v tar >/dev/null 2>&1 || missing_packages+=(tar)
command -v gzip >/dev/null 2>&1 || missing_packages+=(gzip)
[[ -s /etc/ssl/certs/ca-certificates.crt ]] || missing_packages+=(ca-certificates)

if (( ${#missing_packages[@]} > 0 )); then
  command -v apt-get >/dev/null 2>&1 || fail "apt-get is required to install bootstrap dependencies"
  printf '[SG-Gateway] Preparing required Ubuntu tools...\n'
  apt-get -o Dpkg::Use-Pty=0 update -qq
  env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a \
    apt-get -o Dpkg::Use-Pty=0 install -y -qq --no-install-recommends "${missing_packages[@]}"
fi

for command in curl tar gzip; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command after bootstrap: $command"
done

TEMP_DIR="$(mktemp -d /tmp/sg-gateway-github-install.XXXXXX)"
ARCHIVE="$TEMP_DIR/sg-gateway-main.tar.gz"
SOURCE_DIR="$TEMP_DIR/source"
mkdir -p "$SOURCE_DIR"

printf '[SG-Gateway] Downloading GitHub branch %s...\n' "$BRANCH"
curl -fL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 \
  "$ARCHIVE_URL" -o "$ARCHIVE"

gzip -t "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$SOURCE_DIR" --strip-components=1

[[ -f "$SOURCE_DIR/install.sh" ]] || fail "install.sh is missing from the GitHub archive"
[[ -f "$SOURCE_DIR/VERSION" ]] || fail "VERSION is missing from the GitHub archive"
[[ -f "$SOURCE_DIR/requirements.txt" ]] || fail "requirements.txt is missing from the GitHub archive"
[[ -d "$SOURCE_DIR/app" ]] || fail "application source is missing from the GitHub archive"

printf '[SG-Gateway] GitHub source version: %s\n' "$(tr -d '\r\n' < "$SOURCE_DIR/VERSION")"
printf '[SG-Gateway] Starting the native Ubuntu CLEAN installer...\n'
SG_GATEWAY_SOURCE_DIR="$SOURCE_DIR" bash "$SOURCE_DIR/install.sh"

# SG_GATEWAY_FIX30_IPV6_BOOTSTRAP_V1
# Keep the proven native installer untouched while Fix30 is developed.  The
# GitHub clean-install wrapper records dual-stack runtime facts only after the
# baseline installation has succeeded.  IPv6 is optional and can never turn a
# successful IPv4 installation into a failed one.
valid_ip_family() {
  local value="${1:-}" family="${2:-}"
  python3 - "$value" "$family" <<'PYIP' >/dev/null 2>&1
import ipaddress
import sys
try:
    address = ipaddress.ip_address(sys.argv[1].strip())
    family = int(sys.argv[2])
except (ValueError, IndexError):
    raise SystemExit(1)
raise SystemExit(0 if address.version == family and address.is_global else 1)
PYIP
}

env_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 1
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$file"
}

detect_global_ipv6() {
  local value=""
  if command -v ip >/dev/null 2>&1; then
    value="$(ip -6 route get 2606:4700:4700::1111 2>/dev/null \
      | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1 || true)"
    if valid_ip_family "$value" 6; then
      printf '%s' "$value"
      return 0
    fi

    while IFS= read -r value; do
      value="${value%%/*}"
      if valid_ip_family "$value" 6; then
        printf '%s' "$value"
        return 0
      fi
    done < <(ip -6 -o address show scope global 2>/dev/null | awk '{print $4}' || true)
  fi
  return 1
}

persist_dual_stack_runtime() {
  local runtime_file="/etc/sg-gateway/runtime.env"
  local app_file="/etc/sg-gateway/sg-gateway.env"
  local legacy_ipv4="" public_ipv6=""

  legacy_ipv4="$(env_value "$runtime_file" SG_GATEWAY_PUBLIC_ADDRESS 2>/dev/null || true)"
  if ! valid_ip_family "$legacy_ipv4" 4; then
    legacy_ipv4=""
  fi
  public_ipv6="$(detect_global_ipv6 || true)"

  if ! python3 - "$runtime_file" "$app_file" "$legacy_ipv4" "$public_ipv6" <<'PYENV'
from pathlib import Path
import sys

runtime_path = Path(sys.argv[1])
app_path = Path(sys.argv[2])
ipv4 = sys.argv[3].strip()
ipv6 = sys.argv[4].strip()
values = {
    "SG_GATEWAY_PUBLIC_IPV4": ipv4,
    "SG_GATEWAY_PUBLIC_IPV6": ipv6,
}

for path in (runtime_path, app_path):
    if not path.is_file():
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    output = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    for key, value in remaining.items():
        output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
PYENV
  then
    printf '[SG-Gateway] IPv6 bootstrap: runtime persistence failed; IPv4 installation remains active.\n' >&2
    return 0
  fi

  if [[ -n "$public_ipv6" ]]; then
    printf '[SG-Gateway] IPv6 detected: %s\n' "$public_ipv6"
    printf '[SG-Gateway] Dual Stack runtime metadata: ACTIVE\n'
  else
    printf '[SG-Gateway] IPv6 not detected; IPv4 runtime remains unchanged.\n'
  fi

  systemctl try-restart sg-hostd.service sg-gateway.service >/dev/null 2>&1 || true
}

persist_dual_stack_runtime || true
