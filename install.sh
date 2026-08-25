#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=${SG_GATEWAY_ROOT:-/}
if [[ -n ${SG_GATEWAY_PREFIX:-} ]]; then
  PREFIX=$SG_GATEWAY_PREFIX
elif [[ $ROOT == / ]]; then
  PREFIX=/opt/sg-gateway
else
  PREFIX=${ROOT%/}/opt/sg-gateway
fi
DATABASE=${SG_GATEWAY_DATABASE:-${ROOT%/}/var/lib/sg-gateway/sg-gateway.sqlite}
[[ $ROOT == / ]] && DATABASE=${SG_GATEWAY_DATABASE:-/var/lib/sg-gateway/sg-gateway.sqlite}

if [[ ${SG_GATEWAY_SKIP_CORE_INSTALL:-0} != 1 ]]; then
  "$ROOT_DIR/deploy/install-core.sh" "$@"
fi

PYTHON=${SG_GATEWAY_PYTHON:-$PREFIX/.venv/bin/python}
SOURCE_ROOT=${SG_GATEWAY_SOURCE_ROOT:-$PREFIX}
[[ -x $PYTHON ]] || PYTHON=${SG_GATEWAY_PYTHON:-python3}
exec "$PYTHON" -m app.maintenance.awg31_stage3a migrate \
  --source-root "$SOURCE_ROOT" \
  --root "$ROOT" \
  --database "$DATABASE"
