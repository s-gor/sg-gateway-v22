
from pathlib import Path

path = Path("deploy/update-from-github.sh")
text = path.read_text(encoding="utf-8")

anchor = 'PANEL_SERVICE="sg-gateway.service"\nHOSTD_SERVICE="sg-hostd.service"\n'
replacement = '''PANEL_SERVICE="sg-gateway.service"
HOSTD_SERVICE="sg-hostd.service"
AWG3_SERVICE="sg-gateway-awg3.service"
AWG3_CONFIG="/etc/amnezia/amneziawg/awg3.conf"
AWG3_UNIT="/etc/systemd/system/sg-gateway-awg3.service"
AWG3_ROOT="$PREFIX/awg3"
'''
if anchor not in text:
    raise SystemExit("constants anchor not found")
text = text.replace(anchor, replacement, 1)

def replace_function(src: str, name: str, next_name: str, body: str) -> str:
    start = src.index(f"{name}() {{")
    end = src.index(f"\n}}\n\n{next_name}() {{", start) + 2
    return src[:start] + body.rstrip() + src[end:]

capture = r'''capture_service_states() {
  local output="$1" service active enabled failed
  : > "$output"
  for service in \
    nginx.service xray.service mihomo.service sg-gateway-awg.service "$AWG3_SERVICE" \
    sg-gateway-singbox.service "$HOSTD_SERVICE" "$PANEL_SERVICE"; do
    active=0
    enabled=0
    failed=0
    systemctl is-active --quiet "$service" && active=1 || true
    systemctl is-enabled --quiet "$service" && enabled=1 || true
    systemctl is-failed --quiet "$service" && failed=1 || true
    printf '%s\t%s\t%s\t%s\n' "$service" "$active" "$enabled" "$failed" >> "$output"
  done
}'''
text = replace_function(text, "capture_service_states", "verify_runtime_states_unchanged", capture)

verify_states = r'''verify_runtime_states_unchanged() {
  local before="$1" service active enabled failed now now_enabled now_failed
  while IFS=$'\t' read -r service active enabled failed; do
    [[ -n "$service" ]] || continue
    case "$service" in
      "$PANEL_SERVICE"|"$HOSTD_SERVICE") continue ;;
    esac
    now=0
    now_enabled=0
    now_failed=0
    systemctl is-active --quiet "$service" && now=1 || true
    systemctl is-enabled --quiet "$service" && now_enabled=1 || true
    systemctl is-failed --quiet "$service" && now_failed=1 || true
    if [[ "$now" != "$active" || "$now_enabled" != "$enabled" || "$now_failed" != "$failed" ]]; then
      echo "Runtime service state changed: $service active $active->$now enabled $enabled->$now_enabled failed $failed->$now_failed" >&2
      return 1
    fi
  done < "$before"
}'''
text = replace_function(text, "verify_runtime_states_unchanged", "https_state", verify_states)

helper = r'''
protected_runtime_paths() {
  local https_env="$1" output="$2"
  local cert="" key=""
  # shellcheck disable=SC1090
  source "$https_env"
  cert="${HTTPS_CERT:-}"
  key="${HTTPS_KEY:-}"
  python3 - "$output" "$cert" "$key" <<'PYPROTECTED'
import os
import sys
from pathlib import Path

output = Path(sys.argv[1])
values = [
    "/etc/letsencrypt",
    "/var/lib/sg-gateway/security/tls-state.json",
    "/etc/amnezia/amneziawg/awg3.conf",
    "/etc/systemd/system/sg-gateway-awg3.service",
    "/opt/sg-gateway/awg3",
]
for raw in sys.argv[2:]:
    raw = str(raw or "").strip()
    if not raw:
        continue
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts or str(path) == "/":
        raise SystemExit(f"unsafe protected runtime path: {raw!r}")
    values.append(os.path.normpath(str(path)))
    if path.exists() or path.is_symlink():
        values.append(os.path.realpath(str(path)))

seen = set()
ordered = []
for raw in values:
    value = os.path.normpath(str(raw))
    if value == "/" or not value.startswith("/") or value in seen:
        continue
    seen.add(value)
    ordered.append(value)
output.write_text("\n".join(ordered) + "\n", encoding="utf-8")
PYPROTECTED
}
'''
insert_at = text.index("\ncreate_safety_backup() {")
text = text[:insert_at] + "\n" + helper.strip("\n") + "\n" + text[insert_at:]

