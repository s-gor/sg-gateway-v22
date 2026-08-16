#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="0.1.0-021.12"
INSTALLER_BUILD="02112-full-clean-backup-domain"
SOURCE_DIR="${SG_GATEWAY_SOURCE_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
PREFIX="/opt/sg-gateway"
CONFIG_DIR="/etc/sg-gateway"
DATA_DIR="/var/lib/sg-gateway"
LOG_DIR="/var/log/sg-gateway"
INSTALL_LOG="/var/log/sg-gateway-installer-02112.log"
BACKUP_ROOT="/root/sg-gateway-backups"
RESUME_FILE="/root/sg-gateway-02112-installer-resume.env"
MIHOMO_VERSION="v1.19.29"
SING_BOX_VERSION="1.13.14"
WGCF_CLI_VERSION="v0.3.6"
AMNEZIAWG_TOOLS_VERSION="1.0.20260618-2"
AMNEZIAWG_KMOD_VERSION="1.0.20260329-2"
AMNEZIAWG_DKMS_VERSION="1.0.0"
PANEL_USER="sg-gateway"
PANEL_GROUP="sg-gateway"
XRAY_REQUIRED_VERSION="v26.6.27"
XRAY_MINIMUM_VERSION="v26.6.27"

# SG-Gateway 021 vendor bundle. Clean installation does not download these
# runtimes from upstream projects. The files are committed with the source.
VENDOR_CORES_DIR="${SG_GATEWAY_VENDOR_CORES_DIR:-$SOURCE_DIR/vendor/cores}"
VENDOR_CORES_MANIFEST="$VENDOR_CORES_DIR/SHA256SUMS"
XRAY_VENDOR_FILE="Xray-linux-64.zip"
MIHOMO_VENDOR_FILE="mihomo-linux-amd64-v1.19.29.gz"
SINGBOX_VENDOR_FILE="sing-box-1.13.14-linux-amd64.tar.gz"
WGCF_VENDOR_FILE="wgcf-cli-linux-64.tar.zstd"
AWG_TOOLS_VENDOR_FILE="amneziawg-tools-1.0.20260618-2.tar.gz"
AWG_KMOD_VENDOR_FILE="amneziawg-linux-kernel-module-1.0.20260329-2.tar.gz"

DEFAULT_PANEL_PORT="63443"
DEFAULT_XRAY_PORT="443"
DEFAULT_AWG_PORT="585"
DEFAULT_REALITY_TARGET="www.bing.com:443"
DEFAULT_REALITY_SNI="www.bing.com"
MIHOMO_PORT="2099"
XHTTP_REALITY_PORT="8444"
XHTTP_TLS_PORT="8445"
HYSTERIA2_PORT="8446"
ANYTLS_PORT="9443"
TUIC_PORT="10443"
HOSTD_PORT="8090"
BACKEND_PORT="18080"
REALITY_INTERNAL_PORT="7443"
PLACEHOLDER_TLS_INTERNAL_PORT="7444"

GREEN=$'\033[1;32m'
RED=$'\033[1;31m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[1;36m'
RESET=$'\033[0m'

TOTAL_STAGES=10
CURRENT_STAGE="0"
CURRENT_LABEL="Подготовка"
PANEL_PORT=""
XRAY_PORT=""
AWG_PORT=""
REALITY_TARGET=""
REALITY_SNI=""
ADMIN_PASSWORD=""
ADMIN_PASSWORD_HASH=""
PUBLIC_ADDRESS=""
SERVER_NAME=""
COUNTRY_CODE="unknown"
CREATE_SG_ADMIN="1"
SECRET_KEY=""
BACKUP_DIR=""
MUTATION_STARTED=0
INSTALL_SUCCESS=0
UPDATE_MODE=0
EXISTING_VERSION=""
SERVER_NAME_MIGRATION_REQUIRED=0
MIGRATE_MINIMAL_013=0
MIGRATION_XRAY_PRIVATE=""
MIGRATION_XRAY_PUBLIC=""
MIGRATION_XRAY_SHORT_ID=""
MIGRATION_VLESS_ENCRYPTION=""
MIGRATION_VLESS_DECRYPTION=""
MIGRATION_013_CLIENTS_JSON=""

MANAGED_PATHS=(
  etc/hostname
  etc/hosts
  opt/sg-gateway
  etc/sg-gateway
  var/lib/sg-gateway
  etc/systemd/system/sg-gateway.service
  etc/systemd/system/sg-gateway.service.d
  etc/systemd/system/sg-hostd.service
  etc/systemd/system/sg-hostd.service.d
  etc/systemd/system/sg-gateway-awg.service
  etc/systemd/system/sg-gateway-singbox.service
  etc/systemd/system/mihomo.service
  etc/nginx/nginx.conf
  etc/nginx/stream-conf.d/sg-gateway-443.conf
  etc/nginx/sites-available/sg-gateway-acme
  etc/nginx/sites-enabled/sg-gateway-acme
  var/www/sg-gateway-placeholder
  var/www/sg-gateway-acme
  etc/nginx/sites-available/sg-gateway
  etc/nginx/sites-enabled/sg-gateway
  etc/nginx/sites-enabled/default
  etc/letsencrypt/renewal-hooks/deploy/sg-gateway-nginx
  etc/letsencrypt/renewal-hooks/deploy/reload-sg-gateway-nginx.sh
  etc/mihomo
  var/lib/mihomo
  etc/sing-box
  var/lib/sing-box
  usr/local/bin/xray
  usr/local/bin/mihomo
  usr/local/bin/sing-box
  usr/local/bin/wgcf-cli
  usr/bin/sing-box
  usr/bin/awg
  usr/bin/awg-quick
  usr/src/amneziawg-1.0.0
  usr/local/share/xray
  usr/local/etc/xray
  etc/systemd/system/xray.service
  etc/systemd/system/xray.service.d
  etc/systemd/system/xray@.service
  etc/systemd/system/xray@.service.d
  etc/amnezia/amneziawg
  etc/sysctl.d/99-sg-gateway.conf
)

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Запустите установщик через sudo." >&2
    exit 1
  fi
}

prepare_log() {
  install -d -m 0755 "$(dirname "$INSTALL_LOG")"
  : > "$INSTALL_LOG"
  chmod 0600 "$INSTALL_LOG"
}


sanitize_installer_stream() {
  # Keep the permanent installer log useful without retaining exported
  # profiles, subscriptions, PEM material or generated private credentials.
  # The raw command output exists only in a 0600 temporary file and is removed
  # immediately after this filter has processed it.
  if ! command -v python3 >/dev/null 2>&1; then
    cat
    return 0
  fi
  python3 -c '
import re
import sys

text = sys.stdin.read()

# Complete PEM blocks: certificates, keys, CSRs and similar material.
text = re.sub(
    r"-----BEGIN ([A-Z0-9][A-Z0-9 -]*)-----.*?-----END \1-----",
    "[REDACTED PEM BLOCK]",
    text,
    flags=re.DOTALL,
)

# Connection links are never useful in an installer log.
text = re.sub(
    r"(?i)\b(vless|hysteria2|hy2|mieru|trojan|ss|ssr)://[^\s<>\"\x27]+",
    lambda match: f"{match.group(1)}://[REDACTED]",
    text,
)
text = re.sub(
    r"(?im)(subscription-base64\s*:\s*)\S+",
    r"\1[REDACTED]",
    text,
)

# Shell/env and JSON secret fields.
text = re.sub(
    r"(?im)^(\s*(?:SG_[A-Z0-9_]*(?:PASSWORD|PRIVATE_KEY|SECRET|TOKEN|DECRYPTION|ENCRYPTION)|PASSWORD|PRIVATE_KEY|SECRET_KEY|TOKEN)\s*=).*$",
    r"\1[REDACTED]",
    text,
)
text = re.sub(
    r"(?i)([\"](?:password|private[_-]?key|secret[_-]?key|token|decryption|encryption)[\"]\s*:\s*[\"])[^\"]*([\"])",
    r"\1[REDACTED]\2",
    text,
)

# Last-resort protection for standalone very long Base64/Base64URL blobs.
cleaned = []
for line in text.splitlines(keepends=True):
    body = line.rstrip("\r\n")
    token = body.strip()
    if len(token) >= 320 and re.fullmatch(r"[A-Za-z0-9_+/=.-]+", token):
        ending = line[len(body):]
        cleaned.append("[REDACTED LONG CREDENTIAL]" + ending)
    else:
        cleaned.append(line)
sys.stdout.write("".join(cleaned))
'
}


sanitize_installer_log_file() {
  [[ -f "$INSTALL_LOG" ]] || return 0
  local sanitized=""
  sanitized="$(mktemp /tmp/sg-gateway-installer-log.XXXXXX)"
  chmod 0600 "$sanitized"
  sanitize_installer_stream < "$INSTALL_LOG" > "$sanitized"
  cat "$sanitized" > "$INSTALL_LOG"
  chmod 0600 "$INSTALL_LOG"
  rm -f "$sanitized"
}

show_log_tail() {
  echo
  printf "%s[SG-Gateway] Причина:%s\n" "$YELLOW" "$RESET"
  local summary=""
  summary="$(python3 - "$INSTALL_LOG" <<'PYERROR'
from pathlib import Path
import sys
path = Path(sys.argv[1])
try:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
except OSError:
    lines = []
failed = -1
traceback = -1
for index, line in enumerate(lines):
    if line.startswith("Traceback (most recent call last):"):
        traceback = index
    if line.startswith("FAILED COMMAND"):
        failed = index

if failed >= 0:
    # Diagnostics are appended after FAILED COMMAND. Show the actual command
    # failure and the lines immediately before it, not a service-journal tail.
    start = traceback if 0 <= traceback < failed else max(0, failed - 24)
    selected = lines[start : failed + 1]
elif traceback >= 0:
    selected = lines[traceback : traceback + 24]
else:
    selected = lines[-18:]
print("\n".join(selected))
PYERROR
)"
  if [[ -n "$summary" ]]; then
    while IFS= read -r line; do
      printf '[SG-Gateway] %s\n' "$line"
    done <<< "$summary"
  else
    printf '[SG-Gateway] Точная причина отсутствует в журнале.\n'
  fi
  printf '[SG-Gateway] Полный технический журнал: %s\n' "$INSTALL_LOG"
}

show_service_diagnostics() {
  {
    local service
    echo "===== SERVICE DIAGNOSTICS ====="
    for service in sg-gateway.service sg-hostd.service xray.service mihomo.service \
      sg-gateway-awg.service sg-gateway-singbox.service nginx.service; do
      if systemctl cat "$service" >/dev/null 2>&1; then
        echo "===== ${service} ====="
        systemctl is-active "$service" 2>/dev/null || true
        journalctl -b -u "$service" -n 25 --no-pager -o short-iso || true
      fi
    done
  } 2>&1 | sanitize_installer_stream >> "$INSTALL_LOG"
}

rollback_remove_managed_paths() {
  # SG_GATEWAY_02110_INSTALLER_SAFETY_FIX2
  # nginx.conf belongs to the Ubuntu Nginx package. Never blindly delete it
  # during rollback. If it existed before the install, managed-paths.tar will
  # overwrite it with the saved copy. If Nginx was installed by this attempt,
  # nginx-after-packages.tar will overwrite it with the healthy package
  # baseline. If apt itself fails before that snapshot exists, preserving the
  # package-created nginx.conf is still strictly safer than deleting it.
  local root="${1:-/}" relative target
  root="${root%/}"
  for relative in "${MANAGED_PATHS[@]}"; do
    [[ "$relative" == "etc/nginx/nginx.conf" ]] && continue
    target="${root}/${relative}"
    rm -rf "$target"
  done
}

restore_backup() {
  [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || return 0
  printf "\n%s[SG-Gateway] [ОТКАТ]%s Восстанавливаю предыдущую установку SG-Gateway.\n" "$YELLOW" "$RESET"

  systemctl stop sg-gateway.service sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-singbox.service nginx.service >/dev/null 2>&1 || true
  rollback_remove_managed_paths /

  if [[ -f "$BACKUP_DIR/managed-paths.tar" ]]; then
    tar -C / -xpf "$BACKUP_DIR/managed-paths.tar"
  fi

  # SG_GATEWAY_02110_INSTALLER_SAFETY_FIX1
  # If apt installed/repaired Nginx during this attempt, restore the exact
  # package/user Nginx tree captured before SG-Gateway touched it.  This avoids
  # the old failure mode where rollback removed nginx.conf but left the package.
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

  # Restore enablement first.  Missing/optional units are ignored only when
  # they were not present or active before the update.
  for service in sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-singbox.service sg-gateway.service nginx.service; do
    if [[ "${was_enabled[$service]:-0}" == "1" ]]; then
      systemctl enable "$service" >/dev/null 2>&1 || true
    elif [[ -n "${was_enabled[$service]+x}" ]]; then
      systemctl disable "$service" >/dev/null 2>&1 || true
    fi
  done

  # Restore the exact active set in dependency-safe order.
  for service in sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-singbox.service sg-gateway.service nginx.service; do
    if [[ "${was_active[$service]:-0}" == "1" ]]; then
      if ! systemctl restart "$service" >>"$INSTALL_LOG" 2>&1; then
        echo "ROLLBACK SERVICE FAILED: $service" >>"$INSTALL_LOG"
        failures=$((failures + 1))
      fi
    elif [[ -n "${was_active[$service]+x}" ]]; then
      systemctl stop "$service" >/dev/null 2>&1 || true
    fi
  done

  # Backups made by older installers do not have service-state.tsv.
  if [[ ! -f "$state_file" ]]; then
    for service in sg-hostd.service sg-gateway.service nginx.service; do
      [[ -f "/etc/systemd/system/$service" || "$service" == "nginx.service" ]] || continue
      systemctl enable --now "$service" >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    done
    if [[ -f /usr/local/etc/xray/config.json ]]; then
      systemctl enable --now xray.service >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    fi
    if [[ -f /etc/mihomo/config.yaml ]]; then
      systemctl enable --now mihomo.service >>"$INSTALL_LOG" 2>&1 || failures=$((failures + 1))
    fi
  fi

  # Do not print a false green result: every service that was active before
  # the update must be active again after rollback.
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
    printf "%s[SG-Gateway] [ОТКАТ НЕПОЛНЫЙ]%s Файлы восстановлены, но не все прежние службы запустились.\n" "$RED" "$RESET"
    printf "[SG-Gateway] Резервная копия: %s\n" "$BACKUP_DIR"
    return 1
  fi
  printf "%s[SG-Gateway] [ОТКАТ OK]%s Предыдущая установка и активные службы восстановлены.\n" "$GREEN" "$RESET"
  printf "[SG-Gateway] Резервная копия: %s\n" "$BACKUP_DIR"
}

unexpected_error() {
  local rc=$?
  trap - ERR INT TERM
  rm -f /tmp/sg-gateway-installer-output.* /tmp/sg-gateway-installer-log.* 2>/dev/null || true
  if (( MUTATION_STARTED == 1 && INSTALL_SUCCESS == 0 )); then
    show_service_diagnostics
    restore_backup || true
  fi
  sanitize_installer_log_file || true
  printf "\n%s[SG-Gateway] [ОШИБКА]%s Установка остановлена.\n" "$RED" "$RESET"
  printf "[SG-Gateway] %s\n" "$CURRENT_LABEL"
  printf "[SG-Gateway] Этот же EC2 можно использовать повторно; пересоздавать сервер не нужно.\n"
  show_log_tail
  exit "$rc"
}
trap unexpected_error ERR
trap 'rm -f /tmp/sg-gateway-installer-output.* /tmp/sg-gateway-installer-log.* 2>/dev/null || true; exit 130' INT TERM

run_quiet() {
  local label="$1"
  shift
  CURRENT_LABEL="$label"
  local started=$SECONDS rc=0 pid frame=0 raw_output=""
  local frames=('|' '/' '-' "\\")
  raw_output="$(mktemp /tmp/sg-gateway-installer-output.XXXXXX)"
  chmod 0600 "$raw_output"
  printf "\r\033[K%s[SG-Gateway] [-]%s %s" "$GREEN" "$RESET" "$label"
  (
    trap - ERR INT TERM
    "$@"
  ) >"$raw_output" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    frame=$(( (frame + 1) % 4 ))
    printf "\r\033[K%s[SG-Gateway] [%s]%s %s" "$GREEN" "${frames[$frame]}" "$RESET" "$label"
    sleep 0.18
  done
  if wait "$pid"; then rc=0; else rc=$?; fi
  sanitize_installer_stream < "$raw_output" >> "$INSTALL_LOG"
  rm -f "$raw_output"
  local elapsed=$((SECONDS - started))
  if (( rc != 0 )); then
    printf "\r\033[K%s[SG-Gateway] [ОШИБКА]%s %s (%s сек.)\n" "$RED" "$RESET" "$label" "$elapsed"
    printf "FAILED COMMAND (rc=%s): %s\n" "$rc" "$label" >> "$INSTALL_LOG"
    return "$rc"
  fi
  printf "\r\033[K%s[SG-Gateway] [OK]%s %s (%s сек.)\n" "$GREEN" "$RESET" "$label" "$elapsed"
}

run_live() {
  local label="$1"
  shift
  CURRENT_LABEL="$label"
  local started=$SECONDS rc=0 raw_output=""
  raw_output="$(mktemp /tmp/sg-gateway-installer-output.XXXXXX)"
  chmod 0600 "$raw_output"
  printf "%s[SG-Gateway] [..]%s %s\n" "$GREEN" "$RESET" "$label"
  set +e
  (
    trap - ERR INT TERM
    "$@"
  ) > >(tee "$raw_output") 2>&1
  rc=$?
  set -e
  sanitize_installer_stream < "$raw_output" >> "$INSTALL_LOG"
  rm -f "$raw_output"
  local elapsed=$((SECONDS - started))
  if (( rc != 0 )); then
    printf "%s[SG-Gateway] [ОШИБКА]%s %s (%s сек.)\n" "$RED" "$RESET" "$label" "$elapsed"
    printf "FAILED COMMAND (rc=%s): %s\n" "$rc" "$label" >> "$INSTALL_LOG"
    return "$rc"
  fi
  printf "%s[SG-Gateway] [OK]%s %s (%s сек.)\n" "$GREEN" "$RESET" "$label" "$elapsed"
}
run_hidden() { run_quiet "$@"; }

run_stage() {
  local number="$1"
  local label="$2"
  local function_name="$3"
  CURRENT_STAGE="$number"
  CURRENT_LABEL="Этап ${number}/${TOTAL_STAGES} · ${label}"
  if [[ "$number" == "1" ]]; then
    run_live "$CURRENT_LABEL" "$function_name"
  else
    run_quiet "$CURRENT_LABEL" "$function_name"
  fi
}

wait_for_apt() {
  local waited=0
  local max_wait="${SG_GATEWAY_APT_WAIT_SECONDS:-1800}"
  while ! python3 - <<'PYLOCK'
import fcntl
import os
paths = (
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/dpkg/lock",
    "/var/cache/apt/archives/lock",
    "/var/lib/apt/lists/lock",
)
opened = []
try:
    for path in paths:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o640)
        opened.append(fd)
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
finally:
    for fd in reversed(opened):
        try:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
PYLOCK
  do
    if (( waited == 0 )); then
      echo "APT/dpkg занят автоматическим обновлением Ubuntu; ожидаю."
    fi
    sleep 3
    waited=$((waited + 3))
    if (( waited > 0 && waited % 30 == 0 )); then
      echo "APT/dpkg всё ещё занят; ожидание: ${waited} сек."
    fi
    if (( waited >= max_wait )); then
      echo "APT/dpkg не освободился за ${max_wait} секунд." >&2
      return 1
    fi
  done
}

