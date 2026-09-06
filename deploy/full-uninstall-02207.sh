#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX="${SG_GATEWAY_PREFIX:-/opt/sg-gateway}"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"
TMP=""

fail() {
  printf '[SG-Gateway 22.07] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  [[ -z "$TMP" ]] || rm -rf -- "$TMP"
}
trap cleanup EXIT INT TERM

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "run through sudo"
[[ "$BRANCH" == "dev-02207" || "$BRANCH" == feature/02207-* ]] || \
  fail "22.07 uninstaller refuses branch $BRANCH"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

BASE="$PREFIX/deploy/full-uninstall-ubuntu.sh"
NAIVE="$PREFIX/deploy/uninstall-naiveproxy.sh"
[[ -f "$BASE" ]] || fail "base full uninstaller is missing: $BASE"
[[ -f "$NAIVE" ]] || fail "NaiveProxy uninstaller is missing: $NAIVE"

TMP="$(mktemp -d /tmp/sg-gateway-full-uninstall-02207.XXXXXX)"
PATCHED="$TMP/full-uninstall-02207.sh"
cp -- "$BASE" "$PATCHED"
python3 - "$PATCHED" "$BRANCH" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
branch = sys.argv[2]
source = path.read_text(encoding="utf-8")
replacements = {
    'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02206.log"':
        'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02207.log"',
    'SG-Gateway 0.1.0-022.06 · ПОЛНОЕ УДАЛЕНИЕ':
        'SG-Gateway 0.1.0-022.07-dev · ПОЛНОЕ УДАЛЕНИЕ',
}
for old, new in replacements.items():
    if source.count(old) != 1:
        raise SystemExit(f"cannot patch unique full-uninstall marker: {old}")
    source = source.replace(old, new)
old_command = (
    "curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/"
    "2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff/deploy/install-from-github.sh | "
    "sudo env SG_GATEWAY_GITHUB_BRANCH=stable-02206 "
    "SG_GATEWAY_SOURCE_COMMIT=2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff bash"
)
new_command = (
    "curl -4 -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/"
    f"{branch}/deploy/install-from-github-02207.sh | "
    f"sudo env SG_GATEWAY_GITHUB_BRANCH={branch} bash"
)
if source.count(old_command) != 1:
    raise SystemExit("cannot patch unique reinstall command")
source = source.replace(old_command, new_command)
path.write_text(source, encoding="utf-8")
PY
bash -n "$PATCHED"

bash "$NAIVE"
bash "$PATCHED"

bad=0
for path in \
  /opt/sg-gateway/naiveproxy \
  /etc/sg-gateway/naiveproxy \
  /var/lib/sg-gateway/naiveproxy \
  /etc/systemd/system/sg-gateway-naiveproxy.service; do
  if [[ -e "$path" || -L "$path" ]]; then
    printf '[SG-Gateway 22.07] Residue after full uninstall: %s\n' "$path" >&2
    bad=1
  fi
done
if id -u sg-naiveproxy >/dev/null 2>&1; then
  printf '[SG-Gateway 22.07] Residue after full uninstall: user sg-naiveproxy\n' >&2
  bad=1
fi
if getent group sg-naiveproxy >/dev/null 2>&1; then
  printf '[SG-Gateway 22.07] Residue after full uninstall: group sg-naiveproxy\n' >&2
  bad=1
fi
(( bad == 0 )) || fail "full uninstall left NaiveProxy state"
printf '[SG-Gateway 22.07] NaiveProxy residue verification: OK.\n'