backup = r'''create_safety_backup() {
  mkdir -p "$BACKUP_ROOT"
  chmod 0700 "$BACKUP_ROOT"
  BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%d-%H%M%S)-before-update"
  mkdir -p "$BACKUP_DIR"
  chmod 0700 "$BACKUP_DIR"

  capture_service_states "$BACKUP_DIR/service-state.tsv"
  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE"
  SERVICES_STOPPED=1

  https_state > "$BACKUP_DIR/https-before.env"
  protected_runtime_paths "$BACKUP_DIR/https-before.env" "$BACKUP_DIR/protected-runtime-paths.txt"

  local protected_paths=()
  mapfile -t protected_paths < "$BACKUP_DIR/protected-runtime-paths.txt"
  fingerprint_paths "${protected_paths[@]}" > "$BACKUP_DIR/protected-runtime-before.sha256"
  fingerprint_clients > "$BACKUP_DIR/clients-before.sha256"
  fingerprint_paths /etc/letsencrypt > "$BACKUP_DIR/letsencrypt-before.sha256"
  fingerprint_paths \
    /etc/nginx/nginx.conf \
    /etc/nginx/sites-available/sg-gateway \
    /etc/nginx/sites-enabled/sg-gateway \
    /etc/nginx/stream-conf.d/sg-gateway-443.conf \
    > "$BACKUP_DIR/nginx-before.sha256"

  local existing=() relative absolute
  for relative in \
    opt/sg-gateway \
    etc/sg-gateway \
    var/lib/sg-gateway \
    etc/letsencrypt \
    etc/amnezia/amneziawg/awg3.conf \
    etc/nginx/nginx.conf \
    etc/nginx/sites-available/sg-gateway \
    etc/nginx/sites-enabled/sg-gateway \
    etc/nginx/stream-conf.d/sg-gateway-443.conf \
    etc/systemd/system/sg-gateway.service \
    etc/systemd/system/sg-hostd.service \
    etc/systemd/system/sg-gateway-awg3.service; do
    if [[ -e "/$relative" || -L "/$relative" ]]; then
      existing+=("$relative")
    fi
  done

  while IFS= read -r absolute; do
    [[ -n "$absolute" && "$absolute" == /* ]] || continue
    if [[ -e "$absolute" || -L "$absolute" ]]; then
      existing+=("${absolute#/}")
    fi
  done < "$BACKUP_DIR/protected-runtime-paths.txt"

  local unique=() item
  declare -A seen=()
  for item in "${existing[@]}"; do
    [[ -n "$item" ]] || continue
    [[ -n "${seen[$item]+x}" ]] && continue
    seen[$item]=1
    unique+=("$item")
  done
  existing=("${unique[@]}")

  printf '%s\n' "${existing[@]}" > "$BACKUP_DIR/existing-paths.txt"
  tar -C / -cpf "$BACKUP_DIR/state.tar" "${existing[@]}"
  tar -tf "$BACKUP_DIR/state.tar" >/dev/null
  BACKUP_READY=1
}'''
text = replace_function(text, "create_safety_backup", "rollback_update", backup)