apt_get() {
  local attempt=1
  local max_attempts=4
  local rc=0
  while (( attempt <= max_attempts )); do
    wait_for_apt
    if apt-get -o Dpkg::Use-Pty=0 -o DPkg::Lock::Timeout="${SG_GATEWAY_APT_WAIT_SECONDS:-1800}" "$@"; then
      return 0
    else
      rc=$?
    fi
    (( attempt == max_attempts )) && return "$rc"
    echo "apt-get завершился ошибкой; повтор через 8 секунд."
    sleep 8
    attempt=$((attempt + 1))
  done
}

bootstrap_packages() {
  export DEBIAN_FRONTEND=noninteractive
  echo "[Ubuntu 1/2] Обновляю список пакетов"
  apt_get update
  echo "[Ubuntu 2/2] Устанавливаю базовые инструменты"
  apt_get install -y ca-certificates curl tar gzip unzip zstd jq openssl python3 python3-venv python3-pip
}

read_tty() {
  local prompt="$1"
  local target="$2"
  local default_value="${3:-}"
  local value=""
  if [[ -n "$default_value" ]]; then
    read -r -p "[SG-Gateway] ${prompt} [${default_value}]: " value < /dev/tty
    value="${value:-$default_value}"
  else
    read -r -p "[SG-Gateway] ${prompt}: " value < /dev/tty
  fi
  printf -v "$target" '%s' "$value"
}

read_password() {
  local first="" second=""
  while true; do
    read -r -s -p "[SG-Gateway] Пароль администратора (не менее 8 символов): " first < /dev/tty
    printf "\n" > /dev/tty
    read -r -s -p "[SG-Gateway] Повторите пароль: " second < /dev/tty
    printf "\n" > /dev/tty
    if (( ${#first} < 8 )); then
      printf "%sПароль слишком короткий.%s\n" "$YELLOW" "$RESET" > /dev/tty
      continue
    fi
    if [[ "$first" != "$second" ]]; then
      printf "%sПароли не совпадают.%s\n" "$YELLOW" "$RESET" > /dev/tty
      continue
    fi
    ADMIN_PASSWORD="$first"
    ADMIN_PASSWORD_HASH="$(python3 - "$first" <<'PYADMINHASH'
import base64, hashlib, os, sys
password=sys.argv[1]
salt=os.urandom(16)
rounds=310000
digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,rounds)
print(f"pbkdf2_sha256${rounds}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}")
PYADMINHASH
)"
    return 0
  done
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 ))
}


valid_hostname() {
  python3 - "$1" <<'PYHOST'
import re, sys
value=sys.argv[1]
raise SystemExit(0 if len(value) <= 63 and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", value) else 1)
PYHOST
}

normalize_hostname() {
  printf '%s' "$1" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g' | cut -c1-63
}

valid_public_ipv4() {
  python3 - "$1" <<'PYIP'
import ipaddress, sys
try:
    ip = ipaddress.ip_address(sys.argv[1].strip())
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if ip.version == 4 and ip.is_global else 1)
PYIP
}

detect_public_ip() {
  local value="" endpoint token=""
  for endpoint in \
    "https://api.ipify.org" \
    "https://ifconfig.me/ip" \
    "https://icanhazip.com" \
    "https://checkip.amazonaws.com"; do
    value="$(curl -4 -fsS --max-time 8 "$endpoint" 2>/dev/null | tr -d '[:space:]' || true)"
    if valid_public_ipv4 "$value"; then
      printf '%s' "$value"
      return 0
    fi
  done
  token="$(curl -fsS --max-time 3 -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
    http://169.254.169.254/latest/api/token 2>/dev/null || true)"
  if [[ -n "$token" ]]; then
    value="$(curl -fsS --max-time 3 -H "X-aws-ec2-metadata-token: $token" \
      http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null | tr -d '[:space:]' || true)"
    if valid_public_ipv4 "$value"; then
      printf '%s' "$value"
      return 0
    fi
  fi
  return 1
}

detect_country_code() {
  local ip="$1" value=""
  value="$(curl -fsS --max-time 8 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null | sed -n 's/^loc=//p' | tail -n 1 | tr '[:lower:]' '[:upper:]' || true)"
  [[ "$value" =~ ^[A-Z]{2}$ ]] || value="$(curl -fsS --max-time 8 "https://ipapi.co/${ip}/country/" 2>/dev/null | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]' || true)"
  [[ "$value" =~ ^[A-Z]{2}$ ]] || value="$(curl -fsS --max-time 8 "https://country.is/${ip}" 2>/dev/null | sed -nE 's/.*"country"[[:space:]]*:[[:space:]]*"([A-Za-z]{2})".*/\1/p' | tr '[:lower:]' '[:upper:]' || true)"
  [[ "$value" =~ ^[A-Z]{2}$ ]] || value="UNKNOWN"
  printf '%s' "$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
}

read_yes_no() {
  local prompt="$1" target="$2" default_value="${3:-1}" answer=""
  local suffix="[Enter = Да / n = Нет]"
  [[ "$default_value" == "0" ]] && suffix="[y = Да / Enter = Нет]"
  while true; do
    read -r -p "[SG-Gateway] $prompt $suffix: " answer < /dev/tty
    answer="${answer:-$([[ "$default_value" == "1" ]] && echo y || echo n)}"
    case "${answer,,}" in
      y|yes|д|да) printf -v "$target" '%s' 1; return 0 ;;
      n|no|н|нет) printf -v "$target" '%s' 0; return 0 ;;
    esac
  done
}

apply_server_hostname() {
  local clean
  clean="$(normalize_hostname "$SERVER_NAME")"
  [[ -n "$clean" ]] || { echo "Некорректное имя сервера" >&2; return 1; }
  SERVER_NAME="$clean"
  hostnamectl set-hostname "$SERVER_NAME"
  if grep -qE '^127\\.0\\.1\\.1[[:space:]]' /etc/hosts; then
    sed -i -E "s/^127\\.0\\.1\\.1[[:space:]].*/127.0.1.1 ${SERVER_NAME}/" /etc/hosts
  else
    printf '127.0.1.1 %s\\n' "$SERVER_NAME" >> /etc/hosts
  fi
}

fingerprint_clients() {
  local database="$1" output="$2"
  if [[ ! -f "$database" ]]; then
    printf 'NO_DATABASE\n' > "$output"
    return 0
  fi
  python3 - "$database" > "$output" <<'PYCLIENTFP'
import hashlib, json, sqlite3, sys
path=sys.argv[1]
conn=sqlite3.connect(path)
conn.row_factory=sqlite3.Row
payload={}
for table in ("clients","devices","device_credentials"):
    try:
        rows=conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
    except sqlite3.Error:
        rows=[]
    cleaned=[]
    for row in rows:
        item=dict(row)
        if table == "device_credentials" and item.get("config_json"):
            try:
                cfg=json.loads(item["config_json"])
            except Exception:
                cfg={}
            def secrets(value):
                if isinstance(value,dict):
                    return {k:secrets(v) for k,v in sorted(value.items()) if k.lower() in {
                        "uuid","id","private_key","public_key","password","username","address","auth","token","short_id"
                    }}
                if isinstance(value,list): return [secrets(v) for v in value]
                return value
            item["config_json"]=secrets(cfg)
        cleaned.append(item)
    payload[table]=cleaned
raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
print(hashlib.sha256(raw).hexdigest())
PYCLIENTFP
}

env_value() {
  local file="$1" key="$2"
  python3 - "$file" "$key" <<'PYENV'
import shlex
import sys
from pathlib import Path
path = Path(sys.argv[1])
key = sys.argv[2]
try:
    lines = path.read_text(encoding="utf-8").splitlines()
except OSError:
    raise SystemExit(1)
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() != key:
        continue
    value = value.strip()
    if value[:1] in {"\"", "'"}:
        try:
            parsed = shlex.split(value, posix=True)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = value[1:-1] if len(value) >= 2 else ""
    print(value)
    raise SystemExit(0)
raise SystemExit(1)
PYENV
}

save_resume_state() {
  # Keep the installer-wide umask unchanged. A persistent `umask 077` here
  # made the later virtualenv root-only: stage 5 succeeded as root, then
  # stage 6 failed when the sg-gateway service user executed its Python.
  (
    umask 077
    cat > "$RESUME_FILE" <<EOF
PANEL_PORT=$(printf '%q' "$PANEL_PORT")
XRAY_PORT=$(printf '%q' "$XRAY_PORT")
AWG_PORT=$(printf '%q' "$AWG_PORT")
REALITY_TARGET=$(printf '%q' "$REALITY_TARGET")
REALITY_SNI=$(printf '%q' "$REALITY_SNI")
ADMIN_PASSWORD=$(printf '%q' "$ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH=$(printf '%q' "$ADMIN_PASSWORD_HASH")
PUBLIC_ADDRESS=$(printf '%q' "$PUBLIC_ADDRESS")
SERVER_NAME=$(printf '%q' "$SERVER_NAME")
COUNTRY_CODE=$(printf '%q' "$COUNTRY_CODE")
CREATE_SG_ADMIN=$(printf '%q' "$CREATE_SG_ADMIN")
SECRET_KEY=$(printf '%q' "$SECRET_KEY")
EOF
    chmod 0600 "$RESUME_FILE"
  )
}

load_resume_state() {
  [[ -f "$RESUME_FILE" ]] || return 1
  # shellcheck disable=SC1090
  source "$RESUME_FILE"
  valid_port "${PANEL_PORT:-}" || return 1
  valid_port "${XRAY_PORT:-}" || return 1
  valid_port "${AWG_PORT:-}" || return 1
  [[ -n "${REALITY_TARGET:-}" && -n "${REALITY_SNI:-}" ]] || return 1
  [[ -n "${ADMIN_PASSWORD:-}" || -n "${ADMIN_PASSWORD_HASH:-}" ]] || return 1
  [[ -n "${PUBLIC_ADDRESS:-}" && -n "${SECRET_KEY:-}" ]] || return 1
  valid_public_ipv4 "$PUBLIC_ADDRESS" || fail "SG-Gateway 013: не удалось определить публичный IPv4"
  valid_hostname "${SERVER_NAME:-}" || return 1
  [[ "${COUNTRY_CODE:-unknown}" =~ ^([a-z]{2}|unknown)$ ]] || return 1
  [[ "${CREATE_SG_ADMIN:-1}" =~ ^[01]$ ]] || return 1
  echo "[SG-Gateway] Найдены параметры предыдущей незавершённой установки. Повторно вопросы не задаю."
  return 0
}

detect_existing_install() {
  local runtime_file="$CONFIG_DIR/runtime.env"
  local app_file="$CONFIG_DIR/sg-gateway.env"
  if [[ ! -f "$PREFIX/VERSION" || ! -f "$runtime_file" || ! -f "$app_file" ]]; then
    return 1
  fi

  EXISTING_VERSION="$(cat "$PREFIX/VERSION" 2>/dev/null || true)"
  PANEL_PORT="$(env_value "$runtime_file" SG_GATEWAY_PANEL_PORT)"
  XRAY_PORT="$(env_value "$runtime_file" SG_GATEWAY_XRAY_PORT)"
  AWG_PORT="$(env_value "$runtime_file" SG_GATEWAY_AWG_PORT)"
  REALITY_TARGET="$(env_value "$runtime_file" SG_GATEWAY_REALITY_TARGET)"
  REALITY_SNI="$(env_value "$runtime_file" SG_GATEWAY_REALITY_SNI)"
  PUBLIC_ADDRESS="$(env_value "$runtime_file" SG_GATEWAY_PUBLIC_ADDRESS || true)"
  local stored_server_name=""
  stored_server_name="$(env_value "$runtime_file" SG_GATEWAY_SERVER_NAME || true)"
  COUNTRY_CODE="$(env_value "$runtime_file" SG_GATEWAY_COUNTRY_CODE || true)"
  CREATE_SG_ADMIN="0"
  if [[ -f "$DATA_DIR/sg-gateway.sqlite" ]]; then
    local existing_clients="0"
    existing_clients="$(sqlite3 "$DATA_DIR/sg-gateway.sqlite" "SELECT COUNT(*) FROM clients;" 2>/dev/null || echo 0)"
    [[ "$existing_clients" =~ ^[0-9]+$ ]] || existing_clients="0"
    (( existing_clients == 0 )) && CREATE_SG_ADMIN="1"
  else
    CREATE_SG_ADMIN="1"
  fi
  SECRET_KEY="$(env_value "$app_file" SG_GATEWAY_SECRET_KEY)"
  ADMIN_PASSWORD="$(env_value "$app_file" SG_GATEWAY_ADMIN_PASSWORD || true)"
  ADMIN_PASSWORD_HASH="$(env_value "$app_file" SG_GATEWAY_ADMIN_PASSWORD_HASH || true)"

  valid_port "$PANEL_PORT" || return 1
  valid_port "$XRAY_PORT" || return 1
  valid_port "$AWG_PORT" || return 1
  [[ -n "$REALITY_TARGET" && -n "$REALITY_SNI" ]] || return 1
  if ! valid_public_ipv4 "$PUBLIC_ADDRESS"; then
    PUBLIC_ADDRESS="$(detect_public_ip || true)"
  fi
  valid_public_ipv4 "$PUBLIC_ADDRESS" || return 1
  if [[ ! "$COUNTRY_CODE" =~ ^[a-z]{2}$ || "$COUNTRY_CODE" == "unknown" ]]; then
    COUNTRY_CODE="$(detect_country_code "$PUBLIC_ADDRESS")"
  fi
  [[ "$COUNTRY_CODE" =~ ^([a-z]{2}|unknown)$ ]] || COUNTRY_CODE="unknown"
  SERVER_NAME="$(normalize_hostname "$stored_server_name")"
  case "$SERVER_NAME" in
    ""|ubuntu|ip-[0-9]*|localhost)
      SERVER_NAME="sg-gateway"
      [[ "$COUNTRY_CODE" != "unknown" ]] && SERVER_NAME="sg-gateway-${COUNTRY_CODE}"
      SERVER_NAME_MIGRATION_REQUIRED=1
      ;;
  esac
  valid_hostname "$SERVER_NAME" || return 1
  [[ -n "$SECRET_KEY" ]] || return 1
  [[ -n "$ADMIN_PASSWORD" || -n "$ADMIN_PASSWORD_HASH" ]] || return 1
  UPDATE_MODE=1
  return 0
}


