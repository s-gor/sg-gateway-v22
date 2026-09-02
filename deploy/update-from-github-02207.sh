#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="${SG_GATEWAY_GITHUB_REPOSITORY:-s-gor/sg-gateway-v22}"
BRANCH="${SG_GATEWAY_GITHUB_BRANCH:-dev-02207}"
PREFIX="${SG_GATEWAY_PREFIX:-/opt/sg-gateway}"
PANEL_STATE="${SG_GATEWAY_PANEL_UPDATE_STATE:-/var/lib/sg-gateway/updates/panel-state.json}"
BACKUP_ROOT="${SG_GATEWAY_UPDATE_BACKUP_ROOT:-/root/sg-gateway-update-safety}"
PANEL_SERVICE="sg-gateway.service"
HOSTD_SERVICE="sg-hostd.service"
HOSTD_UNIT="/etc/systemd/system/${HOSTD_SERVICE}"
HOSTD_HEALTH_URL="http://127.0.0.1:8090/health"
NAIVE_SERVICE="sg-gateway-naiveproxy.service"
NAIVE_UNIT="/etc/systemd/system/${NAIVE_SERVICE}"
REQUESTED_SOURCE_COMMIT="${SG_GATEWAY_SOURCE_COMMIT:-}"
TX_DIR=""
TX_BACKUP_DIR=""
SOURCE_COMMIT=""
NAIVE_UNIT_EXISTED=0
NAIVE_USER_EXISTED=0
NAIVE_GROUP_EXISTED=0
NAIVE_WAS_ACTIVE=0
NAIVE_WAS_ENABLED=0