rollback = r'''rollback_update() {
  (( BACKUP_READY == 1 )) || return 0
  printf '\n%s[SG-Gateway Update] ROLLBACK:%s restoring the pre-update server state...\n' "$YELLOW" "$RESET"
  systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE" "$AWG3_SERVICE" >/dev/null 2>&1 || true

  local path
  for path in \
    /opt/sg-gateway \
    /etc/sg-gateway \
    /var/lib/sg-gateway \
    /etc/letsencrypt \
    /etc/amnezia/amneziawg/awg3.conf \
    /etc/nginx/sites-available/sg-gateway \
    /etc/nginx/sites-enabled/sg-gateway \
    /etc/nginx/stream-conf.d/sg-gateway-443.conf \
    /etc/systemd/system/sg-gateway.service \
    /etc/systemd/system/sg-hostd.service \
    /etc/systemd/system/sg-gateway-awg3.service; do
    rm -rf -- "$path"
  done

  while IFS= read -r path; do
    [[ -n "$path" && "$path" == /* ]] || continue
    case "$path" in
      /opt/sg-gateway|/opt/sg-gateway/*|/etc/sg-gateway|/etc/sg-gateway/*|/var/lib/sg-gateway|/var/lib/sg-gateway/*|/etc/letsencrypt|/etc/letsencrypt/*|/etc/amnezia/amneziawg/awg3.conf|/etc/systemd/system/sg-gateway-awg3.service)
        continue
        ;;
    esac
    if [[ -f "$path" || -L "$path" ]]; then
      rm -f -- "$path"
    fi
  done < "$BACKUP_DIR/protected-runtime-paths.txt"

  tar -C / -xpf "$BACKUP_DIR/state.tar"
  systemctl daemon-reload >/dev/null 2>&1 || true

  if command -v nginx >/dev/null 2>&1 && nginx -t >/dev/null 2>&1; then
    systemctl is-active --quiet nginx.service && systemctl reload nginx.service >/dev/null 2>&1 || true
  fi

  local service active enabled failed
  while IFS=$'\t' read -r service active enabled failed; do
    [[ -n "$service" ]] || continue
    if [[ "$enabled" == "1" ]]; then
      systemctl enable "$service" >/dev/null 2>&1 || true
    else
      systemctl disable "$service" >/dev/null 2>&1 || true
    fi
    if [[ "$active" == "1" ]]; then
      systemctl restart "$service" >/dev/null 2>&1 || true
    else
      systemctl stop "$service" >/dev/null 2>&1 || true
    fi
  done < "$BACKUP_DIR/service-state.tsv"

  printf '%s[SG-Gateway Update] ROLLBACK OK.%s Backup: %s\n' "$GREEN" "$RESET" "$BACKUP_DIR"
}'''
text = replace_function(text, "rollback_update", "on_error", rollback)

old_perm = r'''  chown -R root:root "$PREFIX"
  chmod 0755 "$PREFIX"
  find "$PREFIX" -path "$PREFIX/.venv" -prune -o -type d -exec chmod 0755 {} +
  find "$PREFIX" -path "$PREFIX/.venv" -prune -o -type f -exec chmod 0644 {} +
'''
new_perm = r'''  chmod 0755 "$PREFIX"
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -exec chown root:root {} +
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -type d -exec chmod 0755 {} +
  find "$PREFIX" \
    \( -path "$PREFIX/.venv" -o -path "$PREFIX/assets" -o -path "$AWG3_ROOT" \) -prune -o \
    -type f -exec chmod 0644 {} +
'''
if old_perm not in text:
    raise SystemExit("permission sweep anchor not found")
text = text.replace(old_perm, new_perm, 1)

verify = r'''verify_final() {
  local before after
  local protected_paths=()

  before="$(cat "$BACKUP_DIR/clients-before.sha256")"
  after="$(fingerprint_clients)"
  [[ "$before" == "$after" ]] || fail "Clients/credentials changed during Update"

  before="$(cat "$BACKUP_DIR/letsencrypt-before.sha256")"
  after="$(fingerprint_paths /etc/letsencrypt)"
  [[ "$before" == "$after" ]] || fail "/etc/letsencrypt changed during Update"

  mapfile -t protected_paths < "$BACKUP_DIR/protected-runtime-paths.txt"
  before="$(cat "$BACKUP_DIR/protected-runtime-before.sha256")"
  after="$(fingerprint_paths "${protected_paths[@]}")"
  [[ "$before" == "$after" ]] || fail "TLS/AWG3 protected runtime changed during Update"

  https_state > "$TEMP_DIR/https-after.env"
  cmp -s "$BACKUP_DIR/https-before.env" "$TEMP_DIR/https-after.env" || \
    fail "HTTPS certificate state changed during Update"

  before="$(cat "$BACKUP_DIR/nginx-before.sha256")"
  after="$(fingerprint_paths \
    /etc/nginx/nginx.conf \
    /etc/nginx/sites-available/sg-gateway \
    /etc/nginx/sites-enabled/sg-gateway \
    /etc/nginx/stream-conf.d/sg-gateway-443.conf)"
  [[ "$before" == "$after" ]] || fail "Nginx configuration changed during Update"

  verify_runtime_states_unchanged "$BACKUP_DIR/service-state.tsv"
  nginx -t >/dev/null

  # shellcheck disable=SC1090
  source "$BACKUP_DIR/https-before.env"
  if [[ "${HTTPS_READY:-0}" == "1" ]]; then
    curl --noproxy '*' -fsS --max-time 15 \
      --resolve "${HTTPS_DOMAIN}:${PANEL_PORT}:127.0.0.1" \
      "https://${HTTPS_DOMAIN}:${PANEL_PORT}/health" >/dev/null
  else
    curl -fsS --max-time 8 "http://127.0.0.1:${PANEL_PORT}/health" >/dev/null
  fi

  systemctl is-active --quiet "$HOSTD_SERVICE"
  systemctl is-active --quiet "$PANEL_SERVICE"
  systemctl is-active --quiet nginx.service
}'''
text = replace_function(text, "verify_final", "bind_panel_update_state", verify)