detect_minimal_013_install() {
  local public_file="$CONFIG_DIR/public.env"
  local xray_file="$CONFIG_DIR/xray.env"
  local panel_file="$CONFIG_DIR/panel.env"
  [[ -f "$public_file" && -f "$xray_file" && -f "$panel_file" ]] || return 1
  [[ -f "$PREFIX/VERSION" ]] || return 1

  local installed
  installed="$(cat "$PREFIX/VERSION" 2>/dev/null || true)"
  [[ "$installed" == *"013"* || -f "$CONFIG_DIR/lineage" ]] || return 1

  EXISTING_VERSION="${installed:-SG-Gateway 013}"
  PANEL_PORT="$DEFAULT_PANEL_PORT"
  XRAY_PORT="$(env_value "$public_file" SG_TCP_PORT || true)"
  AWG_PORT="$DEFAULT_AWG_PORT"
  REALITY_TARGET="$(env_value "$xray_file" SG_REALITY_TARGET || true)"
  REALITY_SNI="$(env_value "$public_file" SG_REALITY_SNI || true)"
  PUBLIC_ADDRESS="$(env_value "$public_file" SG_PUBLIC_HOST || true)"
  SERVER_NAME="$(normalize_hostname "$(env_value "$public_file" SG_SERVER_NAME || true)")"
  COUNTRY_CODE="$(env_value "$public_file" SG_COUNTRY_CODE || true)"
  COUNTRY_CODE="${COUNTRY_CODE,,}"
  CREATE_SG_ADMIN="0"
  ADMIN_PASSWORD=""
  ADMIN_PASSWORD_HASH="$(env_value "$panel_file" SG_PANEL_PASSWORD_HASH || true)"
  SECRET_KEY="$(env_value "$panel_file" SG_PANEL_SESSION_SECRET || true)"
  [[ -n "$ADMIN_PASSWORD_HASH" && -n "$SECRET_KEY" ]] || fail "SG-Gateway 013: не удалось сохранить пароль/сессионный ключ панели"

  MIGRATION_XRAY_PRIVATE="$(env_value "$xray_file" SG_REALITY_PRIVATE_KEY || true)"
  MIGRATION_XRAY_PUBLIC="$(env_value "$public_file" SG_REALITY_PUBLIC_KEY || true)"
  MIGRATION_XRAY_SHORT_ID="$(env_value "$public_file" SG_REALITY_SHORT_ID || true)"
  MIGRATION_VLESS_ENCRYPTION="$(env_value "$xray_file" SG_VLESS_ENCRYPTION || true)"
  MIGRATION_VLESS_DECRYPTION="$(env_value "$xray_file" SG_VLESS_DECRYPTION || true)"

  XRAY_PORT="$DEFAULT_XRAY_PORT"
  [[ -n "$REALITY_TARGET" ]] || REALITY_TARGET="$DEFAULT_REALITY_TARGET"
  [[ -n "$REALITY_SNI" ]] || REALITY_SNI="$DEFAULT_REALITY_SNI"
  if ! valid_public_ipv4 "$PUBLIC_ADDRESS"; then
    PUBLIC_ADDRESS="$(detect_public_ip || true)"
  fi
  valid_public_ipv4 "$PUBLIC_ADDRESS" || return 1
  if ! valid_hostname "$SERVER_NAME"; then
    SERVER_NAME="sg-gateway"
    [[ "$COUNTRY_CODE" =~ ^[a-z]{2}$ ]] && SERVER_NAME="sg-gateway-${COUNTRY_CODE}"
  fi
  if [[ ! "$COUNTRY_CODE" =~ ^[a-z]{2}$ || "$COUNTRY_CODE" == "un" ]]; then
    COUNTRY_CODE="$(detect_country_code "$PUBLIC_ADDRESS")"
  fi
  [[ "$COUNTRY_CODE" =~ ^([a-z]{2}|unknown)$ ]] || COUNTRY_CODE="unknown"

  [[ -n "$MIGRATION_XRAY_PRIVATE" && -n "$MIGRATION_XRAY_PUBLIC" && -n "$MIGRATION_XRAY_SHORT_ID" ]] || fail "SG-Gateway 013: не найдены подтверждённые Reality keys/ShortID"
  [[ -n "$MIGRATION_VLESS_ENCRYPTION" && -n "$MIGRATION_VLESS_DECRYPTION" ]] || fail "SG-Gateway 013: не найдена подтверждённая ML-KEM-768 пара"
  if ! PYTHONPATH="$SOURCE_DIR" python3 - "$MIGRATION_VLESS_ENCRYPTION" "$MIGRATION_VLESS_DECRYPTION" <<'PY013PAIR'
import sys
from app.xray.encryption import normalize_pair
client, server, _ = normalize_pair(sys.argv[1], sys.argv[2])
assert client == sys.argv[1]
assert server == sys.argv[2]
PY013PAIR
  then
    fail "SG-Gateway 013: сохранённая ML-KEM-768 пара не прошла строгую проверку ролей"
  fi

  UPDATE_MODE=1
  MIGRATE_MINIMAL_013=1
  return 0
}

prepare_minimal_013_database() {
  (( MIGRATE_MINIMAL_013 == 1 )) || return 0
  local database="$DATA_DIR/sg-gateway.sqlite"
  MIGRATION_013_CLIENTS_JSON="$DATA_DIR/sg-gateway-013-clients.json"
  [[ -f "$database" ]] || { printf '[]\n' > "$MIGRATION_013_CLIENTS_JSON"; return 0; }
  python3 - "$database" "$MIGRATION_013_CLIENTS_JSON" <<'PY013DB'
import json, os, sqlite3, sys
from pathlib import Path

db=Path(sys.argv[1]); out=Path(sys.argv[2])
con=sqlite3.connect(db)
con.row_factory=sqlite3.Row
try:
    tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columns={r[1] for r in con.execute("PRAGMA table_info(clients)")} if 'clients' in tables else set()
    minimal='uuid' in columns and 'devices' not in tables
    if not minimal:
        out.write_text('[]\n',encoding='utf-8')
        raise SystemExit(0)
    rows=[]
    for row in con.execute("SELECT name, uuid, enabled, created_at FROM clients ORDER BY id"):
        rows.append(dict(row))
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
finally:
    con.close()
archive=db.with_name('sg-gateway-013-minimal.sqlite')
if archive.exists():
    archive.unlink()
os.replace(db,archive)
for suffix in ('-wal','-shm'):
    Path(str(db)+suffix).unlink(missing_ok=True)
print(f"Minimal 013 database archived: {archive}; clients={len(rows)}")
PY013DB
  chown "$PANEL_USER":"$PANEL_GROUP" "$MIGRATION_013_CLIENTS_JSON" 2>/dev/null || true
  chmod 0600 "$MIGRATION_013_CLIENTS_JSON" 2>/dev/null || true
}

restore_minimal_013_clients() {
  (( MIGRATE_MINIMAL_013 == 1 )) || return 0
  [[ -f "$MIGRATION_013_CLIENTS_JSON" ]] || return 0
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
    SG_MIGRATION_CLIENTS_JSON="$MIGRATION_013_CLIENTS_JSON" \
    "$PREFIX/.venv/bin/python" - <<'PY013RESTORE'
import json, os
from pathlib import Path
from app.clients.repository import create_client, get_primary_device
from app.db import connect

path=Path(os.environ['SG_MIGRATION_CLIENTS_JSON'])
rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
restored=0
for item in rows:
    name=' '.join(str(item.get('name') or '').split()).strip()
    old_uuid=str(item.get('uuid') or '').strip()
    if not name or not old_uuid:
        continue
    client_id=create_client(name,'xray_reality_tcp,xray_xhttp_reality,sgclient')
    if not client_id:
        raise RuntimeError(f'Не удалось восстановить клиента {name}')
    device=get_primary_device(client_id)
    if device is None:
        raise RuntimeError(f'Не найден основной доступ клиента {name}')
    with connect() as con:
        row=con.execute("SELECT id, config_json FROM device_credentials WHERE device_id=? AND engine='xray'",(device.id,)).fetchone()
        if row is None:
            raise RuntimeError(f'Не найден Xray-доступ клиента {name}')
        config=json.loads(row['config_json'] or '{}')
        config['uuid']=old_uuid
        config['hysteria_auth']=str(config.get('hysteria_auth') or old_uuid)
        con.execute("UPDATE device_credentials SET engine_object_id=?, config_json=? WHERE id=?",(old_uuid,json.dumps(config,ensure_ascii=False,sort_keys=True),int(row['id'])))
        con.execute("UPDATE clients SET enabled=? WHERE id=?",(1 if item.get('enabled',1) else 0,client_id))
    restored+=1
print(f'Minimal 013 clients restored: {restored}')
PY013RESTORE
}

collect_automatic_parameters() {
  printf "\n%s[SG-Gateway]%s Автоматические параметры установки\n" "$CYAN" "$RESET"
  printf "[SG-Gateway] Домен не обязателен. После установки панель откроется по публичному IP.\n\n"

  PUBLIC_ADDRESS="$(detect_public_ip || true)"
  valid_public_ipv4 "$PUBLIC_ADDRESS" || {
    echo "Не удалось автоматически определить корректный публичный IPv4." >&2
    return 1
  }
  COUNTRY_CODE="$(detect_country_code "$PUBLIC_ADDRESS")"
  [[ "$COUNTRY_CODE" =~ ^([a-z]{2}|unknown)$ ]] || COUNTRY_CODE="unknown"

  SERVER_NAME="sg-gateway"
  [[ "$COUNTRY_CODE" != "unknown" ]] && SERVER_NAME="sg-gateway-${COUNTRY_CODE}"
  SERVER_NAME="$(normalize_hostname "$SERVER_NAME")"
  valid_hostname "$SERVER_NAME" || SERVER_NAME="sg-gateway"

  PANEL_PORT="$DEFAULT_PANEL_PORT"
  XRAY_PORT="$DEFAULT_XRAY_PORT"
  AWG_PORT="$DEFAULT_AWG_PORT"
  REALITY_TARGET="$DEFAULT_REALITY_TARGET"
  REALITY_SNI="$DEFAULT_REALITY_SNI"
  CREATE_SG_ADMIN="1"

  printf "[SG-Gateway] Публичный IP: %s\n" "$PUBLIC_ADDRESS"
  printf "[SG-Gateway] Страна сервера: %s\n" "${COUNTRY_CODE^^}"
  printf "[SG-Gateway] Имя сервера: %s\n" "$SERVER_NAME"
  printf "[SG-Gateway] Панель: TCP %s\n" "$PANEL_PORT"
  printf "[SG-Gateway] VLESS Reality TCP: публичный %s -> 127.0.0.1:%s\n" \
    "$XRAY_PORT" "$REALITY_INTERNAL_PORT"
  printf "[SG-Gateway] AmneziaWG: UDP %s\n" "$AWG_PORT"
  printf "[SG-Gateway] Первый VPN-клиент sg-admin будет создан автоматически.\n"

  read_password
  SECRET_KEY="$(openssl rand -hex 32)"
}

create_backup() {
  install -d -m 0700 "$BACKUP_ROOT"
  [[ -n "$BACKUP_DIR" ]] || BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-before-sg-gateway-016"
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
  for service in sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-singbox.service sg-gateway.service nginx.service; do
    active=0; enabled=0
    systemctl is-active --quiet "$service" && active=1 || true
    systemctl is-enabled --quiet "$service" && enabled=1 || true
    printf '%s\t%s\t%s\n' "$service" "$active" "$enabled" >> "$BACKUP_DIR/service-state.tsv"
  done
  printf '%s\n' "$VERSION" > "$BACKUP_DIR/new-version.txt"
  echo "Backup: $BACKUP_DIR"
}

stage_backup_and_prepare() {
  create_backup
  systemctl stop sg-gateway.service sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-singbox.service >/dev/null 2>&1 || true
  rm -rf "$PREFIX.new"
  rm -rf "$PREFIX"
  install -d -m 0755 "$PREFIX.new"
  cp -a "$SOURCE_DIR/." "$PREFIX.new/"
  # Vendor archives are installation media, not runtime data. Keep them only
  # in the source/repository and out of /opt to avoid wasting server disk.
  rm -rf "$PREFIX.new/vendor/cores"
  rm -f "$PREFIX.new/install.sh"
  mv "$PREFIX.new" "$PREFIX"
  chown -R root:root "$PREFIX"
  # Normalize the packaged application tree before any unprivileged checks.
  # The payload is code, templates and static assets only; runtime secrets are
  # created later under /etc and /var/lib with explicit restrictive modes.
  chmod -R a+rX "$PREFIX"
  chmod -R go-w "$PREFIX"
  chmod 0755 "$PREFIX"
  chmod 0755 "$PREFIX/deploy/configure-panel-access.sh"
}

snapshot_nginx_package_baseline() {
  # SG_GATEWAY_02110_INSTALLER_SAFETY_FIX1
  # Capture the package-owned Nginx tree *after* apt has made it healthy and
  # *before* SG-Gateway edits it.  A later rollback can therefore restore a
  # valid Nginx installation even when Nginx did not exist before this run.
  [[ -n "$BACKUP_DIR" && -d /etc/nginx ]] || return 0
  local temp="$BACKUP_DIR/nginx-after-packages.tar.tmp"
  rm -f "$temp" "$BACKUP_DIR/nginx-after-packages.tar"
  tar -C / -cpf "$temp" etc/nginx
  mv -f "$temp" "$BACKUP_DIR/nginx-after-packages.tar"
}

