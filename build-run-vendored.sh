#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
exec "$ROOT/build-run.sh" "${1:-$ROOT/SG-Gateway-${VERSION}-FULL.run}"
