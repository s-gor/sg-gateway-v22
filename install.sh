#!/usr/bin/env bash
set -Eeuo pipefail

MASTER_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SG_GATEWAY_SOURCE_DIR="$MASTER_ROOT"
# The historical 22.08 implementation is retained as a function library only.
# This file is the single installation master and owns all 24 stages.
# shellcheck source=deploy/install-core-02208.sh
source "$MASTER_ROOT/deploy/install-core-02208.sh"

TOTAL_STAGES=24
INSTALLER_BUILD="02208-unified-24stage"
NAIVEPROXY_VERSION="v2.11.2-naive"
NAIVEPROXY_ARCHIVE_SHA256="19eccb7321dd877a5fb4a3dba6ef1b745185188b616c96cc6201f1a1fc0380a8"
NAIVEPROXY_URL="https://github.com/klzgrad/forwardproxy/releases/download/${NAIVEPROXY_VERSION}/caddy-forwardproxy-naive.tar.xz"
NAIVEPROXY_PORT="8447"
NAIVEPROXY_PREFIX="/opt/sg-gateway/naiveproxy"
NAIVEPROXY_CONFIG="/etc/sg-gateway/naiveproxy"
NAIVEPROXY_STATE="/var/lib/sg-gateway/naiveproxy"
NAIVEPROXY_SERVICE="sg-gateway-naiveproxy.service"

# First-class rollback ownership. opt/sg-gateway is already covered, but the
# explicit entries make the NaiveProxy contract visible and independently auditable.
MANAGED_PATHS+=(
  etc/systemd/system/sg-gateway-naiveproxy.service
  etc/sg-gateway/naiveproxy
  var/lib/sg-gateway/naiveproxy
  opt/sg-gateway/naiveproxy
)

