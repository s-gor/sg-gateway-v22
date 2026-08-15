#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="v0.3.6"
BASE_URL="https://github.com/ArchiveNetwork/wgcf-cli/releases/download/$VERSION"
DEST="/usr/local/bin/wgcf-cli"

log(){ printf '[SG-Gateway] %s\n' "$*"; }
fail(){ printf '[SG-Gateway] ERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "run as root"

case "$(uname -m)" in
  x86_64|amd64) ASSET="wgcf-cli-linux-64.tar.zstd" ;;
  aarch64|arm64) ASSET="wgcf-cli-linux-arm64-v8a.tar.zstd" ;;
  *) fail "unsupported architecture: $(uname -m)" ;;
esac

for command in curl tar sha256sum; do
  command -v "$command" >/dev/null 2>&1 || fail "missing command: $command"
done
if ! command -v unzstd >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y zstd
fi

TMP="$(mktemp -d /tmp/sg-gateway-wgcf.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

log "Installing wgcf-cli $VERSION"
curl -fL --retry 3 --connect-timeout 15 \
  "$BASE_URL/$ASSET" -o "$TMP/$ASSET"
curl -fL --retry 3 --connect-timeout 15 \
  "$BASE_URL/$ASSET.dgst" -o "$TMP/$ASSET.dgst"

EXPECTED="$(awk -F'= ' '/^SHA2-256=/{print $2}' "$TMP/$ASSET.dgst" | tr -d '[:space:]')"
[[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] || fail "invalid SHA-256 digest file"
printf '%s  %s\n' "$EXPECTED" "$TMP/$ASSET" | sha256sum -c - >/dev/null

tar --use-compress-program=unzstd -xf "$TMP/$ASSET" -C "$TMP"
BINARY="$(find "$TMP" -type f -name wgcf-cli | head -n 1)"
[[ -n "$BINARY" ]] || fail "wgcf-cli binary not found in archive"
install -m 0755 "$BINARY" "$DEST"
"$DEST" version >/dev/null 2>&1 || "$DEST" --version >/dev/null 2>&1 || fail "wgcf-cli does not start"
log "wgcf-cli installed: $DEST"