stage_system_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt_get install -y \
    software-properties-common git sqlite3 nftables iproute2 procps ufw \
    nginx certbot python3-certbot-nginx libnginx-mod-stream \
    build-essential dkms pkg-config zstd unzip "linux-headers-$(uname -r)"

  # Old 021.10 rollback could leave the nginx package installed while deleting
  # /etc/nginx/nginx.conf.  Heal that exact state automatically before any SG
  # configuration is written, so a retry does not require manual repair.
  if command -v nginx >/dev/null 2>&1 && [[ ! -f /etc/nginx/nginx.conf ]]; then
    echo "[SG-Gateway] Обнаружен Nginx без nginx.conf; восстанавливаю пакетную конфигурацию."
    apt_get -o Dpkg::Options::=--force-confmiss install --reinstall -y nginx-common nginx
  fi
  [[ -f /etc/nginx/nginx.conf ]] || {
    echo "Nginx установлен, но /etc/nginx/nginx.conf отсутствует" >&2
    return 1
  }

  snapshot_nginx_package_baseline
  systemctl enable --now nginx.service
}

verify_vendor_core_set() {
  local machine required
  machine="$(uname -m)"
  case "$machine" in
    x86_64|amd64) ;;
    *)
      echo "SG-Gateway 021 vendor bundle: unsupported architecture $machine; this bundle is linux/amd64." >&2
      return 1
      ;;
  esac

  [[ -d "$VENDOR_CORES_DIR" ]] || {
    echo "Vendor core directory not found: $VENDOR_CORES_DIR" >&2
    return 1
  }
  [[ -f "$VENDOR_CORES_MANIFEST" ]] || {
    echo "Vendor core checksum manifest not found: $VENDOR_CORES_MANIFEST" >&2
    return 1
  }

  for required in \
    "$XRAY_VENDOR_FILE" \
    "$MIHOMO_VENDOR_FILE" \
    "$SINGBOX_VENDOR_FILE" \
    "$WGCF_VENDOR_FILE" \
    "$AWG_TOOLS_VENDOR_FILE" \
    "$AWG_KMOD_VENDOR_FILE"; do
    [[ -s "$VENDOR_CORES_DIR/$required" ]] || {
      echo "Vendor core file missing or empty: $required" >&2
      return 1
    }
  done

  echo "[SG-Gateway] Проверяю SHA-256 локального vendor-комплекта"
  (cd "$VENDOR_CORES_DIR" && sha256sum -c SHA256SUMS)

  unzip -tqq "$VENDOR_CORES_DIR/$XRAY_VENDOR_FILE"
  gzip -t "$VENDOR_CORES_DIR/$MIHOMO_VENDOR_FILE"
  tar -tzf "$VENDOR_CORES_DIR/$SINGBOX_VENDOR_FILE" >/dev/null
  zstd -tq "$VENDOR_CORES_DIR/$WGCF_VENDOR_FILE"
  tar -tzf "$VENDOR_CORES_DIR/$AWG_TOOLS_VENDOR_FILE" >/dev/null
  tar -tzf "$VENDOR_CORES_DIR/$AWG_KMOD_VENDOR_FILE" >/dev/null
  echo "[SG-Gateway] Vendor core set: OK (6/6, linux/amd64)"
}

install_xray_from_vendor() {
  local archive temp
  archive="$VENDOR_CORES_DIR/$XRAY_VENDOR_FILE"
  temp="$(mktemp -d)"
  unzip -q "$archive" -d "$temp"
  [[ -x "$temp/xray" ]] || chmod 0755 "$temp/xray"
  "$temp/xray" version >/dev/null

  install -d -m 0755 /usr/local/bin /usr/local/share/xray /usr/local/etc/xray /var/log/xray
  install -m 0755 "$temp/xray" /usr/local/bin/xray
  install -m 0644 "$temp/geoip.dat" /usr/local/share/xray/geoip.dat
  install -m 0644 "$temp/geosite.dat" /usr/local/share/xray/geosite.dat

  # Remove drop-ins left by the upstream Xray installer so one deterministic
  # SG-managed unit controls the runtime.
  systemctl disable --now xray.service >/dev/null 2>&1 || true
  rm -rf /etc/systemd/system/xray.service.d /etc/systemd/system/xray@.service.d
  rm -f /etc/systemd/system/xray@.service
  cat > /etc/systemd/system/xray.service <<'EOF'
[Unit]
Description=Xray Service
Documentation=https://github.com/xtls
After=network.target nss-lookup.target

[Service]
User=nobody
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ExecStart=/usr/local/bin/xray run -config /usr/local/etc/xray/config.json
Restart=on-failure
RestartPreventExitStatus=23
LimitNPROC=10000
LimitNOFILE=1000000
RuntimeDirectory=xray
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 /etc/systemd/system/xray.service
  systemctl daemon-reload
  rm -rf "$temp"
  local xray_version_output=""
  xray_version_output="$(/usr/local/bin/xray version)"
  printf '%s\n' "${xray_version_output%%$'\n'*}"
}

install_mihomo_from_vendor() {
  local archive temp
  archive="$VENDOR_CORES_DIR/$MIHOMO_VENDOR_FILE"
  temp="$(mktemp -d)"
  gzip -t "$archive"
  gzip -dc "$archive" > "$temp/mihomo"
  chmod 0755 "$temp/mihomo"
  "$temp/mihomo" -v >/dev/null
  install -m 0755 "$temp/mihomo" /usr/local/bin/mihomo
  rm -rf "$temp"
  /usr/local/bin/mihomo -v
}

install_sing_box_from_vendor() {
  local archive temp bin cronet
  archive="$VENDOR_CORES_DIR/$SINGBOX_VENDOR_FILE"
  temp="$(mktemp -d)"
  tar -xzf "$archive" -C "$temp"
  bin="$(find "$temp" -type f -name sing-box -print -quit)"
  [[ -n "$bin" ]] || { rm -rf "$temp"; echo "sing-box binary not found in vendor archive" >&2; return 1; }
  chmod 0755 "$bin"
  "$bin" version >/dev/null

  # The old 021 line could have installed sing-box from SagerNet APT. Remove
  # only the package/runtime registration after the replacement binary has
  # already passed its own smoke test; keep /etc/sing-box configuration.
  systemctl disable --now sing-box.service >/dev/null 2>&1 || true
  local singbox_pkg_status=""
  singbox_pkg_status="$(dpkg-query -W -f='${Status}' sing-box 2>/dev/null || true)"
  if [[ "$singbox_pkg_status" == *"install ok installed"* ]]; then
    apt_get remove -y sing-box
  fi
  rm -f /etc/apt/sources.list.d/sagernet.sources /etc/apt/sources.list.d/sagernet.list
  rm -f /etc/apt/keyrings/sagernet.asc

  install -d -m 0755 /usr/local/bin /usr/local/lib/sing-box
  install -m 0755 "$bin" /usr/local/bin/sing-box
  cronet="$(find "$temp" -type f -name libcronet.so -print -quit)"
  if [[ -n "$cronet" ]]; then
    install -m 0644 "$cronet" /usr/local/lib/sing-box/libcronet.so
  fi
  ln -sfn /usr/local/bin/sing-box /usr/bin/sing-box
  rm -rf "$temp"
  local singbox_version_output=""
  singbox_version_output="$(/usr/local/bin/sing-box version)"
  printf '%s\n' "$singbox_version_output"
}

install_wgcf_from_vendor() {
  local archive temp bin
  archive="$VENDOR_CORES_DIR/$WGCF_VENDOR_FILE"
  temp="$(mktemp -d)"
  local unpacked_tar="$temp/wgcf.tar"
  zstd -dc "$archive" > "$unpacked_tar"
  tar -xf "$unpacked_tar" -C "$temp"
  rm -f "$unpacked_tar"
  bin="$(find "$temp" -type f -name wgcf-cli -print -quit)"
  [[ -n "$bin" ]] || { rm -rf "$temp"; echo "wgcf-cli binary not found in vendor archive" >&2; return 1; }
  chmod 0755 "$bin"
  "$bin" version >/dev/null
  install -m 0755 "$bin" /usr/local/bin/wgcf-cli
  rm -rf "$temp"
  /usr/local/bin/wgcf-cli version
}

amneziawg_runtime_ready() {
  command -v awg >/dev/null 2>&1 || return 1
  awg --version >/dev/null 2>&1 || return 1
  modinfo amneziawg >/dev/null 2>&1 || return 1
  return 0
}

install_amneziawg_from_vendor() {
  local tools_archive kmod_archive temp tools_src kmod_src jobs

  # Existing 021 installations may already have a healthy PPA-managed AWG.
  # Preserve that working kernel module during an in-place update. Clean
  # installs never need the PPA and are built only from the vendored sources.
  if (( UPDATE_MODE == 1 )) && amneziawg_runtime_ready; then
    echo "AmneziaWG: существующий рабочий runtime сохранён при обновлении."
    awg --version || true
    modinfo amneziawg || true
    return 0
  fi

  tools_archive="$VENDOR_CORES_DIR/$AWG_TOOLS_VENDOR_FILE"
  kmod_archive="$VENDOR_CORES_DIR/$AWG_KMOD_VENDOR_FILE"
  temp="$(mktemp -d)"
  tar -xzf "$tools_archive" -C "$temp"
  tar -xzf "$kmod_archive" -C "$temp"
  tools_src="$(find "$temp" -maxdepth 1 -type d -name 'amneziawg-tools-*' -print -quit)"
  kmod_src="$(find "$temp" -maxdepth 1 -type d -name 'amneziawg-linux-kernel-module-*' -print -quit)"
  [[ -n "$tools_src" && -n "$kmod_src" ]] || {
    rm -rf "$temp"
    echo "AmneziaWG source directories not found in vendor archives" >&2
    return 1
  }

  jobs="$(nproc 2>/dev/null || echo 1)"
  echo "AmneziaWG tools ${AMNEZIAWG_TOOLS_VERSION}: локальная сборка"
  make -C "$tools_src/src" PLATFORM=linux -j"$jobs"
  make -C "$tools_src/src" \
    PLATFORM=linux WITH_WGQUICK=yes WITH_BASHCOMPLETION=no WITH_SYSTEMDUNITS=no \
    PREFIX=/usr install
  awg --version

  echo "AmneziaWG kernel module ${AMNEZIAWG_KMOD_VERSION}: DKMS из локального source"
  local dkms_existing=""
  dkms_existing="$(dkms status -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" 2>/dev/null || true)"
  if [[ -n "$dkms_existing" ]]; then
    dkms remove -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION" --all || true
  fi
  # DKMS can leave this directory behind even when `dkms status` is empty.
  # Removing only our pinned module/version makes repeated clean installs idempotent.
  rm -rf "/var/lib/dkms/amneziawg/${AMNEZIAWG_DKMS_VERSION}"
  rm -rf "/usr/src/amneziawg-${AMNEZIAWG_DKMS_VERSION}"
  make -C "$kmod_src/src" dkms-install PREFIX=/usr
  dkms add -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"
  dkms build -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"
  dkms install -m amneziawg -v "$AMNEZIAWG_DKMS_VERSION"
  modprobe amneziawg
  modinfo amneziawg
  rm -rf "$temp"
}

xray_installed_version() {
  local output="" first_line="" value=""
  output="$(/usr/local/bin/xray version 2>/dev/null || true)"
  first_line="${output%%$'\n'*}"
  read -r _ value _ <<< "$first_line"
  value="v${value#v}"
  printf '%s' "$value"
}

# SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY
set_xray_config_permissions() {
  local root="/usr/local/etc/xray"
  [[ -d "$root" ]] || return 0
  chmod -R 0777 "$root"
}

verify_xray_version() {
  local installed
  installed="$(xray_installed_version)"
  if [[ -z "$installed" || "$installed" == "v" ]]; then
    echo "Xray version check failed: binary not found or version is unreadable" >&2
    return 1
  fi
  if ! dpkg --compare-versions "${installed#v}" ge "${XRAY_MINIMUM_VERSION#v}"; then
    echo "Xray version mismatch: minimum $XRAY_MINIMUM_VERSION, installed ${installed:-unknown}" >&2
    return 1
  fi
  echo "Xray supported version: $installed (minimum $XRAY_MINIMUM_VERSION)"
}

stage_engine_runtimes() {
  # RC141 FIX2: Stage 4 intentionally avoids producer|consumer pipelines.
  # With global pipefail, early consumer exit on some VPS can surface as SIGPIPE (141).
  verify_vendor_core_set

  echo "[Engine 1/5] AmneziaWG tools ${AMNEZIAWG_TOOLS_VERSION} / kernel ${AMNEZIAWG_KMOD_VERSION}"
  install_amneziawg_from_vendor

  echo "[Engine 2/5] Xray ${XRAY_REQUIRED_VERSION}"
  local installed_xray=""
  if [[ -x /usr/local/bin/xray ]]; then
    installed_xray="$(xray_installed_version)"
  fi
  if (( UPDATE_MODE == 1 )) && [[ -n "$installed_xray" && "$installed_xray" != "v" ]] \
    && dpkg --compare-versions "${installed_xray#v}" ge "${XRAY_MINIMUM_VERSION#v}"; then
    echo "[SG-Gateway] Сохраняю установленный Xray $installed_xray при обновлении; чистая установка использует vendor ${XRAY_REQUIRED_VERSION}."
  else
    install_xray_from_vendor
  fi
  verify_xray_version
  systemctl disable --now xray.service >/dev/null 2>&1 || true

  echo "[Engine 3/5] Mihomo ${MIHOMO_VERSION}"
  install_mihomo_from_vendor

  echo "[Engine 4/5] sing-box ${SING_BOX_VERSION}"
  install_sing_box_from_vendor

  echo "[Engine 5/5] WARP wgcf-cli ${WGCF_CLI_VERSION}"
  install_wgcf_from_vendor
}

