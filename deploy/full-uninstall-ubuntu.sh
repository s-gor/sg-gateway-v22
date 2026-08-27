#!/usr/bin/env bash
set -Eeuo pipefail

PREFIX="/opt/sg-gateway"
CONFIG_DIR="/etc/sg-gateway"
DATA_DIR="/var/lib/sg-gateway"
LOG_DIR="/var/log/sg-gateway"
UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02206.log"

PANEL_PORT="63443"
XRAY_PORT="443"
AWG_PORT="585"
AWG3_PORT="586"
AWG31_PORT="587"
MIHOMO_PORT="2099"
XHTTP_REALITY_PORT="8444"
XHTTP_TLS_PORT="8445"
HYSTERIA2_PORT="8446"
ANYTLS_PORT="9443"
TUIC_PORT="10443"
TLS_DOMAIN=""

GREEN=$'\033[1;32m'
RED=$'\033[1;31m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[1;36m'
RESET=$'\033[0m'
TOTAL_STAGES=7

fail(){ printf '%s[SG-Gateway] ОШИБКА:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "запустите деинсталлятор через sudo"
cd /

read_env_value(){
  local file="$1" key="$2" fallback="$3" value=""
  if [[ -f "$file" ]]; then
    value="$(awk -F= -v key="$key" '$1==key {sub(/^[^=]*=/,""); print; exit}' "$file" 2>/dev/null || true)"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
  fi
  printf '%s' "${value:-$fallback}"
}

RUNTIME_ENV="$CONFIG_DIR/runtime.env"
PANEL_PORT="$(read_env_value "$RUNTIME_ENV" SG_GATEWAY_PANEL_PORT "$PANEL_PORT")"
XRAY_PORT="$(read_env_value "$RUNTIME_ENV" SG_GATEWAY_XRAY_PORT "$XRAY_PORT")"
AWG_PORT="$(read_env_value "$RUNTIME_ENV" SG_GATEWAY_AWG_PORT "$AWG_PORT")"
MIHOMO_PORT="$(read_env_value "$RUNTIME_ENV" SG_GATEWAY_MIHOMO_PORT "$MIHOMO_PORT")"

if [[ -f "$DATA_DIR/security/tls-state.json" ]] && command -v python3 >/dev/null 2>&1; then
  TLS_DOMAIN="$(python3 - "$DATA_DIR/security/tls-state.json" <<'PY' 2>/dev/null || true
import json, sys
try:
    value=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception:
    value={}
domain=str(value.get('domain') or '').strip().lower()
print(domain)
PY
)"
fi
if [[ ! "$TLS_DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]; then
  TLS_DOMAIN=""
fi

printf '\n%sSG-Gateway 0.1.0-022.06 · ПОЛНОЕ УДАЛЕНИЕ%s\n' "$CYAN" "$RESET"
printf 'Будут удалены приложение, база, настройки, backups, SG-службы и установленные SG runtime.\n'
printf 'Системные пакеты Ubuntu (nginx, certbot, ufw, Python и т.п.) останутся установленными.\n'
if [[ -n "$TLS_DOMAIN" ]]; then
  printf 'Также будет удалён сертификат Let\x27s Encrypt, принадлежащий SG-Gateway: %s\n' "$TLS_DOMAIN"
fi
printf '\nДля подтверждения введите точно: %sDELETE SG-GATEWAY%s\n' "$YELLOW" "$RESET"
read -r -p '> ' CONFIRM < /dev/tty
[[ "$CONFIRM" == "DELETE SG-GATEWAY" ]] || { echo "Удаление отменено."; exit 0; }

: > "$UNINSTALL_LOG"
chmod 0600 "$UNINSTALL_LOG"

spinner_loop(){
  local pid="$1" label="$2" frames=('|' '/' '-' '\\') index=0
  while kill -0 "$pid" 2>/dev/null; do
    printf '\r\033[K%s[%s]%s %s' "$GREEN" "${frames[$index]}" "$RESET" "$label"
    index=$(( (index + 1) % 4 )); sleep 0.12
  done
}

run_stage(){
  local stage="$1" label="$2" fn="$3" started=$SECONDS rc elapsed
  "$fn" >>"$UNINSTALL_LOG" 2>&1 & local pid=$!
  spinner_loop "$pid" "Этап ${stage}/${TOTAL_STAGES} · ${label}"
  set +e; wait "$pid"; rc=$?; set -e
  elapsed=$((SECONDS-started))
  if (( rc != 0 )); then
    printf '\r\033[K%s[ОШИБКА]%s Этап %s/%s · %s\n' "$RED" "$RESET" "$stage" "$TOTAL_STAGES" "$label"
    tail -n 80 "$UNINSTALL_LOG" || true
    exit "$rc"
  fi
  printf '\r\033[K%s[OK]%s Этап %s/%s · %s (%s сек.)\n' "$GREEN" "$RESET" "$stage" "$TOTAL_STAGES" "$label" "$elapsed"
}

stop_runtime(){
  local service
  for service in \
    sg-gateway.service sg-hostd.service xray.service mihomo.service \
    sg-gateway-awg.service sg-gateway-awg3.service sg-gateway-awg31.service sg-gateway-singbox.service; do
    systemctl disable --now "$service" >/dev/null 2>&1 || true
  done
  ip link delete awg0 >/dev/null 2>&1 || true
  ip link delete awg3 >/dev/null 2>&1 || true
  ip link delete awg31 >/dev/null 2>&1 || true
  rm -f /var/run/amneziawg/awg3.sock /var/run/amneziawg/awg31.sock >/dev/null 2>&1 || true
  if command -v nft >/dev/null 2>&1; then
    nft delete table ip sg_gateway_awg >/dev/null 2>&1 || true
    nft delete table ip sg_gateway_awg3 >/dev/null 2>&1 || true
    nft delete table ip sg_gateway_awg31 >/dev/null 2>&1 || true
  fi
}

remove_service_and_web_config(){
  rm -f \
    /etc/systemd/system/sg-gateway.service \
    /etc/systemd/system/sg-hostd.service \
    /etc/systemd/system/sg-gateway-awg.service \
    /etc/systemd/system/sg-gateway-awg3.service \
    /etc/systemd/system/sg-gateway-awg31.service \
    /etc/systemd/system/xray.service \
    /etc/systemd/system/xray@.service \
    /etc/systemd/system/mihomo.service \
    /etc/systemd/system/sg-gateway-awg.service \
    /etc/systemd/system/sg-gateway-awg3.service \
    /etc/systemd/system/sg-gateway-awg31.service \
    /etc/systemd/system/sg-gateway-singbox.service
  rm -rf \
    /etc/systemd/system/sg-gateway.service.d \
    /etc/systemd/system/sg-hostd.service.d \
    /etc/systemd/system/xray.service.d \
    /etc/systemd/system/xray@.service.d
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true

  rm -f \
    /etc/nginx/sites-enabled/sg-gateway \
    /etc/nginx/sites-available/sg-gateway \
    /etc/nginx/sites-enabled/sg-gateway-acme \
    /etc/nginx/sites-available/sg-gateway-acme \
    /etc/nginx/stream-conf.d/sg-gateway-443.conf \
    /etc/letsencrypt/renewal-hooks/deploy/sg-gateway-nginx \
    /etc/letsencrypt/renewal-hooks/deploy/reload-sg-gateway-nginx.sh
  rm -rf /var/www/sg-gateway-acme /var/www/sg-gateway-placeholder

  # Remove the exact SG-Gateway stream include. If SG-Gateway created its
  # own stream block, remove the whole block; inside a shared stream block,
  # remove only our include line.
  if [[ -f /etc/nginx/nginx.conf ]] && command -v python3 >/dev/null 2>&1; then
    python3 - /etc/nginx/nginx.conf <<'PYNGINXCLEAN'
from pathlib import Path
import re, sys
path = Path(sys.argv[1])
body = path.read_text(encoding="utf-8")
# Current direct include and the historical wildcard marker block.
body = re.sub(
    r"(?ms)\n*# SG_GATEWAY_PLACEHOLDER_80_443_V3\s*\nstream\s*\{\s*"
    r"include\s+/etc/nginx/stream-conf\.d/(?:sg-gateway-443\.conf|\*\.conf);\s*\}\s*",
    "\n",
    body,
    count=1,
)
body = re.sub(
    r"(?m)^\s*include\s+/etc/nginx/stream-conf\.d/sg-gateway-443\.conf;\s*\n?",
    "",
    body,
)
body = re.sub(
    r"(?m)^\s*# SG_GATEWAY_PLACEHOLDER_80_443_V3\s*\n?",
    "",
    body,
)
path.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")
PYNGINXCLEAN
  fi
  remove_service_and_web_config_finalize_nginx
}

check_nginx_after_sg_cleanup() {
  # SG_GATEWAY_02110_UNINSTALL_SAFETY_FIX2
  # A failed/partial older install can leave the nginx binary/package present
  # while /etc/nginx/nginx.conf is missing. Uninstall must not call nginx -t in
  # that state and must continue removing SG-Gateway. The optional path exists
  # only to make this exact guard regression-testable without touching /etc.
  local nginx_conf="${1:-/etc/nginx/nginx.conf}"
  if command -v nginx >/dev/null 2>&1 && [[ -f "$nginx_conf" ]]; then
    nginx -t
    systemctl reload nginx.service >/dev/null 2>&1 || true
  elif command -v nginx >/dev/null 2>&1; then
    echo "[SG-Gateway] Nginx установлен без ${nginx_conf}; nginx -t пропущен."
  fi
}

remove_service_and_web_config_finalize_nginx() {
  check_nginx_after_sg_cleanup /etc/nginx/nginx.conf
}

remove_sg_certificate(){
  [[ -n "$TLS_DOMAIN" ]] || return 0
  if command -v certbot >/dev/null 2>&1; then
    certbot delete --cert-name "$TLS_DOMAIN" --non-interactive >/dev/null 2>&1 || true
  fi
  # Exact-domain fallback only; never wipe the whole Let's Encrypt tree.
  if [[ "$TLS_DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]; then
    rm -f "/etc/letsencrypt/renewal/${TLS_DOMAIN}.conf"
    rm -rf "/etc/letsencrypt/live/${TLS_DOMAIN}" "/etc/letsencrypt/archive/${TLS_DOMAIN}"
  fi
  local remaining_cert=""
  if [[ -d /etc/letsencrypt/renewal ]]; then
    remaining_cert="$(find /etc/letsencrypt/renewal -maxdepth 1 -type f -name '*.conf' -print -quit 2>/dev/null || true)"
  fi
  if [[ -d /etc/letsencrypt/renewal && -z "$remaining_cert" ]]; then
    systemctl disable --now certbot.timer >/dev/null 2>&1 || true
  fi
}

remove_application_and_state(){
  rm -rf \
    "$PREFIX" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" \
    /root/sg-gateway-backups \
    /run/sg-gateway \
    /etc/mihomo /var/lib/mihomo \
    /etc/sing-box /var/lib/sing-box /var/log/sing-box \
    /etc/amnezia/amneziawg \
    /var/run/amneziawg
  rmdir /etc/amnezia >/dev/null 2>&1 || true
  rm -f \
    /etc/sysctl.d/99-sg-gateway.conf \
    /root/sg-gateway-021-installer-resume.env \
    /root/sg-gateway-02110-installer-resume.env \
    /root/sg-gateway-02111-installer-resume.env \
    /root/sg-gateway-02112-installer-resume.env \
    /root/sg-gateway-02206-installer-resume.env \
    /root/sg-gateway-preview48-installer-resume.env \
    /root/sg-gateway-preview50-installer-resume.env \
    /root/sg-gateway-preview51-installer-resume.env \
    /root/sg-gateway-preview52-installer-resume.env \
    /root/sg-gateway-preview53-installer-resume.env \
    /root/sg-gateway-019-installer-resume.env \
    /root/sg-gateway-020-installer-resume.env \
    /var/log/sg-gateway-installer-021.log \
    /var/log/sg-gateway-installer-02110.log \
    /var/log/sg-gateway-installer-02111.log \
    /var/log/sg-gateway-installer-02112.log \
    /var/log/sg-gateway-full-uninstall-02111.log
  rm -f /tmp/sg-gateway-installer-output.* /tmp/sg-gateway-installer-log.* >/dev/null 2>&1 || true
}

remove_engine_runtimes(){
  rm -rf /usr/local/etc/xray /usr/local/share/xray /var/log/xray
  rm -f /usr/local/bin/xray /usr/local/bin/mihomo /usr/local/bin/wgcf-cli

  if [[ -L /usr/bin/sing-box ]] && [[ "$(readlink -f /usr/bin/sing-box 2>/dev/null || true)" == "/usr/local/bin/sing-box" ]]; then
    rm -f /usr/bin/sing-box
  fi
  rm -f /usr/local/bin/sing-box
  rm -rf /usr/local/lib/sing-box
  apt-get -o Dpkg::Use-Pty=0 remove -y sing-box >/dev/null 2>&1 || true
  rm -f /etc/apt/sources.list.d/sagernet.sources /etc/apt/sources.list.d/sagernet.list /etc/apt/keyrings/sagernet.asc

  modprobe -r amneziawg >/dev/null 2>&1 || true
  if command -v dkms >/dev/null 2>&1; then
    dkms remove -m amneziawg -v 1.0.0 --all >/dev/null 2>&1 || true
  fi
  rm -rf /var/lib/dkms/amneziawg/1.0.0 /usr/src/amneziawg-1.0.0
  apt-get -o Dpkg::Use-Pty=0 purge -y amneziawg amneziawg-dkms amneziawg-tools >/dev/null 2>&1 || true

  # DKMS can lose its state while leaving a compiled SG module behind.
  # Remove orphaned amneziawg modules from every installed kernel so a
  # later Clean Install cannot accidentally reuse an AWG3/experimental ko.
  find /lib/modules -type f \
    \( -name 'amneziawg.ko' -o -name 'amneziawg.ko.*' \) \
    -path '*/updates/dkms/*' -delete

  rm -f /usr/bin/awg /usr/bin/awg-quick
  rm -f /usr/share/man/man8/awg.8 /usr/share/man/man8/awg.8.gz /usr/share/man/man8/awg-quick.8 /usr/share/man/man8/awg-quick.8.gz
  rm -f /usr/share/bash-completion/completions/awg /usr/share/bash-completion/completions/awg-quick
  rm -f /etc/apt/sources.list.d/amnezia-ubuntu-ppa-*.sources /etc/apt/sources.list.d/amnezia-ubuntu-ppa-*.list
  depmod -a >/dev/null 2>&1 || true
}

cleanup_firewall(){
  local ufw_state=""
  if command -v ufw >/dev/null 2>&1; then
    ufw_state="$(ufw status 2>/dev/null || true)"
  fi
  if grep -q '^Status: active' <<<"$ufw_state"; then
    local rule
    for rule in \
      "${PANEL_PORT}/tcp" "80/tcp" "${XRAY_PORT}/tcp" \
      "${XHTTP_REALITY_PORT}/tcp" "${XHTTP_TLS_PORT}/tcp" \
      "${AWG_PORT}/udp" "${AWG3_PORT}/udp" "${AWG31_PORT}/udp" "${HYSTERIA2_PORT}/udp" \
      "${MIHOMO_PORT}/tcp" "${ANYTLS_PORT}/tcp" "${TUIC_PORT}/udp"; do
      ufw --force delete allow "$rule" >/dev/null 2>&1 || true
    done
  fi
  sysctl --system >/dev/null 2>&1 || true
}

remove_account_and_verify(){
  if id sg-gateway >/dev/null 2>&1; then
    pkill -TERM -u sg-gateway >/dev/null 2>&1 || true
    sleep 1
    pkill -KILL -u sg-gateway >/dev/null 2>&1 || true
    userdel sg-gateway >/dev/null 2>&1 || true
  fi
  getent group sg-gateway >/dev/null 2>&1 && groupdel sg-gateway >/dev/null 2>&1 || true

  # userdel/NSS hooks may touch the former service home after the main
  # state-removal stage. Remove owned paths one final time before the
  # absence checks so Full Uninstall is deterministic and idempotent.
  rm -rf "$PREFIX" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" /run/sg-gateway

  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true

  local bad=0 path
  if id sg-gateway >/dev/null 2>&1; then
    echo "Остаток после удаления: пользователь sg-gateway" >&2
    bad=1
  fi
  if getent group sg-gateway >/dev/null 2>&1; then
    echo "Остаток после удаления: группа sg-gateway" >&2
    bad=1
  fi
  for path in \
    "$PREFIX" "$CONFIG_DIR" "$DATA_DIR" \
    /etc/systemd/system/sg-gateway.service \
    /etc/systemd/system/sg-hostd.service \
    /etc/systemd/system/sg-gateway-awg.service \
    /etc/systemd/system/sg-gateway-awg3.service \
    /etc/systemd/system/sg-gateway-awg31.service \
    /etc/systemd/system/xray.service \
    /etc/nginx/stream-conf.d/sg-gateway-443.conf \
    /var/www/sg-gateway-placeholder \
    /usr/local/bin/xray /usr/local/bin/mihomo /usr/local/bin/sing-box /usr/local/bin/wgcf-cli \
    /usr/bin/awg /usr/bin/awg-quick; do
    if [[ -e "$path" || -L "$path" ]]; then
      echo "Остаток после удаления: $path" >&2
      bad=1
    fi
  done
  if [[ -f /etc/nginx/nginx.conf ]] && grep -Eq '^\s*include\s+/etc/nginx/stream-conf\.d/sg-gateway-443\.conf;\s*$' /etc/nginx/nginx.conf; then
    echo "Остаток после удаления: include sg-gateway-443.conf в nginx.conf" >&2
    bad=1
  fi
  if [[ -e /root/sg-gateway-02110-installer-resume.env ]]; then
    echo "Остаток после удаления: /root/sg-gateway-02110-installer-resume.env" >&2
    bad=1
  fi
  if [[ -e /root/sg-gateway-02111-installer-resume.env ]]; then
    echo "Остаток после удаления: /root/sg-gateway-02111-installer-resume.env" >&2
    bad=1
  fi
  if [[ -e /root/sg-gateway-02206-installer-resume.env ]]; then
    echo "Остаток после удаления: /root/sg-gateway-02206-installer-resume.env" >&2
    bad=1
  fi
  (( bad == 0 )) || return 1
}

run_stage 1 "Остановка SG-служб и интерфейсов" stop_runtime
run_stage 2 "Удаление systemd/Nginx конфигурации" remove_service_and_web_config
run_stage 3 "Удаление сертификата SG-Gateway" remove_sg_certificate
run_stage 4 "Удаление приложения, базы, backups и состояния" remove_application_and_state
run_stage 5 "Удаление Xray/Mihomo/sing-box/WARP/AmneziaWG" remove_engine_runtimes
run_stage 6 "Очистка SG firewall/sysctl" cleanup_firewall
run_stage 7 "Удаление service account и проверка чистоты" remove_account_and_verify

printf '\n%s[SG-Gateway] ПОЛНОЕ УДАЛЕНИЕ ЗАВЕРШЕНО.%s\n' "$GREEN" "$RESET"
printf '[SG-Gateway] EC2 готов к чистой установке SG-Gateway.\n'
printf '[SG-Gateway] Системные пакеты Ubuntu не удалялись.\n'
printf '[SG-Gateway] Журнал: %s\n' "$UNINSTALL_LOG"
printf '\n[SG-Gateway] Для повторной установки SG-Gateway выполните:\n'
printf '%s\n' 'curl -fsSL https://raw.githubusercontent.com/s-gor/sg-gateway-v22/dev-02206/deploy/install-from-github.sh | sudo env SG_GATEWAY_ALLOW_DEVELOPMENT=1 SG_GATEWAY_GITHUB_BRANCH=dev-02206 bash'