create_backup() {
  install -d -m 0700 "$BACKUP_ROOT"
  [[ -n "$BACKUP_DIR" ]] || BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-before-sg-gateway-02208"
  install -d -m 0700 "$BACKUP_DIR"

  local existing=()
  local relative
  for relative in "${MANAGED_PATHS[@]}"; do
    [[ -e "/$relative" || -L "/$relative" ]] && existing+=("$relative")
  done
  printf '%s\n' "${existing[@]}" > "$BACKUP_DIR/existing-paths.txt"
  if (( ${#existing[@]} > 0 )); then
    tar -C / -cpf "$BACKUP_DIR/managed-paths.tar" "${existing[@]}"
  fi

  : > "$BACKUP_DIR/service-state.tsv"
  local service active enabled
  for service in \
    sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-awg31.service \
    sg-gateway-singbox.service sg-gateway-naiveproxy.service \
    sg-gateway.service nginx.service; do
    active=0
    enabled=0
    systemctl is-active --quiet "$service" && active=1 || true
    systemctl is-enabled --quiet "$service" && enabled=1 || true
    printf '%s\t%s\t%s\n' "$service" "$active" "$enabled" >> "$BACKUP_DIR/service-state.tsv"
  done

  printf '%s\n' "$VERSION" > "$BACKUP_DIR/new-version.txt"
  if (( UPDATE_MODE == 1 )) && [[ -f "$DATA_DIR/sg-gateway.sqlite" ]]; then
    fingerprint_clients "$DATA_DIR/sg-gateway.sqlite" "$BACKUP_DIR/client-identities-before.sha256"
  fi
  echo "Backup: $BACKUP_DIR"
}

restore_backup() {
  [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
  printf '\n%s[SG-Gateway] [ОТКАТ]%s Восстанавливаю предыдущую установку SG-Gateway.\n' "$YELLOW" "$RESET"

  systemctl stop \
    sg-gateway.service sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-awg31.service \
    sg-gateway-singbox.service sg-gateway-naiveproxy.service nginx.service \
    >/dev/null 2>&1 || true

  rollback_remove_managed_paths /

  if [[ -f "$BACKUP_DIR/managed-paths.tar" ]]; then
    tar -C / -xpf "$BACKUP_DIR/managed-paths.tar"
  fi
  if [[ -f "$BACKUP_DIR/nginx-after-packages.tar" ]]; then
    tar -C / -xpf "$BACKUP_DIR/nginx-after-packages.tar"
  fi
  systemctl daemon-reload || true

  local state_file="$BACKUP_DIR/service-state.tsv"
  local service active enabled failures=0
  declare -A was_active=()
  declare -A was_enabled=()

  if [[ -f "$state_file" ]]; then
    while IFS=$'\t' read -r service active enabled; do
      [[ -n "$service" ]] || continue
      was_active["$service"]="$active"
      was_enabled["$service"]="$enabled"
    done < "$state_file"
  fi

  local services=(
    sg-hostd.service xray.service mihomo.service
    sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-awg31.service
    sg-gateway-singbox.service sg-gateway-naiveproxy.service
    sg-gateway.service nginx.service
  )

  for service in "${services[@]}"; do
    if [[ "${was_enabled[$service]:-0}" == "1" ]]; then
      systemctl enable "$service" >/dev/null 2>&1 || true
    elif [[ -n "${was_enabled[$service]+x}" ]]; then
      systemctl disable "$service" >/dev/null 2>&1 || true
    fi
  done

  for service in "${services[@]}"; do
    if [[ "${was_active[$service]:-0}" == "1" ]]; then
      if ! systemctl restart "$service" >>"$INSTALL_LOG" 2>&1; then
        echo "ROLLBACK SERVICE FAILED: $service" >>"$INSTALL_LOG"
        failures=$((failures + 1))
      fi
    elif [[ -n "${was_active[$service]+x}" ]]; then
      systemctl stop "$service" >/dev/null 2>&1 || true
    fi
  done

  if [[ ! -f "$state_file" ]]; then
    for service in sg-hostd.service sg-gateway.service nginx.service; do
      [[ -f "/etc/systemd/system/$service" || "$service" == "nginx.service" ]] || continue
      systemctl enable --now "$service" >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    done
    [[ ! -f /usr/local/etc/xray/config.json ]] || \
      systemctl enable --now xray.service >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    [[ ! -f /etc/mihomo/config.yaml ]] || \
      systemctl enable --now mihomo.service >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    if [[ -f "$NAIVEPROXY_CONFIG/Caddyfile" ]]; then
      systemctl enable --now "$NAIVEPROXY_SERVICE" >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    fi
  fi

  if [[ -f "$state_file" ]]; then
    while IFS=$'\t' read -r service active enabled; do
      [[ "$active" == "1" ]] || continue
      if ! systemctl is-active --quiet "$service"; then
        echo "ROLLBACK VERIFY FAILED: $service is not active" >>"$INSTALL_LOG"
        failures=$((failures + 1))
      fi
    done < "$state_file"
  fi

  if (( failures > 0 )); then
    printf '%s[SG-Gateway] [ОТКАТ НЕПОЛНЫЙ]%s Файлы восстановлены, но не все прежние службы запустились.\n' "$RED" "$RESET"
    printf '[SG-Gateway] Резервная копия: %s\n' "$BACKUP_DIR"
    return 1
  fi
  printf '%s[SG-Gateway] [ОТКАТ OK]%s Предыдущая установка и активные службы восстановлены.\n' "$GREEN" "$RESET"
  printf '[SG-Gateway] Резервная копия: %s\n' "$BACKUP_DIR"
}

stage_prepare_install_context() {
  verify_vendor_core_set

  if detect_existing_install; then
    printf '[SG-Gateway] Обнаружена установленная полная панель %s. Выполняется безопасное обновление.\n' \
      "${EXISTING_VERSION:-неизвестной версии}"
    if (( SERVER_NAME_MIGRATION_REQUIRED == 1 )); then
      SERVER_NAME="sg-gateway"
      [[ "$COUNTRY_CODE" != "unknown" ]] && SERVER_NAME="sg-gateway-${COUNTRY_CODE}"
      SERVER_NAME="$(normalize_hostname "$SERVER_NAME")"
      valid_hostname "$SERVER_NAME" || SERVER_NAME="sg-gateway"
    fi
  elif detect_minimal_013_install; then
    printf '[SG-Gateway] Обнаружена рабочая база SG-Gateway 013; выполняется миграция.\n'
  else
    if ! load_resume_state; then
      collect_automatic_parameters
      save_resume_state
    fi
  fi

  AWG_PORT="$DEFAULT_AWG_PORT"
  AWG3_PORT="$DEFAULT_AWG3_PORT"
  BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-before-sg-gateway-02208"
}

stage_vendor_media_contract() {
  verify_vendor_core_set
}

stage_backup_and_prepare() {
  create_backup
  MUTATION_STARTED=1
  systemctl stop \
    sg-gateway.service sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-awg31.service \
    sg-gateway-singbox.service sg-gateway-naiveproxy.service \
    >/dev/null 2>&1 || true

  rm -rf "$PREFIX.new" "$PREFIX"
  install -d -m 0755 "$PREFIX.new"
  cp -a "$SOURCE_DIR/." "$PREFIX.new/"
  rm -rf "$PREFIX.new/vendor/cores"
  rm -f "$PREFIX.new/install.sh"
  mv "$PREFIX.new" "$PREFIX"

  verify_installed_connections_ui_contract "$PREFIX"
  chown -R root:root "$PREFIX"
  chmod -R a+rX "$PREFIX"
  chmod -R go-w "$PREFIX"
  chmod 0755 "$PREFIX"
  chmod 0755 "$PREFIX/deploy/configure-panel-access.sh"
  chmod 0755 "$PREFIX/deploy/sg-gateway-awg3-userspace.sh"
}

stage_system_packages_02208() {
  stage_system_packages
  apt_get install -y xz-utils
}

stage_awg2_runtime() {
  verify_vendor_core_set
  install_amneziawg_from_vendor
}

stage_awg3_runtime() {
  verify_vendor_core_set
  install_amneziawg3_userspace_from_vendor
}

stage_xray_runtime() {
  verify_vendor_core_set
  local installed_xray=""
  if [[ -x /usr/local/bin/xray ]]; then
    installed_xray="$(xray_installed_version)"
  fi
  if (( UPDATE_MODE == 1 )) && [[ -n "$installed_xray" && "$installed_xray" != "v" ]] \
    && dpkg --compare-versions "${installed_xray#v}" ge "${XRAY_MINIMUM_VERSION#v}"; then
    echo "[SG-Gateway] Xray $installed_xray сохранён при обновлении."
  else
    install_xray_from_vendor
  fi
  verify_xray_version
  systemctl disable --now xray.service >/dev/null 2>&1 || true
}

stage_mihomo_runtime() {
  verify_vendor_core_set
  install_mihomo_from_vendor
}

stage_singbox_and_warp_runtime() {
  verify_vendor_core_set
  install_sing_box_from_vendor
  install_wgcf_from_vendor
}

stage_naiveproxy_runtime() {
  local work archive candidate binary_sha256
  [[ "$(uname -m)" == "x86_64" ]] || {
    echo "NaiveProxy pinned runtime supports linux/amd64 only" >&2
    return 1
  }

  for tool in curl tar sha256sum systemctl; do
    command -v "$tool" >/dev/null 2>&1 || {
      echo "NaiveProxy requires $tool" >&2
      return 1
    }
  done

  systemctl stop "$NAIVEPROXY_SERVICE" >/dev/null 2>&1 || true

  if ! getent group sg-naiveproxy >/dev/null; then
    groupadd --system sg-naiveproxy
  fi
  if ! id -u sg-naiveproxy >/dev/null 2>&1; then
    useradd --system --gid sg-naiveproxy --home-dir "$NAIVEPROXY_STATE" --shell /usr/sbin/nologin sg-naiveproxy
  fi

  install -d -m 0755 "$NAIVEPROXY_PREFIX/bin"
  install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 "$NAIVEPROXY_STATE"
  install -d -o sg-naiveproxy -g sg-naiveproxy -m 0750 "$NAIVEPROXY_STATE/site"
  install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 \
    "$NAIVEPROXY_STATE/xdg-data" "$NAIVEPROXY_STATE/xdg-config"

  work="$(mktemp -d /tmp/sg-gateway-naiveproxy.XXXXXX)"
  archive="$work/caddy-forwardproxy-naive.tar.xz"
  curl -fsSL --retry 3 --connect-timeout 15 -o "$archive" "$NAIVEPROXY_URL"
  printf '%s  %s\n' "$NAIVEPROXY_ARCHIVE_SHA256" "$archive" | sha256sum -c - >/dev/null
  tar -xJf "$archive" -C "$work"
  candidate="$work/caddy-forwardproxy-naive/caddy"
  [[ -x "$candidate" ]] || {
    rm -rf "$work"
    echo "Pinned NaiveProxy archive does not contain executable caddy" >&2
    return 1
  }
  "$candidate" list-modules | grep -qx 'http.handlers.forward_proxy'

  install -m 0755 "$candidate" "$NAIVEPROXY_PREFIX/bin/caddy.new"
  mv -f "$NAIVEPROXY_PREFIX/bin/caddy.new" "$NAIVEPROXY_PREFIX/bin/caddy"
  binary_sha256="$(sha256sum "$NAIVEPROXY_PREFIX/bin/caddy" | awk '{print $1}')"
  printf '%s  %s\n' "$binary_sha256" "$NAIVEPROXY_PREFIX/bin/caddy" > "$NAIVEPROXY_PREFIX/CADDY-SHA256"
  cat > "$NAIVEPROXY_PREFIX/VERSIONS.env" <<EOF
RUNTIME_VERSION=$NAIVEPROXY_VERSION
RUNTIME_ARCHIVE_SHA256=$NAIVEPROXY_ARCHIVE_SHA256
RUNTIME_BINARY_SHA256=$binary_sha256
RUNTIME_URL=$NAIVEPROXY_URL
EOF
  rm -rf "$work"
}

stage_configuration_and_database_02208() {
  stage_configuration_and_database

  chmod o+x "$CONFIG_DIR"
  install -d -o root -g sg-naiveproxy -m 0750 "$NAIVEPROXY_CONFIG"

  cat >> "$CONFIG_DIR/runtime.env" <<EOF
SG_GATEWAY_NAIVEPROXY_INSTALLED_BY_SG=1
SG_GATEWAY_NAIVEPROXY_VERSION=${NAIVEPROXY_VERSION}
SG_GATEWAY_NAIVEPROXY_PORT=${NAIVEPROXY_PORT}
EOF

  runuser -u "$PANEL_USER" -- env \
    PYTHONPATH="$PREFIX" \
    SG_GATEWAY_ENV=production \
    SG_GATEWAY_HOST=127.0.0.1 \
    SG_GATEWAY_PORT="$BACKEND_PORT" \
    SG_GATEWAY_PUBLIC_PORT="$PANEL_PORT" \
    SG_GATEWAY_PUBLIC_ADDRESS="$PUBLIC_ADDRESS" \
    SG_GATEWAY_SERVER_NAME="$SERVER_NAME" \
    SG_GATEWAY_COUNTRY_CODE="$COUNTRY_CODE" \
    SG_GATEWAY_DATA_DIR="$DATA_DIR" \
    SG_GATEWAY_LOG_DIR="$LOG_DIR" \
    SG_GATEWAY_SECRET_KEY="$SECRET_KEY" \
    SG_GATEWAY_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    SG_GATEWAY_ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
    "$PREFIX/.venv/bin/python" - <<'PYNAIVEDB'
from app.naiveproxy.integration import install
from app.db import connect

install()
with connect() as connection:
    row = connection.execute(
        "SELECT port FROM connection_settings WHERE engine='naiveproxy'"
    ).fetchone()
assert row is not None, "NaiveProxy connection settings are missing"
assert int(row["port"]) == 8447, row["port"]
print("NaiveProxy database seed: OK")
PYNAIVEDB
}

stage_systemd_units_02208() {
  stage_systemd_units
  install -m 0644 "$PREFIX/deploy/$NAIVEPROXY_SERVICE" "/etc/systemd/system/$NAIVEPROXY_SERVICE"
  systemctl daemon-reload
}

stage_firewall_and_network_02208() {
  stage_firewall_and_network
  local ufw_state=""
  ufw_state="$(ufw status 2>/dev/null || true)"
  if grep -q '^Status: active' <<<"$ufw_state"; then
    ufw allow "${NAIVEPROXY_PORT}/tcp"
  fi
}

restore_update_runtime_services() {
  (( UPDATE_MODE == 1 )) || return 0
  local service
  for service in \
    mihomo.service sg-gateway-awg.service sg-gateway-awg3.service \
    sg-gateway-awg31.service sg-gateway-singbox.service sg-gateway-naiveproxy.service; do
    if service_was_enabled_before_update "$service"; then
      systemctl_with_retry enable "$service"
    fi
    if service_was_active_before_update "$service"; then
      systemctl_with_retry restart "$service"
      systemctl is-active --quiet "$service"
      echo "Update runtime restored: $service"
    fi
  done
}

verify_naiveproxy_install_contract() {
  [[ -x "$NAIVEPROXY_PREFIX/bin/caddy" ]]
  [[ -f "$NAIVEPROXY_PREFIX/VERSIONS.env" ]]
  [[ -f "/etc/systemd/system/$NAIVEPROXY_SERVICE" ]]
  [[ -d "$NAIVEPROXY_CONFIG" ]]
  [[ -d "$NAIVEPROXY_STATE" ]]
  id -u sg-naiveproxy >/dev/null 2>&1
  getent group sg-naiveproxy >/dev/null

  "$NAIVEPROXY_PREFIX/bin/caddy" list-modules | grep -qx 'http.handlers.forward_proxy'
  grep -Fq "ConditionPathExists=/etc/sg-gateway/naiveproxy/Caddyfile" \
    "/etc/systemd/system/$NAIVEPROXY_SERVICE"

  PYTHONPATH="$PREFIX" SG_GATEWAY_DATA_DIR="$DATA_DIR" "$PREFIX/.venv/bin/python" - <<'PYNAIVEVERIFY'
from app.db import connect
with connect() as connection:
    row = connection.execute(
        "SELECT host, port FROM connection_settings WHERE engine='naiveproxy'"
    ).fetchone()
assert row is not None, "NaiveProxy DB row missing"
assert int(row["port"]) == 8447, row["port"]
print("NaiveProxy DB contract: OK")
PYNAIVEVERIFY

  local body
  body="$(curl -fsS --max-time 10 "http://127.0.0.1:${HOSTD_PORT}/commands")"
  python3 - "$body" <<'PYNAIVECOMMANDS'
import json, sys
value = json.loads(sys.argv[1])
commands = set(value.get("commands", []))
required = {"naiveproxy.status", "naiveproxy.sync"}
missing = sorted(required - commands)
assert not missing, f"Missing NaiveProxy hostd commands: {missing}"
print("NaiveProxy hostd commands: OK")
PYNAIVECOMMANDS

  if [[ -f "$NAIVEPROXY_CONFIG/Caddyfile" ]]; then
    systemctl_with_retry enable "$NAIVEPROXY_SERVICE"
    systemctl_with_retry restart "$NAIVEPROXY_SERVICE"
    systemctl is-active --quiet "$NAIVEPROXY_SERVICE"
  fi
}

stage_final_contract() {
  verify_client_identities_after_update
  verify_installed_connections_ui_contract "$PREFIX"
  verify_xray_version
  systemctl is-active --quiet sg-hostd.service
  systemctl is-active --quiet sg-gateway.service
  systemctl is-active --quiet nginx.service
}

main() {
  require_root
  require_supported_ubuntu
  umask 022
  prepare_log
  export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

  printf '\n%s[SG-Gateway]%s SG-Gateway 0.1.0-022.08 · единый мастер · 24 этапа\n' "$CYAN" "$RESET"
  printf '[SG-Gateway] Технический журнал: %s\n\n' "$INSTALL_LOG"

  run_stage 1 "Подготовка Ubuntu" bootstrap_packages
  run_stage 2 "Определение режима и параметров" stage_prepare_install_context
  run_stage 3 "Проверка установочного комплекта" stage_vendor_media_contract
  run_stage 4 "Резервная копия и исходник" stage_backup_and_prepare
  run_stage 5 "Системные пакеты, Nginx и Certbot" stage_system_packages_02208
  run_stage 6 "AmneziaWG 2 runtime" stage_awg2_runtime
  run_stage 7 "AmneziaWG 3 runtime" stage_awg3_runtime
  run_stage 8 "Xray runtime" stage_xray_runtime
  run_stage 9 "Mihomo runtime" stage_mihomo_runtime
  run_stage 10 "sing-box и WARP runtime" stage_singbox_and_warp_runtime
  run_stage 11 "NaiveProxy runtime" stage_naiveproxy_runtime
  run_stage 12 "Python-окружение и исходник" stage_python_and_source_check
  run_stage 13 "Конфигурация и база" stage_configuration_and_database_02208
  run_stage 14 "Локальная проверка страниц" stage_local_application_smoke_test
  run_stage 15 "Systemd-службы и Nginx" stage_systemd_units_02208
  run_stage 16 "Firewall и сетевые порты" stage_firewall_and_network_02208
  run_stage 17 "Запуск sg-hostd" stage9_start_hostd
  run_stage 18 "Проверка команд hostd" stage9_verify_hostd
  run_stage 19 "Независимый профиль AWG31" run_awg31_stage3a_migration
  run_stage 20 "Применение Xray и клиентов" stage9_apply_runtime
  run_stage 21 "Запуск панели" stage9_start_panel
  run_stage 22 "Проверка Nginx и служб" stage9_verify_nginx
  run_stage 23 "Проверка NaiveProxy" verify_naiveproxy_install_contract
  run_stage 24 "Финальный контракт 22.08" stage_final_contract

  INSTALL_SUCCESS=1
  sanitize_installer_log_file
  rm -f /tmp/sg-gateway-installer-output.* /tmp/sg-gateway-installer-log.* 2>/dev/null || true
  rm -f "$RESUME_FILE" \
    /root/sg-gateway-preview48-installer-resume.env \
    /root/sg-gateway-preview50-installer-resume.env \
    /root/sg-gateway-preview51-installer-resume.env \
    /root/sg-gateway-preview52-installer-resume.env \
    /root/sg-gateway-preview53-installer-resume.env \
    /root/sg-gateway-019-installer-resume.env \
    /root/sg-gateway-020-installer-resume.env
  trap - ERR INT TERM

  printf '\n%s[SG-Gateway] ============================================================%s\n' "$GREEN" "$RESET"
  if (( UPDATE_MODE == 1 )); then
    printf '%s[SG-Gateway] SG-Gateway успешно обновлён%s\n' "$GREEN" "$RESET"
  else
    printf '%s[SG-Gateway] SG-Gateway успешно установлен%s\n' "$GREEN" "$RESET"
  fi
  printf '%s[SG-Gateway] 24/24 · NaiveProxy включён в основной мастер%s\n' "$GREEN" "$RESET"
  printf '%s[SG-Gateway] ============================================================%s\n' "$GREEN" "$RESET"
  printf '[SG-Gateway] Имя сервера:  %s\n' "$SERVER_NAME"
  printf '[SG-Gateway] Страна:       %s\n' "${COUNTRY_CODE^^}"
  printf '[SG-Gateway] Публичный IP: %s\n' "$PUBLIC_ADDRESS"
  printf '[SG-Gateway] Версия:       %s\n' "$VERSION"
  printf '[SG-Gateway] Xray:         %s\n' "$(xray_installed_version)"
  printf '[SG-Gateway] NaiveProxy:   %s · TCP %s\n' "$NAIVEPROXY_VERSION" "$NAIVEPROXY_PORT"
  printf '[SG-Gateway] Логин:        admin\n'
  printf '[SG-Gateway] Журнал:       %s\n' "$INSTALL_LOG"
  printf '[SG-Gateway] Backup:       %s\n' "$BACKUP_DIR"
  print_sg_admin_status
}

main "$@"