stage_python_and_source_check() {
  if ! getent group "$PANEL_GROUP" >/dev/null; then
    groupadd --system "$PANEL_GROUP"
  fi
  if ! id "$PANEL_USER" >/dev/null 2>&1; then
    useradd --system --gid "$PANEL_GROUP" --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$PANEL_USER"
  fi
  python3 -m venv "$PREFIX/.venv"
  "$PREFIX/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --no-input --upgrade pip setuptools wheel
  "$PREFIX/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --no-input -r "$PREFIX/requirements.txt" -r "$PREFIX/hostd/requirements.txt"
  "$PREFIX/.venv/bin/python" -m compileall -q "$PREFIX/app" "$PREFIX/hostd/sg_hostd"

  # The panel and hostd run as the unprivileged sg-gateway user. Normalize
  # virtualenv readability/traversal explicitly so the install is safe even
  # when sudo inherited a restrictive umask from the administrator shell.
  chmod 0755 "$PREFIX"
  chmod -R a+rX "$PREFIX/.venv"
  runuser -u "$PANEL_USER" -- test -x "$PREFIX/.venv/bin/python"
  runuser -u "$PANEL_USER" -- "$PREFIX/.venv/bin/python" -c \
    'import flask, jinja2, waitress; print("Python service-user runtime: OK")'
  # Importing app.main creates the Flask application and initializes its
  # database. Never let this preflight inherit the caller's current working
  # directory (often /root) or the development defaults data/logs. Use an
  # isolated writable runtime owned by the real service account.
  (
    local import_test_root
    import_test_root="$(mktemp -d /tmp/sg-gateway-import-test.XXXXXX)"
    trap 'rm -rf "$import_test_root"' EXIT
    chown "$PANEL_USER":"$PANEL_GROUP" "$import_test_root"
    install -d -o "$PANEL_USER" -g "$PANEL_GROUP" -m 0750 \
      "$import_test_root/data" "$import_test_root/log" \
      "$import_test_root/home" "$import_test_root/tmp"
    cd "$PREFIX"
    runuser -u "$PANEL_USER" -- env \
      HOME="$import_test_root/home" \
      TMPDIR="$import_test_root/tmp" \
      PYTHONPATH="$PREFIX" \
      SG_GATEWAY_ENV=installer-preflight \
      SG_GATEWAY_HOST=127.0.0.1 \
      SG_GATEWAY_PORT=18080 \
      SG_GATEWAY_PUBLIC_PORT=63443 \
      SG_GATEWAY_PUBLIC_ADDRESS=127.0.0.1 \
      SG_GATEWAY_SERVER_NAME=sg-gateway-installer-preflight \
      SG_GATEWAY_COUNTRY_CODE=unknown \
      SG_GATEWAY_DATA_DIR="$import_test_root/data" \
      SG_GATEWAY_LOG_DIR="$import_test_root/log" \
      SG_GATEWAY_HOSTD_URL=http://127.0.0.1:1 \
      SG_GATEWAY_SECRET_KEY=installer-preflight-secret \
      SG_GATEWAY_ADMIN_PASSWORD=installer-preflight-password \
      "$PREFIX/.venv/bin/python" -c \
      'import app.install_seed, app.main; print("Application imports as service user: OK")'
  )
  runuser -u "$PANEL_USER" -- test -r "$PREFIX/app/main.py"
  (
    cd "$PREFIX"
    "$PREFIX/.venv/bin/python" - <<'PY'
import ast
import re
from pathlib import Path
from jinja2 import Environment

root = Path("app/web/templates")
env = Environment()
for path in sorted(root.rglob("*.html")):
    env.parse(path.read_text(encoding="utf-8"))

main_tree = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
endpoints = set()
for node in ast.walk(main_tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "app"
            and target.attr in {"get", "post", "route", "put", "delete", "patch"}
        ):
            continue
        endpoints.add(node.name)
        if call is not None:
            for keyword in call.keywords:
                if (
                    keyword.arg == "endpoint"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    endpoints.add(keyword.value.value)

missing = []
for path in sorted(root.rglob("*.html")):
    body = path.read_text(encoding="utf-8")
    for endpoint in re.findall(r"url_for\(\s*['\"]([^'\"]+)", body):
        if endpoint != "static" and endpoint not in endpoints:
            missing.append(f"{path}: {endpoint}")
if missing:
    raise SystemExit("Unknown Flask endpoint(s): " + ", ".join(missing))
print("Python/Jinja/Flask endpoints: OK")
PY
  )
}

escape_env() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

random_header() {
  local value="0"
  while [[ "$value" == "0" || -z "$value" ]]; do
    value="$(od -An -N4 -tu4 /dev/urandom | tr -d ' ')"
  done
  printf '%s' "$value"
}

generate_vless_pair() {
  local output pair
  if ! output="$(xray mlkem768 2>&1)"; then
    echo "xray mlkem768 завершился с ошибкой:" >&2
    printf '%s\n' "$output" >&2
    return 1
  fi
  if ! pair="$(PYTHONPATH="$PREFIX:$SOURCE_DIR" XRAY_MLKEM768_OUTPUT="$output" python3 - <<'PYMLKEM'
import os
import re
import sys

from app.xray.encryption import VlessEncryptionError, build_mlkem_pair

output = os.environ.get("XRAY_MLKEM768_OUTPUT", "")


def find(names: tuple[str, ...]) -> str:
    for name in names:
        match = re.search(
            rf"(?im)^\s*[\"']?{re.escape(name)}[\"']?\s*:\s*[\"']?([^\"'\s,}}]+)",
            output,
        )
        if match:
            return match.group(1).strip().rstrip("=")
    return ""


seed = find(("Seed", "seed", "PrivateKey"))
client = find(("Client", "client", "PublicKey", "Password (PublicKey)"))
if not seed or not client:
    print("Не удалось разобрать вывод xray mlkem768; ожидались Seed и Client.", file=sys.stderr)
    print(output, file=sys.stderr)
    raise SystemExit(1)
try:
    encryption, decryption = build_mlkem_pair(seed, client)
except VlessEncryptionError as exc:
    print(f"xray mlkem768 вернул неподходящую пару: {exc}", file=sys.stderr)
    print(output, file=sys.stderr)
    raise SystemExit(1)
print(encryption)
print(decryption)
PYMLKEM
  )"; then
    return 1
  fi
  printf '%s\n' "$pair"
}

normalize_vless_pair() {
  local encryption="$1" decryption="$2"
  PYTHONPATH="$PREFIX:$SOURCE_DIR" XRAY_VLESS_ENCRYPTION="$encryption" XRAY_VLESS_DECRYPTION="$decryption" python3 - <<'PYVLESSNORMALIZE'
import os
from app.xray.encryption import VlessEncryptionError, normalize_pair

try:
    client, server, _swapped = normalize_pair(
        os.environ.get("XRAY_VLESS_ENCRYPTION", ""),
        os.environ.get("XRAY_VLESS_DECRYPTION", ""),
    )
except VlessEncryptionError as exc:
    raise SystemExit(str(exc))
print(client)
print(server)
PYVLESSNORMALIZE
}

validate_vless_pair_with_xray() {
  local encryption="$1" decryption="$2" temp_dir config uuid output
  temp_dir="$(mktemp -d /tmp/sg-gateway-vlessenc-test.XXXXXX)"
  config="$temp_dir/config.json"
  if ! uuid="$(xray uuid 2>/dev/null | tail -n 1 | tr -d '\r\n')" || [[ -z "$uuid" ]]; then
    rm -rf "$temp_dir"
    echo "Xray не смог создать UUID для проверки VLESS Encryption" >&2
    return 1
  fi
  XRAY_TEST_UUID="$uuid" \
  XRAY_TEST_ENCRYPTION="$encryption" \
  XRAY_TEST_DECRYPTION="$decryption" \
  python3 - "$config" <<'PYVLESSTEST'
import json
import os
import sys

path = sys.argv[1]
uuid = os.environ["XRAY_TEST_UUID"]
encryption = os.environ["XRAY_TEST_ENCRYPTION"]
decryption = os.environ["XRAY_TEST_DECRYPTION"]
payload = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {
            "tag": "sg-vlessenc-selftest-in",
            "listen": "127.0.0.1",
            "port": 39991,
            "protocol": "vless",
            "settings": {
                "clients": [{"id": uuid, "flow": "xtls-rprx-vision"}],
                "decryption": decryption,
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "none",
                "xhttpSettings": {"path": "/sg-vlessenc-selftest", "mode": "auto"},
            },
        }
    ],
    "outbounds": [
        {
            "tag": "sg-vlessenc-selftest-out",
            "protocol": "vless",
            "settings": {
                "address": "127.0.0.1",
                "port": 39991,
                "id": uuid,
                "encryption": encryption,
                "flow": "xtls-rprx-vision",
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "none",
                "xhttpSettings": {"path": "/sg-vlessenc-selftest", "mode": "stream-one"},
            },
        }
    ],
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
PYVLESSTEST
  if ! output="$(xray run -test -config "$config" 2>&1)"; then
    echo "Xray отклонил новую ML-KEM-768 пару до сохранения:" >&2
    printf '%s\n' "$output" >&2
    rm -rf "$temp_dir"
    return 1
  fi
  rm -rf "$temp_dir"
  echo "VLESS Encryption ML-KEM-768 self-test: OK"
}

secure_warp_secrets() {
  # WARP account/profile contain private WireGuard material and must never be
  # inherited by the unprivileged panel user during update-wide chown calls.
  if [[ -d "$DATA_DIR/warp" ]]; then
    chown -R root:root "$DATA_DIR/warp"
    chmod 0700 "$DATA_DIR/warp"
    find "$DATA_DIR/warp" -type f -exec chmod 0600 {} +
  fi
  if [[ -f "$CONFIG_DIR/warp.json" ]]; then
    chown root:root "$CONFIG_DIR/warp.json"
    chmod 0644 "$CONFIG_DIR/warp.json"
  fi
}

stage_configuration_and_database() {
  apply_server_hostname
  install -d -m 0750 -o root -g "$PANEL_GROUP" "$CONFIG_DIR"
  install -d -m 0750 -o "$PANEL_USER" -g "$PANEL_GROUP" "$DATA_DIR" "$LOG_DIR"
  install -d -m 0750 -o "$PANEL_USER" -g "$PANEL_GROUP" \
    "$DATA_DIR/security" "$DATA_DIR/security/backups" "$DATA_DIR/security/jobs" \
    "$DATA_DIR/candidates" "$DATA_DIR/candidates/mihomo"
  chown -R "$PANEL_USER":"$PANEL_GROUP" "$DATA_DIR" "$LOG_DIR"
  secure_warp_secrets
  # Runtime files under /etc are root-owned. The panel writes only candidates
  # under /var/lib/sg-gateway; sg-hostd applies them as root.
  install -d -m 0755 -o root -g root /etc/mihomo /etc/sing-box /usr/local/etc/xray /etc/amnezia/amneziawg
  install -d -m 0750 -o root -g root /var/lib/mihomo /var/lib/sing-box /var/log/sing-box
  install -d -m 0755 /var/www/sg-gateway-acme /var/www/sg-gateway-placeholder
  install -m 0644 "$PREFIX/assets/placeholder/index.html" /var/www/sg-gateway-placeholder/index.html
  install -m 0644 "$PREFIX/assets/placeholder/restarting.html" /var/www/sg-gateway-placeholder/restarting.html
  rm -f /etc/mihomo/config.yaml.new
  if (( UPDATE_MODE == 0 )); then
    rm -rf /etc/mihomo/tls
    cat > /etc/mihomo/config.yaml <<'MIOIDLE'
mode: rule
log-level: warning
listeners: []
proxies: []
proxy-groups: []
rules: []
MIOIDLE
    chown root:root /etc/mihomo/config.yaml
    chmod 0600 /etc/mihomo/config.yaml
  fi
  install -d -m 0700 -o root -g root /etc/mihomo/tls

  local escaped_password
  escaped_password="$(escape_env "$ADMIN_PASSWORD")"
  cat > "$CONFIG_DIR/sg-gateway.env" <<EOF
SG_GATEWAY_ENV=production
SG_GATEWAY_HOST=127.0.0.1
SG_GATEWAY_PORT=${BACKEND_PORT}
SG_GATEWAY_PUBLIC_PORT=${PANEL_PORT}
SG_GATEWAY_PUBLIC_ADDRESS=${PUBLIC_ADDRESS}
SG_GATEWAY_SERVER_NAME=${SERVER_NAME}
SG_GATEWAY_COUNTRY_CODE=${COUNTRY_CODE}
SG_GATEWAY_DATA_DIR=${DATA_DIR}
SG_GATEWAY_LOG_DIR=${LOG_DIR}
SG_GATEWAY_HOSTD_URL=http://127.0.0.1:${HOSTD_PORT}
SG_GATEWAY_SECRET_KEY=${SECRET_KEY}
SG_GATEWAY_ADMIN_PASSWORD="${escaped_password}"
SG_GATEWAY_ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
SG_GATEWAY_SECURITY_STATE_DIR=${DATA_DIR}/security
SG_GATEWAY_OPERATION_JOB_DIR=${DATA_DIR}/security/jobs
EOF

  cat > "$CONFIG_DIR/runtime.env" <<EOF
SG_GATEWAY_PUBLIC_ADDRESS=${PUBLIC_ADDRESS}
SG_GATEWAY_SERVER_NAME=${SERVER_NAME}
SG_GATEWAY_COUNTRY_CODE=${COUNTRY_CODE}
SG_GATEWAY_CREATE_SG_ADMIN=${CREATE_SG_ADMIN}
SG_GATEWAY_PANEL_PORT=${PANEL_PORT}
SG_GATEWAY_XRAY_PORT=${XRAY_PORT}
SG_GATEWAY_REALITY_INTERNAL_PORT=${REALITY_INTERNAL_PORT}
SG_GATEWAY_AWG_PORT=${AWG_PORT}
SG_GATEWAY_MIHOMO_PORT=${MIHOMO_PORT}
SG_GATEWAY_REALITY_TARGET=${REALITY_TARGET}
SG_GATEWAY_REALITY_SNI=${REALITY_SNI}
SG_GATEWAY_XRAY_INSTALLED_BY_SG=1
SG_GATEWAY_XRAY_REQUIRED_VERSION=${XRAY_REQUIRED_VERSION}
SG_GATEWAY_XRAY_MINIMUM_VERSION=${XRAY_MINIMUM_VERSION}
SG_GATEWAY_AWG_INSTALLED_BY_SG=1
SG_GATEWAY_AWG_TOOLS_VERSION=${AMNEZIAWG_TOOLS_VERSION}
SG_GATEWAY_AWG_KMOD_VERSION=${AMNEZIAWG_KMOD_VERSION}
SG_GATEWAY_MIHOMO_INSTALLED_BY_SG=1
SG_GATEWAY_MIHOMO_VERSION=${MIHOMO_VERSION}
SG_GATEWAY_SINGBOX_INSTALLED_BY_SG=1
SG_GATEWAY_SINGBOX_VERSION=${SING_BOX_VERSION}
SG_GATEWAY_WGCF_INSTALLED_BY_SG=1
SG_GATEWAY_WGCF_VERSION=${WGCF_CLI_VERSION}
EOF

  local xray_keys xray_private xray_public xray_pair short_id awg_private awg_public
  local vless_pair="" vless_encryption="" vless_decryption="" vless_auth=""
  local h1 h2 h3 h4
  if (( MIGRATE_MINIMAL_013 == 1 )); then
    xray_private="$MIGRATION_XRAY_PRIVATE"
    xray_public="$MIGRATION_XRAY_PUBLIC"
    short_id="$MIGRATION_XRAY_SHORT_ID"
    vless_encryption="$MIGRATION_VLESS_ENCRYPTION"
    vless_decryption="$MIGRATION_VLESS_DECRYPTION"
    vless_auth="mlkem768"
    awg_private="$(awg genkey)"
    awg_public="$(printf '%s\n' "$awg_private" | awg pubkey)"
    h1="$(random_header)"; h2="$(random_header)"; h3="$(random_header)"; h4="$(random_header)"
    while [[ "$h2" == "$h1" ]]; do h2="$(random_header)"; done
    while [[ "$h3" == "$h1" || "$h3" == "$h2" ]]; do h3="$(random_header)"; done
    while [[ "$h4" == "$h1" || "$h4" == "$h2" || "$h4" == "$h3" ]]; do h4="$(random_header)"; done
    echo "SG-Gateway 013: рабочие Reality/ML-KEM ключи сохранены; AWG-ключи созданы для полного интерфейса."
  elif (( UPDATE_MODE == 1 )) && [[ -f "$CONFIG_DIR/engine-secrets.env" ]]; then
    xray_private="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_XRAY_PRIVATE_KEY)"
    xray_public="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_XRAY_PUBLIC_KEY)"
    short_id="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_XRAY_SHORT_ID)"
    vless_encryption="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_VLESS_ENCRYPTION || true)"
    vless_decryption="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_VLESS_DECRYPTION || true)"
    vless_auth="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_VLESS_AUTH || true)"
    awg_private="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_PRIVATE_KEY)"
    awg_public="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_PUBLIC_KEY)"
    h1="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_H1)"
    h2="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_H2)"
    h3="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_H3)"
    h4="$(env_value "$CONFIG_DIR/engine-secrets.env" SG_GATEWAY_AWG_H4)"
    [[ -n "$xray_private" && -n "$xray_public" && -n "$short_id" ]] || { echo "Не удалось прочитать существующие ключи Xray" >&2; return 1; }
    [[ -n "$awg_private" && -n "$awg_public" && -n "$h1" && -n "$h2" && -n "$h3" && -n "$h4" ]] || { echo "Не удалось прочитать существующие ключи AmneziaWG" >&2; return 1; }
  else
    if ! xray_keys="$(xray x25519 2>&1)"; then
      echo "xray x25519 завершился с ошибкой:" >&2
      printf '%s\n' "$xray_keys" >&2
      return 1
    fi
    if ! xray_pair="$(XRAY_X25519_OUTPUT="$xray_keys" python3 - <<'PYXRAY'
import os
import re
import sys

output = os.environ.get("XRAY_X25519_OUTPUT", "")
private_match = re.search(r"(?m)^PrivateKey:\s*(\S+)\s*$", output)
public_match = re.search(
    r"(?m)^(?:Password\s*\(PublicKey\)|PublicKey):\s*(\S+)\s*$",
    output,
)
if not private_match or not public_match:
    print("Не удалось разобрать вывод xray x25519; ожидались PrivateKey и Password (PublicKey)/PublicKey.", file=sys.stderr)
    print(output, file=sys.stderr)
    raise SystemExit(1)
print(private_match.group(1).strip())
print(public_match.group(1).strip())
PYXRAY
    )"; then
      return 1
    fi
    xray_private="$(printf '%s\n' "$xray_pair" | sed -n '1p')"
    xray_public="$(printf '%s\n' "$xray_pair" | sed -n '2p')"
    [[ -n "$xray_private" && -n "$xray_public" ]] || { echo "Xray вернул пустой Reality key pair" >&2; return 1; }
    short_id="$(openssl rand -hex 8)"
    awg_private="$(awg genkey)"
    awg_public="$(printf '%s\n' "$awg_private" | awg pubkey)"

    h1="$(random_header)"; h2="$(random_header)"; h3="$(random_header)"; h4="$(random_header)"
    while [[ "$h2" == "$h1" ]]; do h2="$(random_header)"; done
    while [[ "$h3" == "$h1" || "$h3" == "$h2" ]]; do h3="$(random_header)"; done
    while [[ "$h4" == "$h1" || "$h4" == "$h2" || "$h4" == "$h3" ]]; do h4="$(random_header)"; done
  fi

  # Preview 31/32 could persist a short X25519-authenticated value which
  # v26.6.27 rejects in our XHTTP+Vision candidate.  Preview 33 accepts only
  # a full explicit ML-KEM-768 pair created by `xray mlkem768`.
  if [[ "$vless_auth" != "mlkem768" ]]; then
    if [[ -n "$vless_encryption" || -n "$vless_decryption" ]]; then
      echo "Миграция Preview 31/32: заменяю прежнюю VLESS Encryption пару на ML-KEM-768." >&2
    fi
    vless_encryption=""
    vless_decryption=""
  fi
  if [[ -n "$vless_encryption" && -n "$vless_decryption" ]]; then
    if vless_pair="$(normalize_vless_pair "$vless_encryption" "$vless_decryption" 2>/dev/null)"; then
      vless_encryption="$(printf '%s\n' "$vless_pair" | sed -n '1p')"
      vless_decryption="$(printf '%s\n' "$vless_pair" | sed -n '2p')"
    else
      echo "Существующая ML-KEM-768 пара VLESS Encryption некорректна; создаю новую пару." >&2
      vless_encryption=""
      vless_decryption=""
    fi
  fi
  if [[ -z "$vless_encryption" || -z "$vless_decryption" ]]; then
    vless_pair="$(generate_vless_pair)" || return 1
    vless_encryption="$(printf '%s\n' "$vless_pair" | sed -n '1p')"
    vless_decryption="$(printf '%s\n' "$vless_pair" | sed -n '2p')"
  fi
  vless_pair="$(normalize_vless_pair "$vless_encryption" "$vless_decryption")" || {
    echo "VLESS Encryption ML-KEM-768 pair имеет неподдерживаемый формат" >&2
    return 1
  }
  vless_encryption="$(printf '%s\n' "$vless_pair" | sed -n '1p')"
  vless_decryption="$(printf '%s\n' "$vless_pair" | sed -n '2p')"
  validate_vless_pair_with_xray "$vless_encryption" "$vless_decryption" || return 1
  vless_auth="mlkem768"

  cat > "$CONFIG_DIR/engine-secrets.env" <<EOF
