#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX=${SG_GATEWAY_PREFIX:-/opt/sg-gateway}
PYTHON=${SG_GATEWAY_PYTHON:-$PREFIX/.venv/bin/python}
DATABASE=${SG_GATEWAY_DATABASE:-/var/lib/sg-gateway/sg-gateway.sqlite}
ROOT=${SG_GATEWAY_ROOT:-/}
PURGE=()

if [[ "${1:-}" == "--purge-data" ]]; then
  PURGE=(--purge-data)
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--purge-data]" >&2
  exit 2
fi

exec "$PYTHON" -m app.maintenance.awg31_stage3a uninstall \
  --source-root "$PREFIX" --root "$ROOT" --database "$DATABASE" "${PURGE[@]}"
