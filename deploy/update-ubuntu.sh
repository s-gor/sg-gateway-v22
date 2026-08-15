#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX="${SG_GATEWAY_APP_ROOT:-/opt/sg-gateway}"
PYTHON="$PREFIX/.venv/bin/python"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run through sudo."
    exit 1
fi

if [[ ! -x "$PYTHON" ]] || [[ ! -f "$PREFIX/hostd/sg_hostd/panel_update_runtime.py" ]]; then
    echo "SG-Gateway safe updater is not installed."
    echo "Use the current full SG-Gateway installer first."
    exit 1
fi

export PYTHONPATH="$PREFIX:$PREFIX/hostd"
export SG_GATEWAY_ENV=production
export SG_GATEWAY_DATA_DIR=/var/lib/sg-gateway
export SG_GATEWAY_LOG_DIR=/var/log/sg-gateway

cd "$PREFIX"
exec "$PYTHON" - <<'PY'
import json
from sg_hostd.panel_update_runtime import update_panel

print(json.dumps(update_panel(), ensure_ascii=False, indent=2))
PY
