#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${SG_GATEWAY_GITHUB_REPOSITORY:-s-gor/sg-gateway-v22}"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-${SG_GATEWAY_UPDATE_BRANCH:-main}}"
GIT_URL="${SG_GATEWAY_GIT_URL:-https://github.com/${REPOSITORY}.git}"
RAW_BASE="${SG_GATEWAY_RAW_BASE_URL:-https://raw.githubusercontent.com/${REPOSITORY}}"
BOOTSTRAP_DIR=""

fail() {
  printf '[SG-Gateway Update] bootstrap error: %s\n' "$*" >&2
  return 1
}

cleanup() {
  if [[ -n "$BOOTSTRAP_DIR" && -d "$BOOTSTRAP_DIR" ]]; then
    rm -rf -- "$BOOTSTRAP_DIR"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

urlencode_ref() {
  python3 - "$1" <<'PYURL'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PYURL
}

resolve_commit() {
  local resolved="${SG_GATEWAY_SOURCE_COMMIT:-}"
  local encoded

  if [[ "$resolved" =~ ^[0-9a-fA-F]{40}$ ]]; then
    printf '%s\n' "${resolved,,}"
    return 0
  fi

  if command -v git >/dev/null 2>&1; then
    resolved="$(git ls-remote --exit-code "$GIT_URL" "refs/heads/$BRANCH" 2>/dev/null | awk 'NR==1 {print $1}' || true)"
  fi

  if [[ ! "$resolved" =~ ^[0-9a-fA-F]{40}$ ]]; then
    encoded="$(urlencode_ref "$BRANCH")"
    resolved="$(
      curl -4 -fsSL --max-time 20 -A 'SG-Gateway-Updater' \
        "https://api.github.com/repos/${REPOSITORY}/commits/${encoded}" 2>/dev/null \
      | python3 -c 'import json,re,sys; value=str(json.load(sys.stdin).get("sha") or "").strip(); print(value.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", value) else "")' \
        2>/dev/null || true
    )"
  fi

  [[ "$resolved" =~ ^[0-9a-fA-F]{40}$ ]] || fail "cannot resolve exact commit for update channel $BRANCH"
  printf '%s\n' "${resolved,,}"
}

main() {
  command -v curl >/dev/null 2>&1 || fail "required command is missing: curl"
  command -v python3 >/dev/null 2>&1 || fail "required command is missing: python3"
  command -v bash >/dev/null 2>&1 || fail "required command is missing: bash"

  local commit core rc
  commit="$(resolve_commit)"
  BOOTSTRAP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sg-gateway-update-bootstrap.XXXXXX")"
  core="$BOOTSTRAP_DIR/update-from-github-core.sh"

  printf '[SG-Gateway Update] Bootstrap commit: %s\n' "$commit"
  curl -4 -fL --retry 6 --retry-all-errors --retry-delay 2 --connect-timeout 20 \
    "$RAW_BASE/$commit/deploy/update-from-github-core.sh" -o "$core"
  [[ -s "$core" ]] || fail "downloaded core updater is empty"
  head -n 1 "$core" | grep -Eq '^#!.*(ba)?sh([[:space:]]|$)' || \
    fail "downloaded core updater has no shell shebang"
  grep -Fq 'SG_GATEWAY_UPDATE_CORE' "$core" || \
    fail "downloaded file is not the SG-Gateway core updater"
  bash -n "$core" || fail "downloaded core updater failed syntax validation"

  set +e
  SG_GATEWAY_SOURCE_COMMIT="$commit" bash "$core" "$@"
  rc=$?
  set -e
  return "$rc"
}

main "$@"
