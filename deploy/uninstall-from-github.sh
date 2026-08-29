#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="s-gor/sg-gateway-v22"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-stable-02206}}"
ARCHIVE_URL="https://github.com/${REPOSITORY}/archive/refs/heads/${BRANCH}.tar.gz"
TEMP_DIR=""

fail() {
  printf '[SG-Gateway] ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "$BRANCH" == "stable-02206" ]] || fail "stable uninstaller is pinned to stable-02206; requested branch: $BRANCH"
[[ "$(id -u)" -eq 0 ]] || fail "run this uninstaller through sudo"

cleanup() {
  if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
    rm -rf -- "$TEMP_DIR"
  fi
}
trap cleanup EXIT INT TERM

for command in curl tar gzip; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done

TEMP_DIR="$(mktemp -d /tmp/sg-gateway-github-uninstall.XXXXXX)"
ARCHIVE="$TEMP_DIR/sg-gateway-stable-02206.tar.gz"
SOURCE_DIR="$TEMP_DIR/source"
mkdir -p "$SOURCE_DIR"

printf '[SG-Gateway] Downloading GitHub branch %s for official full uninstall...\n' "$BRANCH"
curl -fL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 \
  "$ARCHIVE_URL" -o "$ARCHIVE"

gzip -t "$ARCHIVE"
tar -xzf "$ARCHIVE" -C "$SOURCE_DIR" --strip-components=1

UNINSTALLER="$SOURCE_DIR/deploy/full-uninstall-ubuntu.sh"
[[ -f "$UNINSTALLER" ]] || fail "deploy/full-uninstall-ubuntu.sh is missing from the GitHub archive"
[[ -f "$SOURCE_DIR/VERSION" ]] || fail "VERSION is missing from the GitHub archive"

printf '[SG-Gateway] GitHub source version: %s\n' "$(tr -d '\r\n' < "$SOURCE_DIR/VERSION")"
printf '[SG-Gateway] Starting the official FULL uninstaller...\n'
bash "$UNINSTALLER"