log() { printf '[SG-Gateway 22.07] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }
cleanup() { [[ -z "$TX_DIR" ]] || rm -rf -- "$TX_DIR"; }
trap cleanup EXIT INT TERM

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "run through sudo"
[[ "$BRANCH" == "dev-02207" || "$BRANCH" == feature/02207-* ]] || \
  fail "22.07 updater refuses branch $BRANCH"
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
  fail "invalid GitHub repository: $REPOSITORY"
[[ "$REQUESTED_SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] || \
  fail "22.07 updater requires exact SG_GATEWAY_SOURCE_COMMIT"
REQUESTED_SOURCE_COMMIT="${REQUESTED_SOURCE_COMMIT,,}"
for tool in python3 systemctl curl grep install tar journalctl; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required"
done

capture_naive_prestate() {
  TX_DIR="$(mktemp -d /root/sg-gateway-02207-transaction.XXXXXX)"
  if [[ -e "$NAIVE_UNIT" || -L "$NAIVE_UNIT" ]]; then
    cp -a -- "$NAIVE_UNIT" "$TX_DIR/naive-unit"
    NAIVE_UNIT_EXISTED=1
  fi
  if id -u sg-naiveproxy >/dev/null 2>&1; then
    NAIVE_USER_EXISTED=1
  fi
  if getent group sg-naiveproxy >/dev/null 2>&1; then
    NAIVE_GROUP_EXISTED=1
  fi
  if systemctl is-active --quiet "$NAIVE_SERVICE" 2>/dev/null; then
    NAIVE_WAS_ACTIVE=1
  fi
  if systemctl is-enabled --quiet "$NAIVE_SERVICE" 2>/dev/null; then
    NAIVE_WAS_ENABLED=1
  fi
  return 0
}

dump_required_service_failure() {
  local service="$1"
  log "Service readiness diagnostics: $service"
  systemctl --no-pager --full status "$service" >&2 || true
  journalctl -u "$service" -n 80 --no-pager >&2 || true
}

wait_for_required_service() {
  local service="$1" attempt current_pid="" stable_pid="" consecutive=0 required=3
  [[ "$service" == "$HOSTD_SERVICE" ]] && required=6

  for attempt in {1..15}; do
    current_pid=""
    if systemctl is-active --quiet "$service"; then
      current_pid="$(systemctl show -p MainPID --value "$service" 2>/dev/null || true)"
      if [[ "$current_pid" =~ ^[1-9][0-9]*$ ]]; then
        if [[ "$service" != "$HOSTD_SERVICE" ]] || \
           curl -4fsS --connect-timeout 1 --max-time 2 "$HOSTD_HEALTH_URL" >/dev/null 2>&1; then
          if [[ "$current_pid" == "$stable_pid" ]]; then
            ((consecutive += 1))
          else
            stable_pid="$current_pid"
            consecutive=1
          fi
          if (( consecutive >= required )); then
            return 0
          fi
        else
          stable_pid=""
          consecutive=0
        fi
      else
        stable_pid=""
        consecutive=0
      fi
    else
      stable_pid=""
      consecutive=0
    fi
    sleep 1
  done

  return 1
}

prepare_hostd_preflight_bridge() {
  local staged="$TX_DIR/sg-hostd-preflight.service" required_env
  local url="https://raw.githubusercontent.com/${REPOSITORY}/${REQUESTED_SOURCE_COMMIT}/hostd/systemd/sg-hostd.service"

  log "Preparing exact-commit hostd preflight bridge: ${REQUESTED_SOURCE_COMMIT:0:12}"
  curl -4fL \
    --connect-timeout 15 \
    --max-time 120 \
    --retry 5 \
    --retry-all-errors \
    --retry-delay 2 \
    -o "$staged" \
    "$url" || return 1

  grep -Fqx \
    'Environment=PYTHONPATH=/opt/sg-gateway:/opt/sg-gateway/hostd' \
    "$staged" || {
      log "ERROR: preflight hostd unit has an invalid Python import path"
      return 1
    }
  grep -Fqx \
    'ReadWritePaths=-/run/sg-gateway -/usr/local/share/xray -/usr/local/etc/xray -/etc/amnezia/amneziawg -/etc/sysctl.d -/etc/mihomo -/etc/sing-box -/etc/sg-gateway/naiveproxy -/var/lib/sg-gateway' \
    "$staged" || {
      log "ERROR: preflight hostd unit has invalid writable paths"
      return 1
    }
  grep -Fqx 'LogsDirectory=sg-gateway' "$staged" || {
    log "ERROR: preflight hostd unit has no writable operation job log directory"
    return 1
  }
  for required_env in \
    'EnvironmentFile=/etc/sg-gateway/sg-gateway.env' \
    'EnvironmentFile=/etc/sg-gateway/runtime.env' \
    'EnvironmentFile=/etc/sg-gateway/engine-secrets.env'; do
    grep -Fqx "$required_env" "$staged" || {
      log "ERROR: preflight hostd unit dropped required runtime environment: $required_env"
      return 1
    }
  done
  grep -Fq 'sg_hostd.app:app' "$staged" || {
    log "ERROR: preflight hostd unit has an unexpected ExecStart"
    return 1
  }

  install -o root -g root -m 0644 "$staged" "$HOSTD_UNIT" || return 1
  systemctl daemon-reload || return 1
  if ! systemctl restart "$HOSTD_SERVICE"; then
    dump_required_service_failure "$HOSTD_SERVICE"
    return 1
  fi
  if ! wait_for_required_service "$HOSTD_SERVICE"; then
    log "ERROR: hostd did not remain ready after exact-commit unit bridge"
    dump_required_service_failure "$HOSTD_SERVICE"
    return 1
  fi

  log "Hostd preflight bridge ready: stable MainPID + /health"
  return 0
}

recover_required_services_after_panel_failure() {
  local service recovery_failed=0

  if ! systemctl daemon-reload >/dev/null 2>&1; then
    log "ROLLBACK INCOMPLETE: systemd daemon-reload failed"
    recovery_failed=1
  fi

  for service in "$HOSTD_SERVICE" "$PANEL_SERVICE"; do
    if ! systemctl is-active --quiet "$service"; then
      if ! systemctl start "$service"; then
        log "ROLLBACK INCOMPLETE: failed to start required service $service"
        dump_required_service_failure "$service"
        recovery_failed=1
        continue
      fi
    fi

    if ! wait_for_required_service "$service"; then
      log "ROLLBACK INCOMPLETE: required service did not remain ready: $service"
      dump_required_service_failure "$service"
      recovery_failed=1
    else
      log "ROLLBACK VERIFIED: $service is ready"
    fi
  done

  return "$recovery_failed"
}

run_panel_update() {
  local panel_rc

  prepare_hostd_preflight_bridge || return 1

  set +e
  GIT_TERMINAL_PROMPT=0 \
  GIT_ASKPASS=/bin/false \
  GCM_INTERACTIVE=Never \
  SG_GATEWAY_GITHUB_REPOSITORY="$REPOSITORY" \
  SG_GATEWAY_GIT_URL="https://github.com/${REPOSITORY}.git" \
  SG_GATEWAY_GITHUB_BRANCH="$BRANCH" \
  SG_GATEWAY_SOURCE_COMMIT="$REQUESTED_SOURCE_COMMIT" \
    bash "$PREFIX/deploy/update-from-github.sh"
  panel_rc=$?
  set -e

  if (( panel_rc != 0 )); then
    log "Base panel update failed; verifying required services after rollback..."
    if recover_required_services_after_panel_failure; then
      log "Base panel update failed; required services are ready after rollback."
    else
      log "ERROR: base panel update failed and rollback recovery is incomplete"
    fi
    return "$panel_rc"
  fi

  return 0
}

resolve_safety_backup() {
  local resolved
  resolved="$(python3 - "$PANEL_STATE" "$BACKUP_ROOT" <<'PY'
import json
import re
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
backup_root = Path(sys.argv[2])
try:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError) as exc:
    raise SystemExit(f"cannot read panel update state: {exc}")
name = str(payload.get("backup") or "").strip()
commit = str(payload.get("commit") or "").strip().lower()
if not name or name in {".", ".."} or Path(name).name != name:
    raise SystemExit("panel update state has no safe backup name")
if not re.fullmatch(r"[0-9a-f]{40}", commit):
    raise SystemExit("panel update state has no exact source commit")
path = backup_root / name
required = ("state.tar", "existing-paths.txt", "service-state.tsv")
if not path.is_dir() or any(not (path / item).is_file() for item in required):
    raise SystemExit(f"incomplete Safety Backup: {path}")
print(f"{path}\t{commit}")
PY
)" || fail "cannot resolve the completed Safety Backup and source commit"
  IFS=$'\t' read -r TX_BACKUP_DIR SOURCE_COMMIT <<< "$resolved"
  [[ -n "$TX_BACKUP_DIR" ]] || fail "empty Safety Backup path"
  [[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "invalid exact source commit"
  [[ "$SOURCE_COMMIT" == "$REQUESTED_SOURCE_COMMIT" ]] || \
    fail "panel update source commit does not match requested exact commit"
  tar -tf "$TX_BACKUP_DIR/state.tar" >/dev/null 2>&1 || \
    fail "Safety Backup archive is invalid: $TX_BACKUP_DIR"
}

stage_naive_hostd_unit() {
  local staged="$TX_DIR/sg-hostd.service" required_env
  local target="$PREFIX/hostd/systemd/sg-hostd.service"
  local url="https://raw.githubusercontent.com/${REPOSITORY}/${SOURCE_COMMIT}/hostd/systemd/sg-hostd.service"

  [[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
    log "ERROR: exact source commit is unavailable for hostd unit staging"
    return 1
  }
  curl -4fL \
    --connect-timeout 15 \
    --max-time 120 \
    --retry 5 \
    --retry-all-errors \
    --retry-delay 2 \
    -o "$staged" \
    "$url" || return 1

  grep -Fqx \
    'ReadWritePaths=-/run/sg-gateway -/usr/local/share/xray -/usr/local/etc/xray -/etc/amnezia/amneziawg -/etc/sysctl.d -/etc/mihomo -/etc/sing-box -/etc/sg-gateway/naiveproxy -/var/lib/sg-gateway' \
    "$staged" || {
      log "ERROR: fetched hostd unit is not NaiveProxy-capable"
      return 1
    }
  grep -Fqx \
    'Environment=PYTHONPATH=/opt/sg-gateway:/opt/sg-gateway/hostd' \
    "$staged" || {
      log "ERROR: fetched hostd unit has an invalid Python import path"
      return 1
    }
  grep -Fqx 'LogsDirectory=sg-gateway' "$staged" || {
    log "ERROR: fetched hostd unit has no writable operation job log directory"
    return 1
  }
  for required_env in \
    'EnvironmentFile=/etc/sg-gateway/sg-gateway.env' \
    'EnvironmentFile=/etc/sg-gateway/runtime.env' \
    'EnvironmentFile=/etc/sg-gateway/engine-secrets.env'; do
    grep -Fqx "$required_env" "$staged" || {
      log "ERROR: fetched hostd unit dropped required runtime environment: $required_env"
      return 1
    }
  done
  grep -Fq 'sg_hostd.app:app' "$staged" || {
    log "ERROR: fetched hostd unit has an unexpected ExecStart"
    return 1
  }

  install -d -m 0755 "$(dirname "$target")" || return 1
  install -o root -g root -m 0644 "$staged" "$target" || return 1
}

restore_naive_identity_and_unit() {
  systemctl stop "$NAIVE_SERVICE" >/dev/null 2>&1 || true
  if (( NAIVE_UNIT_EXISTED == 1 )); then
    cp -a -- "$TX_DIR/naive-unit" "$NAIVE_UNIT"
  else
    rm -f -- "$NAIVE_UNIT"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true

  if (( NAIVE_WAS_ENABLED == 1 )); then
    systemctl enable "$NAIVE_SERVICE" >/dev/null 2>&1 || true
  else
    systemctl disable "$NAIVE_SERVICE" >/dev/null 2>&1 || true
  fi
  if (( NAIVE_WAS_ACTIVE == 1 )); then
    systemctl start "$NAIVE_SERVICE" >/dev/null 2>&1 || true
  else
    systemctl stop "$NAIVE_SERVICE" >/dev/null 2>&1 || true
  fi

  if (( NAIVE_USER_EXISTED == 0 )); then
    userdel sg-naiveproxy >/dev/null 2>&1 || true
  fi
  if (( NAIVE_GROUP_EXISTED == 0 )); then
    groupdel sg-naiveproxy >/dev/null 2>&1 || true
  fi
}

rollback_panel_update() {
  local core="$PREFIX/deploy/update-from-github-core.sh"
  local rollback_rc=0
  [[ -f "$core" ]] || {
    log "ROLLBACK ERROR: core updater is missing: $core"
    return 1
  }
  log "NaiveProxy stage failed; restoring the complete pre-update server state..."
  SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1
  # shellcheck disable=SC1090
  source "$core"
  BACKUP_DIR="$TX_BACKUP_DIR"
  BACKUP_READY=1
  UPDATE_FINISHED=0
  rollback_update || rollback_rc=$?
  restore_naive_identity_and_unit
  recover_required_services_after_panel_failure || rollback_rc=1
  return "$rollback_rc"
}

run_naive_stage() {
  stage_naive_hostd_unit || return 1
  SG_GATEWAY_SOURCE_ROOT="$PREFIX" \
  SG_GATEWAY_UPDATE_BRANCH="$BRANCH" \
    bash "$PREFIX/deploy/install-naiveproxy.sh" || return 1

  if ! wait_for_required_service "$HOSTD_SERVICE"; then
    log "ERROR: hostd did not remain ready after NaiveProxy post-stage"
    dump_required_service_failure "$HOSTD_SERVICE"
    return 1
  fi
  if ! wait_for_required_service "$PANEL_SERVICE"; then
    log "ERROR: panel did not remain ready after NaiveProxy post-stage"
    dump_required_service_failure "$PANEL_SERVICE"
    return 1
  fi

  log "Post-Naive readiness verified: hostd + panel"
  return 0
}

capture_naive_prestate
run_panel_update
resolve_safety_backup

set +e
run_naive_stage
naive_rc=$?
set -e
if (( naive_rc != 0 )); then
  if rollback_panel_update; then
    fail "NaiveProxy post-update stage failed; panel update was rolled back"
  fi
  fail "NaiveProxy post-update stage failed and rollback was incomplete"
fi

log "Update and NaiveProxy runtime transaction completed. The selected TCP port will be managed when settings are applied."