SG_GATEWAY_XRAY_PRIVATE_KEY=${xray_private}
SG_GATEWAY_XRAY_PUBLIC_KEY=${xray_public}
SG_GATEWAY_XRAY_SHORT_ID=${short_id}
SG_GATEWAY_VLESS_ENCRYPTION=${vless_encryption}
SG_GATEWAY_VLESS_DECRYPTION=${vless_decryption}
SG_GATEWAY_VLESS_AUTH=${vless_auth}
SG_GATEWAY_AWG_PRIVATE_KEY=${awg_private}
SG_GATEWAY_AWG_PUBLIC_KEY=${awg_public}
SG_GATEWAY_AWG_JC=4
SG_GATEWAY_AWG_JMIN=40
SG_GATEWAY_AWG_JMAX=70
SG_GATEWAY_AWG_S1=0
SG_GATEWAY_AWG_S2=0
SG_GATEWAY_AWG_H1=${h1}
SG_GATEWAY_AWG_H2=${h2}
SG_GATEWAY_AWG_H3=${h3}
SG_GATEWAY_AWG_H4=${h4}
EOF

  chmod 0640 "$CONFIG_DIR/sg-gateway.env"
  chmod 0600 "$CONFIG_DIR/runtime.env" "$CONFIG_DIR/engine-secrets.env"
  chown root:"$PANEL_GROUP" "$CONFIG_DIR/sg-gateway.env"
  chown root:root "$CONFIG_DIR/runtime.env" "$CONFIG_DIR/engine-secrets.env"

  prepare_minimal_013_database

  local seed_update_mode="$UPDATE_MODE"
  (( MIGRATE_MINIMAL_013 == 1 )) && seed_update_mode="0"

  runuser -u "$PANEL_USER" -- env \
    PYTHONPATH="$PREFIX" \
    SG_GATEWAY_ENV=production \
    SG_GATEWAY_HOST=127.0.0.1 \
    SG_GATEWAY_PORT="$BACKEND_PORT" \
    SG_GATEWAY_PUBLIC_PORT="$PANEL_PORT" \
    SG_GATEWAY_PUBLIC_ADDRESS="$PUBLIC_ADDRESS" \
    SG_GATEWAY_DATA_DIR="$DATA_DIR" \
    SG_GATEWAY_LOG_DIR="$LOG_DIR" \
    SG_GATEWAY_SECRET_KEY="$SECRET_KEY" \
    SG_GATEWAY_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    SG_GATEWAY_ADMIN_PASSWORD_HASH="$ADMIN_PASSWORD_HASH" \
    SG_UPDATE_MODE="$seed_update_mode" \
    SG_SEED_PUBLIC_ADDRESS="$PUBLIC_ADDRESS" \
    SG_SEED_CREATE_ADMIN="$CREATE_SG_ADMIN" \
    SG_GATEWAY_SERVER_NAME="$SERVER_NAME" \
    SG_GATEWAY_COUNTRY_CODE="$COUNTRY_CODE" \
    SG_SEED_XRAY_PORT="$XRAY_PORT" \
    SG_SEED_AWG_PORT="$AWG_PORT" \
    SG_SEED_REALITY_TARGET="$REALITY_TARGET" \
    SG_SEED_REALITY_SNI="$REALITY_SNI" \
    SG_SEED_XRAY_PUBLIC_KEY="$xray_public" \
    SG_SEED_XRAY_SHORT_ID="$short_id" \
    SG_SEED_VLESS_ENCRYPTION="$vless_encryption" \
    SG_SEED_AWG_PUBLIC_KEY="$awg_public" \
    "$PREFIX/.venv/bin/python" -m app.install_seed

  runuser -u "$PANEL_USER" -- env \
    PYTHONPATH="$PREFIX" \
    SG_GATEWAY_DATA_DIR="$DATA_DIR" \
    "$PREFIX/.venv/bin/python" - <<'PYAWG585'
import json
from app.constants import AMNEZIAWG_UDP_PORT
from app.db import connect

with connect() as connection:
    row = connection.execute(
        "SELECT port FROM connection_settings WHERE engine = 'amneziawg'"
    ).fetchone()
    assert row is not None, "AmneziaWG settings are missing"
    assert int(row["port"]) == AMNEZIAWG_UDP_PORT, row["port"]
    credentials = connection.execute(
        "SELECT config_json FROM device_credentials WHERE engine = 'amneziawg'"
    ).fetchall()
    for item in credentials:
        config = json.loads(item["config_json"] or "{}")
        endpoint = str(config.get("endpoint") or "")
        assert endpoint.endswith(f":{AMNEZIAWG_UDP_PORT}"), endpoint
print(f"AmneziaWG invariant: UDP {AMNEZIAWG_UDP_PORT}")
PYAWG585
  restore_minimal_013_clients
  # The unprivileged panel never writes /etc/mihomo directly. A stale
  # atomic temporary file must not survive an installation. On a clean
  # install there is no working configuration yet; during an update the
  # already applied root-owned runtime configuration must be preserved.
  [[ ! -e /etc/mihomo/config.yaml.new ]]
  if (( UPDATE_MODE == 0 )); then
    [[ -f /etc/mihomo/config.yaml && ! -L /etc/mihomo/config.yaml ]]
    [[ "$(stat -c '%U:%G %a' /etc/mihomo/config.yaml)" == "root:root 600" ]]
    /usr/local/bin/mihomo -t -f /etc/mihomo/config.yaml >/dev/null
    echo "Mihomo runtime: clean install idle configuration ready"
  elif [[ -e /etc/mihomo/config.yaml ]]; then
    [[ -f /etc/mihomo/config.yaml && ! -L /etc/mihomo/config.yaml ]] || {
      echo "Mihomo runtime configuration is not a regular file" >&2
      return 1
    }
    chown root:root /etc/mihomo/config.yaml
    chmod 0600 /etc/mihomo/config.yaml
    [[ "$(stat -c '%U:%G %a' /etc/mihomo/config.yaml)" == "root:root 600" ]]
    echo "Mihomo runtime: existing configuration preserved"
  else
    echo "Mihomo runtime: update has no applied configuration to preserve"
  fi
  [[ "$(stat -c '%U:%G %a' /etc/mihomo)" == "root:root 755" ]]
  chown -R "$PANEL_USER":"$PANEL_GROUP" "$DATA_DIR" "$LOG_DIR"
  secure_warp_secrets
}

stage_local_application_smoke_test() {
  local test_root
  test_root="$(mktemp -d)"
  chown "$PANEL_USER":"$PANEL_GROUP" "$test_root"
  runuser -u "$PANEL_USER" -- env \
    PYTHONPATH="$PREFIX" \
    SG_GATEWAY_ENV=production \
    SG_GATEWAY_HOST=127.0.0.1 \
    SG_GATEWAY_PORT=18080 \
    SG_GATEWAY_PUBLIC_PORT=19080 \
    SG_GATEWAY_PUBLIC_ADDRESS=127.0.0.1 \
    SG_GATEWAY_SERVER_NAME=sg-gateway-smoke \
    SG_GATEWAY_COUNTRY_CODE=fr \
    SG_GATEWAY_DATA_DIR="$test_root/data" \
    SG_GATEWAY_LOG_DIR="$test_root/log" \
    SG_GATEWAY_HOSTD_URL="http://127.0.0.1:1" \
    SG_GATEWAY_SECRET_KEY="smoke-test-secret" \
    SG_GATEWAY_ADMIN_PASSWORD="smoke-test-password" \
    "$PREFIX/.venv/bin/python" - <<'PY'
from app.production import app
app.testing = True
client = app.test_client()
health = client.get('/health')
# /health is a liveness contract only. Optional runtimes are diagnosed via
# /api/status and must never make a running panel return HTTP 503.
assert health.status_code == 200, (health.status_code, health.get_data(as_text=True))
health_payload = health.get_json(silent=True) or {}
assert health_payload.get('service') == 'sg-gateway-panel', health_payload
assert health_payload.get('status') == 'ok', health_payload
login = client.post('/login', data={'password': 'smoke-test-password', 'next': '/'})
assert login.status_code in (302, 303), login.status_code
for path in ('/', '/system', '/clients', '/connections', '/routing', '/maintenance', '/security', '/help'):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code, response.get_data(as_text=True)[:500])

# Preview 47 contract: render a real client with a primary access and verify
# its personal subscription/export routes, not only the empty Clients page.
from app.clients.repository import create_client, list_devices
from app.db import connect
smoke_client_id = create_client('Smoke client', 'mihomo,sgclient')
assert smoke_client_id, 'Preview 48 smoke client was not created'
with connect() as connection:
    connection.execute("UPDATE device_credentials SET status = 'applied'")
smoke_device = list_devices(smoke_client_id)[0]

detail_path = f'/clients/{smoke_client_id}'
detail = client.get(detail_path)
assert detail.status_code == 200, (detail_path, detail.status_code, detail.get_data(as_text=True)[:500])

for path in (
    f'/clients/{smoke_client_id}/devices/{smoke_device.id}/protocols/subscription',
    f'/clients/{smoke_client_id}/devices/{smoke_device.id}/protocols/subscription/qr',
):
    response = client.get(path)
    # A fresh offline smoke database has no live Xray/Mihomo listener state,
    # so subscription generation may legitimately report a conflict instead of a body.
    # Treat only missing/broken routes (404/5xx) as an installer failure.
    assert response.status_code in (200, 409), (path, response.status_code, response.get_data(as_text=True)[:500])
    if response.status_code == 200:
        assert response.get_data(as_text=True), (path, 'empty HTTP 200 response')
print('Application pages and Preview 48 device access: OK')
PY
  rm -rf "$test_root"
}

saved_https_access() {
  (( UPDATE_MODE == 1 )) || return 0

  python3 - \
    "$DATA_DIR/security/tls-state.json" \
    /etc/nginx/sites-available/sg-gateway \
    "$PANEL_PORT" <<'PYHTTPSSTATE'
import json
import re
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
nginx_path = Path(sys.argv[2])
panel_port = int(sys.argv[3])

if not state_path.is_file() or not nginx_path.is_file():
    raise SystemExit(0)
try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except (OSError, ValueError, json.JSONDecodeError):
    raise SystemExit(0)

if not state.get("https_ready"):
    raise SystemExit(0)
domain = str(state.get("domain") or "").strip().lower()
certificate_path = str(state.get("certificate_path") or "").strip()
key_path = str(state.get("key_path") or "").strip()
try:
    public_port = int(state.get("public_port") or state.get("panel_port") or 0)
except (TypeError, ValueError):
    public_port = 0
if public_port != panel_port:
    raise SystemExit(0)
if not domain or not Path(certificate_path).is_file() or not Path(key_path).is_file():
    raise SystemExit(0)

body = nginx_path.read_text(encoding="utf-8")
listen_pattern = re.compile(rf"(?m)^\\s*listen\\s+(?:\\[::\\]:)?{panel_port}\\s+ssl(?:\\s+[^;]+)?;")
checks = (
    listen_pattern.search(body),
    re.search(rf"(?m)^\\s*server_name\\s+{re.escape(domain)}(?:\\s+[^;]+)?;", body),
    re.search(rf"(?m)^\\s*ssl_certificate\\s+{re.escape(certificate_path)};", body),
    re.search(rf"(?m)^\\s*ssl_certificate_key\\s+{re.escape(key_path)};", body),
)
if all(checks):
    print(domain)
PYHTTPSSTATE
}

