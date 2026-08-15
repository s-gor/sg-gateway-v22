#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/build-run.sh" "${1:-$ROOT/SG-Gateway-02112-FULL-CLEAN.run}"