old_stage = 'run_stage 2 "Safety Backup: SG state + full /etc/letsencrypt" create_safety_backup'
if old_stage not in text:
    raise SystemExit("stage label anchor not found")
text = text.replace(old_stage, 'run_stage 2 "Safety Backup: SG state + TLS + AWG3 runtime" create_safety_backup', 1)

old_msg = "printf '[SG-Gateway Update] Nginx/Certbot/Let'\\''s Encrypt/cores were not modified.\\n'"
if old_msg not in text:
    raise SystemExit("final message anchor not found")
text = text.replace(old_msg, "printf '[SG-Gateway Update] TLS certificates/Nginx/AWG3 runtime/VPN cores were not modified.\\n'", 1)

path.write_text(text, encoding="utf-8")

Path("tests/test_update_runtime_preservation_contract.py").write_text(r'''from pathlib import Path


SCRIPT = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return SCRIPT.split(start, 1)[1].split(end, 1)[0]


def test_update_preserves_awg3_binary_tree_and_does_not_permission_sweep_it():
    deploy = _section("deploy_source() {", "restart_panel() {")
    assert '".venv"|"assets"|"awg3"' in deploy
    assert '-path "$AWG3_ROOT"' in deploy
    assert 'chown -R root:root "$PREFIX"' not in deploy


def test_safety_backup_archives_awg3_config_unit_and_protected_tls_paths():
    backup = _section("create_safety_backup() {", "rollback_update() {")
    assert "etc/amnezia/amneziawg/awg3.conf" in backup
    assert "etc/systemd/system/sg-gateway-awg3.service" in backup
    assert "protected-runtime-paths.txt" in backup
    assert "protected-runtime-before.sha256" in backup

    protected = _section("protected_runtime_paths() {", "create_safety_backup() {")
    assert '"/etc/letsencrypt"' in protected
    assert '"/var/lib/sg-gateway/security/tls-state.json"' in protected
    assert '"/opt/sg-gateway/awg3"' in protected
    assert 'cert="${HTTPS_CERT:-}"' in protected
    assert 'key="${HTTPS_KEY:-}"' in protected
    assert "os.path.realpath" in protected


def test_final_verification_rejects_tls_or_awg3_mutation_and_service_state_drift():
    verify = _section("verify_final() {", "bind_panel_update_state() {")
    assert 'fail "TLS/AWG3 protected runtime changed during Update"' in verify
    assert 'fail "HTTPS certificate state changed during Update"' in verify
    assert 'verify_runtime_states_unchanged "$BACKUP_DIR/service-state.tsv"' in verify

    services = _section("capture_service_states() {", "verify_runtime_states_unchanged() {")
    assert '"$AWG3_SERVICE"' in services
    assert "systemctl is-failed" in services


def test_rollback_restores_awg3_and_external_certificate_material():
    rollback = _section("rollback_update() {", "on_error() {")
    assert '"$AWG3_SERVICE"' in rollback
    assert "/etc/amnezia/amneziawg/awg3.conf" in rollback
    assert "/etc/systemd/system/sg-gateway-awg3.service" in rollback
    assert "protected-runtime-paths.txt" in rollback
    assert 'tar -C / -xpf "$BACKUP_DIR/state.tar"' in rollback
''', encoding="utf-8")
