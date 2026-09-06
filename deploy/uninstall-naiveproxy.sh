#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX="/opt/sg-gateway/naiveproxy"
CONFIG_DIR="/etc/sg-gateway/naiveproxy"
STATE_DIR="/var/lib/sg-gateway/naiveproxy"
STATE_PATH="$STATE_DIR/state.json"
SERVICE="sg-gateway-naiveproxy.service"
UNIT="/etc/systemd/system/$SERVICE"

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo '[SG-Gateway] ERROR: root required' >&2
  exit 1
}

managed_port=""
if command -v python3 >/dev/null 2>&1 && [[ -f "$STATE_PATH" ]]; then
  managed_port="$(
    python3 - "$STATE_PATH" <<'PY'
import json
import sys
from pathlib import Path

try:
    state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError):
    raise SystemExit(0)
firewall = state.get("firewall") if isinstance(state, dict) else None
if not isinstance(firewall, dict) or firewall.get("managed") is not True:
    raise SystemExit(0)
try:
    port = int(firewall.get("port"))
except (TypeError, ValueError):
    raise SystemExit(0)
if 1 <= port <= 65535:
    print(port)
PY
  )"
fi

if [[ -n "$managed_port" ]] && command -v ufw >/dev/null 2>&1; then
  ufw --force delete allow "${managed_port}/tcp" >/dev/null 2>&1 || true
fi

systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
rm -f -- "$UNIT"
systemctl daemon-reload
rm -rf -- "$PREFIX" "$CONFIG_DIR"
rm -rf -- "$STATE_DIR/xdg-data" "$STATE_DIR/xdg-config"

if id -u sg-naiveproxy >/dev/null 2>&1; then
  userdel sg-naiveproxy >/dev/null 2>&1 || true
fi
if getent group sg-naiveproxy >/dev/null 2>&1; then
  groupdel sg-naiveproxy >/dev/null 2>&1 || true
fi
if [[ -d "$STATE_DIR" ]]; then
  chown -R root:root "$STATE_DIR" >/dev/null 2>&1 || true
fi

if command -v python3 >/dev/null 2>&1 && [[ -f "$STATE_PATH" ]]; then
  python3 - "$STATE_PATH" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError):
    raise SystemExit(0)
if not isinstance(state, dict):
    raise SystemExit(0)
state["firewall"] = {"active": False, "managed": False, "port": None}
fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
temporary = Path(raw)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
PY
fi

echo '[SG-Gateway] NaiveProxy runtime removed; managed firewall rule removed; recovery state retained.'