ensure_full_restore_upload_nginx() {
  # SG_GATEWAY_02111_CUMULATIVE_FULL_RESTORE_UPLOAD_FIX
  # Clean installs and upgrades must both accept the .sgbackup upload before
  # the request can reach Flask.  HTTPS refresh also carries the same rule in
  # deploy/configure-panel-access.sh, while HostD repairs it after restore.
  python3 - /etc/nginx/sites-available/sg-gateway "${BACKEND_PORT}" <<'PYFULLUPLOAD'
from pathlib import Path
import sys

path = Path(sys.argv[1])
backend_port = str(sys.argv[2])
marker = "SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1"
if not path.is_file():
    raise SystemExit(f"Nginx site not found: {path}")
body = path.read_text(encoding="utf-8")
if marker in body:
    raise SystemExit(0)

lines = body.splitlines(keepends=True)
candidates = []
for i, line in enumerate(lines):
    if line.strip() != "location / {":
        continue
    indent = line[: len(line) - len(line.lstrip())]
    j = i + 1
    while j < len(lines):
        if lines[j].startswith(indent) and lines[j].strip() == "}":
            break
        j += 1
    if j >= len(lines):
        continue
    block = "".join(lines[i : j + 1])
    if f"proxy_pass http://127.0.0.1:{backend_port};" in block:
        candidates.append((i, indent, block))

if len(candidates) != 1:
    raise SystemExit(
        f"Nginx Full Restore proxy location is ambiguous: {len(candidates)}"
    )
index, indent, existing = candidates[0]
if "proxy_set_header X-Forwarded-Proto https;" in existing:
    forwarded_proto = "https"
elif "proxy_set_header X-Forwarded-Proto http;" in existing:
    forwarded_proto = "http"
else:
    forwarded_proto = "$scheme"

block = (
    f"{indent}# {marker}\n"
    f"{indent}location = /maintenance/full-backups/restore {{\n"
    f"{indent}    client_max_body_size 0;\n"
    f"{indent}    client_body_timeout 300s;\n"
    f"{indent}    proxy_pass http://127.0.0.1:{backend_port};\n"
    f"{indent}    proxy_http_version 1.1;\n"
    f"{indent}    proxy_set_header Host $host;\n"
    f"{indent}    proxy_set_header X-Real-IP $remote_addr;\n"
    f"{indent}    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    f"{indent}    proxy_set_header X-Forwarded-Proto {forwarded_proto};\n"
    f"{indent}    proxy_read_timeout 300s;\n"
    f"{indent}    proxy_send_timeout 300s;\n"
    f"{indent}}}\n\n"
)
lines.insert(index, block)
path.write_text("".join(lines), encoding="utf-8", newline="\n")
PYFULLUPLOAD
}

stage_systemd_units() {
  # Old layered installers left overrides here. They must not survive a full install.
  rm -rf /etc/systemd/system/sg-hostd.service.d
  cat > /etc/systemd/system/sg-hostd.service <<EOF
[Unit]
Description=SG-Gateway privileged host helper
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${PREFIX}/hostd
EnvironmentFile=${CONFIG_DIR}/sg-gateway.env
EnvironmentFile=${CONFIG_DIR}/runtime.env
EnvironmentFile=${CONFIG_DIR}/engine-secrets.env
Environment=PYTHONPATH=${PREFIX}:${PREFIX}/hostd
ExecStart=${PREFIX}/.venv/bin/waitress-serve --host=127.0.0.1 --port=${HOSTD_PORT} sg_hostd.app:app
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
RuntimeDirectory=sg-gateway
RuntimeDirectoryMode=0755
ReadWritePaths=-/run/sg-gateway -${DATA_DIR} -${LOG_DIR} -${CONFIG_DIR} -/etc/mihomo -/var/lib/mihomo -/etc/sing-box -/var/lib/sing-box -/var/log/sing-box -/usr/local/etc/xray -/usr/local/share/xray -/etc/amnezia -/etc/sysctl.d -/etc/nginx -/etc/letsencrypt -/var/www/sg-gateway-acme -/var/www/sg-gateway-placeholder -/etc/systemd/system/sg-gateway.service.d

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/sg-gateway.service <<EOF
[Unit]
Description=SG-Gateway panel
After=network-online.target sg-hostd.service
Wants=network-online.target sg-hostd.service

[Service]
Type=simple
User=${PANEL_USER}
Group=${PANEL_GROUP}
WorkingDirectory=${PREFIX}
EnvironmentFile=${CONFIG_DIR}/sg-gateway.env
ExecStart=${PREFIX}/.venv/bin/waitress-serve --host=\${SG_GATEWAY_HOST} --port=\${SG_GATEWAY_PORT} app.production:app
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF

  install -m 0644 "$PREFIX/deploy/sg-gateway-awg.service" /etc/systemd/system/sg-gateway-awg.service
  install -m 0644 "$PREFIX/deploy/sg-gateway-singbox.service" /etc/systemd/system/sg-gateway-singbox.service
  install -m 0644 "$PREFIX/deploy/mihomo.service" /etc/systemd/system/mihomo.service

  install -d -m 0755 /etc/nginx/stream-conf.d /etc/nginx/sites-available /etc/nginx/sites-enabled
  local https_domain=""
  https_domain="$(saved_https_access)"
  if [[ -n "$https_domain" ]]; then
    echo "Сохраняю рабочий HTTPS для $https_domain до финальной проверки."
  else
  python3 - /etc/nginx/nginx.conf <<'PYNGINXMAIN'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
body = path.read_text(encoding="utf-8")
direct = "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;"
include_pattern = re.compile(
    r"(?m)^\s*include\s+/etc/nginx/stream-conf\.d/(?:\*\.conf|sg-gateway-443\.conf);\s*$"
)

# The accepted live nginx.conf already includes sg-gateway-443.conf directly.
# Adding a wildcard too would load the same file twice and duplicate port 443.
existing = include_pattern.findall(body)
if len(existing) > 1:
    kept = False
    lines = []
    for line in body.splitlines():
        if include_pattern.fullmatch(line):
            if kept:
                continue
            line = direct
            kept = True
        lines.append(line)
    body = "\n".join(lines) + ("\n" if body.endswith("\n") else "")
elif not existing:
    if "stream {" in body:
        pos = body.index("stream {") + len("stream {")
        body = body[:pos] + "\n" + direct + body[pos:]
    else:
        body = body.rstrip() + "\n\n# SG_GATEWAY_PLACEHOLDER_80_443_V3\nstream {\n" + direct + "\n}\n"

path.write_text(body, encoding="utf-8", newline="\n")
PYNGINXMAIN

  cat > /etc/nginx/stream-conf.d/sg-gateway-443.conf <<EOF
# SG_GATEWAY_PLACEHOLDER_80_443_V3
# Before a certificate exists, unknown SNI remains on the Reality listener.
map \$ssl_preread_server_name \$sg_gateway_443_backend {
    hostnames;
    ${REALITY_SNI} 127.0.0.1:${REALITY_INTERNAL_PORT};
    default 127.0.0.1:${REALITY_INTERNAL_PORT};
}

server {
    listen 443;
    listen [::]:443;
    proxy_pass \$sg_gateway_443_backend;
    ssl_preread on;
    proxy_connect_timeout 10s;
    proxy_timeout 1h;
}
EOF

  cat > /etc/nginx/sites-available/sg-gateway <<EOF
# SG_GATEWAY_PLACEHOLDER_80_443_V3
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root /var/www/sg-gateway-placeholder;
    index index.html;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/sg-gateway-acme;
        default_type text/plain;
    }

    location = / {
        try_files /index.html =404;
        add_header Cache-Control "no-cache" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }

    location = /index.html {
        try_files /index.html =404;
        add_header Cache-Control "no-cache" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    }

    location / {
        return 404;
    }
}

server {
    listen ${PANEL_PORT};
    listen [::]:${PANEL_PORT};
    server_name _;

    # SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX
    error_page 502 503 504 =200 /__sg_gateway_restarting;
    location = /__sg_gateway_restarting {
        internal;
        root /var/www/sg-gateway-placeholder;
        try_files /restarting.html =502;
        default_type text/html;
        add_header Cache-Control "no-store" always;
    }

    # SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1
    location = /maintenance/full-backups/restore {
        client_max_body_size 0;
        client_body_timeout 300s;
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
}
EOF
  rm -f /etc/nginx/sites-enabled/default \
    /etc/nginx/sites-enabled/sg-gateway \
    /etc/nginx/sites-enabled/sg-gateway-acme
  ln -s /etc/nginx/sites-available/sg-gateway /etc/nginx/sites-enabled/sg-gateway
  nginx -t
  systemctl reload nginx.service
  fi
  ensure_full_restore_upload_nginx
  nginx -t
  systemctl reload nginx.service
  systemctl daemon-reload
  [[ "$(systemctl show -p User --value sg-hostd.service)" == "root" ]]
  [[ -z "$(systemctl show -p DropInPaths --value sg-hostd.service)" ]]
  if (( UPDATE_MODE == 0 )); then
    systemctl disable sg-gateway-awg.service sg-gateway-singbox.service >/dev/null 2>&1 || true
    systemctl enable --now mihomo.service
    systemctl is-active --quiet mihomo.service
  fi
}

stage_firewall_and_network() {
  local ufw_state=""
  ufw_state="$(ufw status 2>/dev/null || true)"
  if grep -q '^Status: active' <<<"$ufw_state"; then
    local rule
    for rule in \
      "${PANEL_PORT}/tcp" "80/tcp" "${XRAY_PORT}/tcp" \
      "${XHTTP_REALITY_PORT}/tcp" "${XHTTP_TLS_PORT}/tcp" \
      "${AWG_PORT}/udp" "${HYSTERIA2_PORT}/udp" \
      "${MIHOMO_PORT}/tcp" "${ANYTLS_PORT}/tcp" "${TUIC_PORT}/udp"; do
      ufw allow "$rule"
    done
  fi
}

systemctl_with_retry() {
  # SG_GATEWAY_02110_SYSTEMD_TRANSIENT_RETRY_FIX3
  # Package operations can briefly disconnect systemctl from PID 1 / D-Bus.
  # Retry only the systemctl operation; a real service failure still propagates
  # after the bounded attempts and triggers the normal transactional rollback.
  local max_attempts="${SG_GATEWAY_SYSTEMCTL_RETRY_ATTEMPTS:-5}"
  local retry_delay="${SG_GATEWAY_SYSTEMCTL_RETRY_DELAY:-2}"
  local attempt=1 rc=1
  while (( attempt <= max_attempts )); do
    if systemctl "$@"; then
      return 0
    else
      rc=$?
    fi
    printf '[SG-Gateway] systemctl attempt %s/%s failed (rc=%s): systemctl' \
      "$attempt" "$max_attempts" "$rc" >> "$INSTALL_LOG"
    printf ' %q' "$@" >> "$INSTALL_LOG"
    printf '\\n' >> "$INSTALL_LOG"
    if (( attempt < max_attempts )); then
      systemctl daemon-reload >>"$INSTALL_LOG" 2>&1 || true
      sleep "$retry_delay"
    fi
    attempt=$((attempt + 1))
  done
  return "$rc"
}

http_wait_json() {
  local url="$1"
  local expected_service="$2"
  local attempts="${3:-60}"
  local body code attempt
  for attempt in $(seq 1 "$attempts"); do
    body="$(mktemp)"
    code="$(curl -sS --max-time 5 -o "$body" -w '%{http_code}' "$url" 2>>"$INSTALL_LOG" || true)"
    if [[ "$code" == "200" ]] && python3 - "$body" "$expected_service" <<'PY'
import json, sys
path, expected = sys.argv[1:]
try:
    value = json.load(open(path, encoding="utf-8"))
except Exception:
    raise SystemExit(1)
if value.get("service") != expected:
    raise SystemExit(1)
if value.get("status") not in {"ok", "warning"}:
    raise SystemExit(1)
PY
    then
      rm -f "$body"
      return 0
    fi
    if [[ -s "$body" && "$code" != "000" ]]; then
      {
        echo "Health attempt $attempt: HTTP $code from $url"
        head -c 1000 "$body"; echo
      } >> "$INSTALL_LOG"
    fi
    rm -f "$body"
    sleep 2
  done
  return 1
}

stage9_start_hostd() {
  verify_xray_version
  systemctl_with_retry enable --now sg-hostd.service
  http_wait_json "http://127.0.0.1:${HOSTD_PORT}/health" "sg-hostd" 20
}

stage9_verify_hostd() {
  local commands_file
  commands_file="$(mktemp)"
  curl -fsS --max-time 8 "http://127.0.0.1:${HOSTD_PORT}/commands" -o "$commands_file"
  python3 - "$commands_file" <<'PYHOSTDCMDS'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
commands = set(value.get("commands", []))
required = {"clients.apply", "tls.issue.start", "xray.apply", "xray.apply.start", "xray.test", "xray.rollback", "warp.install", "warp.test", "warp.export_json"}
missing = sorted(required - commands)
if missing:
    raise SystemExit("Missing hostd commands: " + ", ".join(missing))
print("hostd commands: OK")
PYHOSTDCMDS
  rm -f "$commands_file"
}

stage9_apply_runtime() {
  # A panel update must not rebuild a working Xray runtime merely because the
  # UI/source changed.  Preview 39 already has a real tested config; preserve
  # it, validate it with the installed Xray, and start it unchanged.  The new
  # managed Routing is applied transactionally later when the administrator
  # explicitly presses Apply or changes a client deployment.
  if (( UPDATE_MODE == 1 )) && [[ -s /usr/local/etc/xray/config.json ]]; then
    local current_test_log
    current_test_log="$(mktemp)"
    if XRAY_LOCATION_ASSET=/usr/local/share/xray /usr/local/bin/xray run -test \
      -config /usr/local/etc/xray/config.json >"$current_test_log" 2>&1; then
      cat "$current_test_log"
      rm -f "$current_test_log"
      set_xray_config_permissions
      systemctl_with_retry enable xray.service
      systemctl_with_retry restart xray.service
      systemctl is-active --quiet xray.service
      echo "Xray update policy: existing tested runtime preserved and restarted"
      return 0
    fi
    echo "Existing Xray config did not pass the new binary test; falling back to generated candidate:" >&2
    cat "$current_test_log" >&2 || true
    rm -f "$current_test_log"
  fi

  local xray_apply_file xray_apply_code
  xray_apply_file="$(mktemp)"
  xray_apply_code="$(curl -sS --max-time 120 -X POST \
    "http://127.0.0.1:${HOSTD_PORT}/commands/xray.apply" \
    -o "$xray_apply_file" -w '%{http_code}')"
  python3 - "$xray_apply_file" "$xray_apply_code" <<'PYXRAYAPPLY'
import json, sys
path, http_code = sys.argv[1:]
body = open(path, encoding="utf-8", errors="replace").read().strip()
try:
    value = json.loads(body or "{}")
except Exception:
    raise SystemExit(
        f"sg-hostd xray.apply returned HTTP {http_code}: "
        + (body or "empty response")
    )
if http_code != "200" or value.get("status") != "ok":
    raise SystemExit(
        (value.get("message") or f"sg-hostd xray.apply returned HTTP {http_code}")
        + (f"; response={body}" if body else "")
    )
print(value.get("message") or "Xray migration/apply: OK")
PYXRAYAPPLY
  rm -f "$xray_apply_file"

  # On a fresh installation apply the seeded catalogue once. Updates preserve
  # the already working optional runtimes and only ensure Xray is available.
  if (( UPDATE_MODE == 0 )); then
    local clients_apply_file clients_apply_code
    clients_apply_file="$(mktemp)"
    clients_apply_code="$(curl -sS --max-time 240 -X POST \
      "http://127.0.0.1:${HOSTD_PORT}/commands/clients.apply" \
      -o "$clients_apply_file" -w '%{http_code}')"
    python3 - "$clients_apply_file" "$clients_apply_code" <<'PYCLIENTSAPPLY'
