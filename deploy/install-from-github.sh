#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="s-gor/sg-gateway"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-main}"
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
  printf 'curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway/main/deploy/update-from-github.sh | sudo bash\n'
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
