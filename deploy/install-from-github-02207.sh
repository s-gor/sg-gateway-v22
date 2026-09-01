#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="s-gor/sg-gateway-v22"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"
SOURCE_COMMIT="${SG_GATEWAY_SOURCE_COMMIT:-}"
REF="${SOURCE_COMMIT:-$BRANCH}"
TMP=""
fail(){ printf '[SG-Gateway 22.07] ERROR: %s\n' "$*" >&2; exit 1; }
cleanup(){ [[ -z "$TMP" ]] || rm -rf "$TMP"; }
trap cleanup EXIT INT TERM

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "run through sudo"
[[ "$BRANCH" == "dev-02207" || "$BRANCH" == feature/02207-* ]] || fail "22.07 installer refuses branch $BRANCH"
[[ -z "$SOURCE_COMMIT" || "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "invalid exact commit"
[[ ! -e /opt/sg-gateway/VERSION ]] || fail "clean install is blocked on an existing server; use update-from-github-02207.sh"
for tool in curl tar gzip python3; do command -v "$tool" >/dev/null || fail "$tool is required"; done
TMP="$(mktemp -d /tmp/sg-gateway-02207.XXXXXX)"
mkdir -p "$TMP/source"
curl -fL --retry 6 --retry-all-errors --connect-timeout 20 \
  "https://github.com/${REPOSITORY}/archive/${REF}.tar.gz" -o "$TMP/source.tar.gz"
gzip -t "$TMP/source.tar.gz"
tar -xzf "$TMP/source.tar.gz" -C "$TMP/source" --strip-components=1
[[ -x "$TMP/source/install.sh" || -f "$TMP/source/install.sh" ]] || fail "install.sh missing"
[[ -x "$TMP/source/deploy/install-naiveproxy.sh" || -f "$TMP/source/deploy/install-naiveproxy.sh" ]] || fail "NaiveProxy installer missing"

patched_installer="$TMP/install-02207.sh"
cp "$TMP/source/install.sh" "$patched_installer"
python3 - "$patched_installer" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
marker = "  INSTALL_SUCCESS=1\n"
if source.count(marker) != 1:
    raise SystemExit("cannot locate unique installer success boundary")
hook = (
    "  run_quiet \"Этап 10/10 · Установка NaiveProxy runtime\" "
    "env SG_GATEWAY_SOURCE_ROOT=\"$SOURCE_DIR\" "
    "bash \"$SOURCE_DIR/deploy/install-naiveproxy.sh\"\n"
)
path.write_text(source.replace(marker, hook + marker), encoding="utf-8")
PY
bash -n "$patched_installer"

SG_GATEWAY_SOURCE_DIR="$TMP/source" \
SG_GATEWAY_SOURCE_COMMIT="$SOURCE_COMMIT" \
SG_GATEWAY_UPDATE_BRANCH="$BRANCH" \
  bash "$patched_installer"

printf '[SG-Gateway 22.07] Installed. NaiveProxy remains disabled until HTTPS/settings are ready; its selected TCP port is managed when settings are applied.\n'