import json, sys
path, http_code = sys.argv[1:]
body = open(path, encoding="utf-8", errors="replace").read().strip()
try:
    value = json.loads(body or "{}")
except Exception:
    raise SystemExit(
        f"sg-hostd clients.apply returned HTTP {http_code}: "
        + (body or "empty response")
    )
if http_code != "200" or value.get("status") != "ok":
    raise SystemExit(
        (value.get("message") or f"sg-hostd clients.apply returned HTTP {http_code}")
        + (f"; response={body}" if body else "")
    )
print(value.get("message") or "First client catalogue apply: OK")
PYCLIENTSAPPLY
    rm -f "$clients_apply_file"
  fi
}

stage9_ensure_warp() {
  local warp_file warp_code
  warp_file="$(mktemp)"
  warp_code="$(curl -sS --max-time 650 -X POST \
    "http://127.0.0.1:${HOSTD_PORT}/commands/warp.install" \
    -o "$warp_file" -w '%{http_code}')"
  python3 - "$warp_file" "$warp_code" <<'PYWARPAUTO'
import json, sys
path, http_code = sys.argv[1:]
body = open(path, encoding="utf-8", errors="replace").read().strip()
try:
    value = json.loads(body or "{}")
except Exception:
    raise SystemExit(
        f"sg-hostd warp.install returned HTTP {http_code}: " + (body or "empty response")
    )
if http_code != "200" or value.get("status") != "ok":
    raise SystemExit(value.get("message") or f"sg-hostd warp.install returned HTTP {http_code}")
print(value.get("message") or "WARP created and activated")
PYWARPAUTO
  rm -f "$warp_file"

  # WARP rebuilds the full Xray config. Keep the service-readable owner/mode
  # before the final restart and health checks.
  if [[ -s /usr/local/etc/xray/config.json ]]; then
    set_xray_config_permissions
    if ! systemctl restart xray.service; then
      systemctl_with_retry restart xray.service
    fi
    systemctl is-active --quiet xray.service
  fi
}

stage9_start_panel() {
  systemctl_with_retry enable --now sg-gateway.service
  http_wait_json "http://127.0.0.1:${BACKEND_PORT}/health" "sg-gateway-panel" 20
  curl -fsS --max-time 8 "http://127.0.0.1:${BACKEND_PORT}/login" >/dev/null
}

service_was_active_before_update() {
  local service="$1"
  [[ -f "$BACKUP_DIR/service-state.tsv" ]] || return 1
  awk -F '\t' -v target="$service" '$1 == target && $2 == "1" { found=1 } END { exit(found ? 0 : 1) }' \
    "$BACKUP_DIR/service-state.tsv"
}

service_was_enabled_before_update() {
  local service="$1"
  [[ -f "$BACKUP_DIR/service-state.tsv" ]] || return 1
  awk -F '\t' -v target="$service" '$1 == target && $3 == "1" { found=1 } END { exit(found ? 0 : 1) }' \
    "$BACKUP_DIR/service-state.tsv"
}

restore_update_runtime_services() {
  (( UPDATE_MODE == 1 )) || return 0
  local service
  for service in mihomo.service sg-gateway-awg.service sg-gateway-singbox.service; do
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

stage9_verify_nginx() {
  restore_update_runtime_services
  local https_domain=""
  https_domain="$(saved_https_access)"
  if [[ -n "$https_domain" ]]; then
    /bin/bash "$PREFIX/deploy/configure-panel-access.sh" --mode refresh
    curl --noproxy '*' -kfsS --max-time 15       --resolve "${https_domain}:${PANEL_PORT}:127.0.0.1"       "https://${https_domain}:${PANEL_PORT}/health"       | python3 -c 'import json,sys; value=json.load(sys.stdin); assert value.get("service")=="sg-gateway-panel"'
    echo "HTTPS domain, certificate and Nginx config preserved: $https_domain"
  else
    nginx -t
    systemctl_with_retry enable --now nginx.service
    http_wait_json "http://127.0.0.1:${PANEL_PORT}/health" "sg-gateway-panel" 15
    curl -fsS --max-time 8 "http://127.0.0.1:${PANEL_PORT}/login" >/dev/null
  fi
  systemctl is-active --quiet sg-hostd.service
  systemctl is-active --quiet sg-gateway.service
  systemctl is-active --quiet nginx.service
  cmp -s /var/www/sg-gateway-placeholder/index.html "$PREFIX/assets/placeholder/index.html"
  curl --noproxy '*' -fsS --max-time 8 http://127.0.0.1/ -o /tmp/sg-gateway-placeholder-check.html
  cmp -s /tmp/sg-gateway-placeholder-check.html /var/www/sg-gateway-placeholder/index.html
  rm -f /tmp/sg-gateway-placeholder-check.html

  # SG_GATEWAY_02110_INSTALLER_SAFETY_FIX1
  # Never put a producer in front of grep -q while pipefail is enabled.
  # grep -q may close the pipe after the first match, giving nginx/ss SIGPIPE
  # (141) and turning a successful verification into a failed installation.
  local nginx_dump="" socket_dump=""
  nginx_dump="$(nginx -T 2>&1)"
  grep -Fq 'include /etc/nginx/stream-conf.d/sg-gateway-443.conf;' <<<"$nginx_dump"
  grep -Fq "${REALITY_SNI} 127.0.0.1:${REALITY_INTERNAL_PORT};" /etc/nginx/stream-conf.d/sg-gateway-443.conf
  socket_dump="$(ss -lntp 2>/dev/null)"
  grep -Eq '(^|[[:space:]])[^[:space:]]*:443[[:space:]].*nginx' <<<"$socket_dump"
  if [[ -s /usr/local/etc/xray/config.json ]]; then
    set_xray_config_permissions
    systemctl is-active --quiet xray.service
    python3 - /usr/local/etc/xray/config.json "$REALITY_INTERNAL_PORT" <<'PYXRAYLISTENER'
import json, sys
path, expected = sys.argv[1], int(sys.argv[2])
config = json.load(open(path, encoding="utf-8"))
inbound = next((item for item in config.get("inbounds", []) if item.get("tag") == "sg-vless-reality-tcp"), None)
assert inbound is not None, "Reality TCP inbound is missing"
assert inbound.get("listen") == "127.0.0.1", inbound.get("listen")
assert int(inbound.get("port", 0)) == expected, inbound.get("port")
print(f"Reality TCP internal listener: 127.0.0.1:{expected}")
PYXRAYLISTENER
    socket_dump="$(ss -lntp 2>/dev/null)"
    grep -Eq "127\.0\.0\.1:${REALITY_INTERNAL_PORT}[[:space:]].*xray" <<<"$socket_dump"
  fi
  if [[ -f /etc/mihomo/config.yaml ]]; then
    /usr/local/bin/mihomo -t -f /etc/mihomo/config.yaml >/dev/null
    systemctl is-active --quiet mihomo.service
  fi
  if [[ -f /etc/amnezia/amneziawg/awg0.conf ]]; then
    grep -Eq '^ListenPort[[:space:]]*=[[:space:]]*585[[:space:]]*$' /etc/amnezia/amneziawg/awg0.conf || {
      echo "AmneziaWG runtime does not listen on UDP 585" >&2
      return 1
    }
  fi
  verify_xray_version
}

run_final_stage() {
  CURRENT_STAGE="9"
  CURRENT_LABEL="Запуск и финальная проверка"
  local started=$SECONDS
  run_hidden "Этап 9/9 · 1/5 · Запуск sg-hostd" stage9_start_hostd
  run_hidden "Этап 9/9 · 2/5 · Проверка команд hostd" stage9_verify_hostd
  run_hidden "Этап 9/9 · 3/5 · Сохранение/применение Xray runtime" stage9_apply_runtime
  run_hidden "Этап 9/9 · 4/5 · Запуск панели" stage9_start_panel
  run_hidden "Этап 9/9 · 5/5 · Проверка Nginx и служб" stage9_verify_nginx
  local elapsed=$((SECONDS - started))
  printf "%s[OK]%s Этап 9/%s · Запуск и финальная проверка (%s сек.)\n" \
    "$GREEN" "$RESET" "$TOTAL_STAGES" "$elapsed"
}


verify_client_identities_after_update() {
  (( UPDATE_MODE == 1 )) || return 0
  local before="$BACKUP_DIR/client-identities-before.sha256" after
  [[ -f "$before" ]] || return 0
  after="$(mktemp)"
  fingerprint_clients "$DATA_DIR/sg-gateway.sqlite" "$after"
  if ! cmp -s "$before" "$after"; then
    echo "Client identity fingerprint changed during update" >&2
    echo "before=$(cat "$before") after=$(cat "$after")" >> "$INSTALL_LOG"
    rm -f "$after"
    return 1
  fi
  rm -f "$after"
  echo "Clients identities: unchanged"
}

print_sg_admin_status() {
  printf '[SG-Gateway] Профили sg-admin: Reality TCP, XHTTP Reality, AmneziaWG, Mieru\n'
  [[ "$CREATE_SG_ADMIN" == "1" ]] || return 0
  printf '[SG-Gateway] Первый клиент sg-admin: создан\n'
  printf '[SG-Gateway] Профили: Clients → sg-admin\n'
}

main() {
  require_root
  # Start from a known-safe installation mask. Secret files below are still
  # created with explicit 0600/0640 modes or inside a scoped umask 077 block.
  # This prevents any restrictive umask inherited through sudo/SSH from
  # making application or virtualenv directories inaccessible to sg-gateway.
  umask 022
  prepare_log
  export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
  printf '\n%s[SG-Gateway]%s Запускаю полный мастер SG-Gateway 0.1.0-021.12\n' "$CYAN" "$RESET"
  printf '%s[SG-Gateway] [OK]%s Мастер установки SG-Gateway 0.1.0-021.12 запущен (0 сек.)\n' "$GREEN" "$RESET"
  printf '[SG-Gateway] Технический журнал: %s\n' "$INSTALL_LOG"
  printf '[SG-Gateway] Повторный запуск выполняется на этом же EC2. Домен не обязателен.\n\n'

  run_stage 1 "Подготовка Ubuntu" bootstrap_packages
  # Fail before any server mutation if our own pinned installation media is
  # missing or damaged. This is the key reproducibility guarantee of 021.
  verify_vendor_core_set
  if detect_existing_install; then
    printf '[SG-Gateway] Обнаружена установленная полная панель %s. Выполняется безопасное обновление.\n\n' \
      "${EXISTING_VERSION:-неизвестной версии}"
    if (( SERVER_NAME_MIGRATION_REQUIRED == 1 )); then
      SERVER_NAME="sg-gateway"
      [[ "$COUNTRY_CODE" != "unknown" ]] && SERVER_NAME="sg-gateway-${COUNTRY_CODE}"
      SERVER_NAME="$(normalize_hostname "$SERVER_NAME")"
      valid_hostname "$SERVER_NAME" || SERVER_NAME="sg-gateway"
      printf '[SG-Gateway] Имя сервера автоматически нормализовано: %s
' "$SERVER_NAME"
    fi
    printf '[SG-Gateway] Все параметры приняты. Дальнейшее обновление не потребует ввода.\n\n'
  elif detect_minimal_013_install; then
    printf '[SG-Gateway] Обнаружена рабочая база SG-Gateway 013.\n'
    printf '[SG-Gateway] Восстанавливаю полный активный UI и сохраняю подтверждённые Xray Reality/ML-KEM ключи.\n'
    printf '[SG-Gateway] Панель будет доступна на TCP %s. Логин и пароль SG-Gateway 013 сохраняются.\n\n' "$PANEL_PORT"
    printf '[SG-Gateway] Все параметры приняты. Дополнительных вопросов не будет.\n\n'
  else
    if [[ -f "$RESUME_FILE" ]]; then
      printf '[SG-Gateway] Повторный запуск выполняется на этом же EC2; использую сохранённые автоматические параметры.
'
    fi
    if ! load_resume_state; then
      collect_automatic_parameters
      save_resume_state
    fi
    printf '\n[SG-Gateway] Основная установка начинается. Дополнительных вопросов не будет.\n\n'
  fi

  # AmneziaWG has one canonical SG-Gateway transport port.
  AWG_PORT="$DEFAULT_AWG_PORT"

  BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)-before-sg-gateway-021"
  MUTATION_STARTED=1
  run_stage 2 "Резервная копия и подготовка исходника" stage_backup_and_prepare
  run_stage 3 "Системные пакеты, Nginx и Certbot" stage_system_packages
  run_stage 4 "Xray, AmneziaWG, Mihomo, sing-box и WARP helper" stage_engine_runtimes
  run_stage 5 "Python-окружение и проверка исходника" stage_python_and_source_check
  run_stage 6 "Полный UI, база и сохранение Xray 013" stage_configuration_and_database
  run_stage 7 "Локальная проверка страниц" stage_local_application_smoke_test
  run_stage 8 "Создание systemd-служб" stage_systemd_units
  run_stage 9 "Firewall и сетевые порты" stage_firewall_and_network

  CURRENT_STAGE="10"
  CURRENT_LABEL="Запуск и финальная проверка"
  run_quiet "Этап 10/10 · Запуск sg-hostd" stage9_start_hostd
  run_quiet "Этап 10/10 · Проверка команд hostd" stage9_verify_hostd
  run_quiet "Этап 10/10 · Применение подтверждённого Xray и клиентов" stage9_apply_runtime
  run_quiet "Этап 10/10 · Запуск панели" stage9_start_panel
  run_quiet "Этап 10/10 · Проверка Nginx и служб" stage9_verify_nginx
  run_quiet "Этап 10/10 · Контроль неизменности Clients" verify_client_identities_after_update

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
  printf '%s[SG-Gateway] ============================================================%s\n' "$GREEN" "$RESET"
  printf '[SG-Gateway] Имя сервера:  %s\n' "$SERVER_NAME"
  printf '[SG-Gateway] Страна:       %s\n' "${COUNTRY_CODE^^}"
  printf '[SG-Gateway] Публичный IP: %s\n' "$PUBLIC_ADDRESS"
  printf '[SG-Gateway] Версия:       %s\n' "$VERSION"
  printf '[SG-Gateway] Xray:         %s\n' "$(xray_installed_version)"
  local final_https_domain=""
  final_https_domain="$(saved_https_access)"
  if [[ -n "$final_https_domain" ]]; then
    printf '[SG-Gateway] Панель:       https://%s:%s\n' "$final_https_domain" "$PANEL_PORT"
    printf '[SG-Gateway] Заглушка:     http://%s/ и https://%s/\n' "$final_https_domain" "$final_https_domain"
  else
    printf '[SG-Gateway] Панель:       http://%s:%s\n' "$PUBLIC_ADDRESS" "$PANEL_PORT"
    printf '[SG-Gateway] Заглушка:     http://%s/\n' "$PUBLIC_ADDRESS"
  fi
  printf '[SG-Gateway] Reality TCP:  %s:%s -> 127.0.0.1:%s\n' "$PUBLIC_ADDRESS" "$XRAY_PORT" "$REALITY_INTERNAL_PORT"
  printf '[SG-Gateway] Логин:        admin\n'
  printf '[SG-Gateway] Журнал:       %s\n' "$INSTALL_LOG"
  printf '[SG-Gateway] Backup:       %s\n' "$BACKUP_DIR"
  printf '[SG-Gateway] SSH hostname станет виден после нового подключения: %s\n' "$SERVER_NAME"
  print_sg_admin_status
  if [[ -s "$DATA_DIR/warp/wgcf.xray.json" || -s "$DATA_DIR/warp/wgcf-profile.conf" ]]; then
    printf '[SG-Gateway] WARP:         существующий профиль сохранён\n'
  else
    printf '[SG-Gateway] WARP:         helper установлен; создаётся при необходимости в Outbounds\n'
  fi

}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
