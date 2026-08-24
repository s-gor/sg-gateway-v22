#!/usr/bin/env bash
set -Eeuo pipefail

# SG_GATEWAY_02206_AWG3_RUNTIME_REPAIR_V2
PREFIX="/opt/sg-gateway"
AWG3_ROOT="$PREFIX/awg3"
DEPLOY_DIR="$PREFIX/deploy"
VENDOR_DIR="$PREFIX/vendor/cores"
HELPER="$DEPLOY_DIR/sg-gateway-awg3-userspace.sh"
UNIT_SOURCE="$DEPLOY_DIR/sg-gateway-awg3.service"
UNIT_TARGET="/etc/systemd/system/sg-gateway-awg3.service"
CONFIG="/etc/amnezia/amneziawg/awg3.conf"
DATABASE="/var/lib/sg-gateway/sg-gateway.sqlite"
PYTHON="$PREFIX/.venv/bin/python"
SERVICE="sg-gateway-awg3.service"
VENDOR_COMMIT="91cb614060edc9491b9f5178475089b443e63687"
TOOLS_FILE="amneziawg-tools-3.1.20260812.tar.gz"
GO_FILE="amneziawg-go-linux-amd64-v3.1.20260814"
TOOLS_SHA256="f18592c499c893b1b87b15de9e707ce265585cf2536698975b6ede8156d14ada"
GO_SHA256="375bc2645df09498aa30215e3b3a09a97626a8e929f409e0edef6564fb8e3110"
RAW_BASE="https://raw.githubusercontent.com/s-gor/sg-gateway-v22/${VENDOR_COMMIT}/vendor/cores"
TMP=""
STAGE_ROOT="$PREFIX/.awg3-repair-new.$$"
BACKUP_ROOT="$PREFIX/.awg3-repair-old.$$"
UNIT_BACKUP=""
HAD_RUNTIME=0
HAD_UNIT=0
WAS_ACTIVE=0
WAS_ENABLED=0
ACTIVE_CLIENTS=0
MUTATED=0
SWAPPED=0
SUCCESS=0

log() { printf '[SG-Gateway AWG3 Repair] %s\n' "$*"; }

cleanup() {
  local rc=$?
  set +e
  if (( SUCCESS == 0 && MUTATED == 1 )); then
    log "Repair не завершён. Возвращаю предыдущий AWG3 runtime."
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    if (( SWAPPED == 1 )); then
      rm -rf -- "$AWG3_ROOT"
      if (( HAD_RUNTIME == 1 )) && [[ -e "$BACKUP_ROOT" ]]; then
        mv -- "$BACKUP_ROOT" "$AWG3_ROOT" || true
      fi
    fi
    if (( HAD_UNIT == 1 )) && [[ -n "$UNIT_BACKUP" && -f "$UNIT_BACKUP" ]]; then
      cp -a -- "$UNIT_BACKUP" "$UNIT_TARGET" || true
    elif (( HAD_UNIT == 0 )); then
      rm -f -- "$UNIT_TARGET"
    fi
    systemctl daemon-reload >/dev/null 2>&1 || true
    if (( WAS_ENABLED == 1 )); then
      systemctl enable "$SERVICE" >/dev/null 2>&1 || true
    else
      systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    fi
    if (( WAS_ACTIVE == 1 )); then
      systemctl restart "$SERVICE" >/dev/null 2>&1 || true
    else
      systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    fi
  fi
  rm -rf -- "$STAGE_ROOT" "$TMP"
  if (( SUCCESS == 1 )); then
    rm -rf -- "$BACKUP_ROOT"
  fi
  exit "$rc"
}
trap cleanup EXIT

[[ "$(id -u)" -eq 0 ]] || { echo "Запустите восстановление через sudo." >&2; exit 1; }
for command in tar make cc pkg-config sha256sum find install cp mv systemctl; do
  command -v "$command" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $command" >&2; exit 1; }
done
[[ -x "$PYTHON" ]] || { echo "Не найден Python runtime SG-Gateway" >&2; exit 1; }
[[ -f "$DATABASE" ]] || { echo "Не найдена база SG-Gateway: $DATABASE" >&2; exit 1; }
[[ -f "$HELPER" ]] || { echo "Не найден AWG3 helper текущей SG-Gateway: $HELPER" >&2; exit 1; }
[[ -f "$UNIT_SOURCE" ]] || { echo "Не найден шаблон AWG3 service текущей SG-Gateway: $UNIT_SOURCE" >&2; exit 1; }

systemctl is-active --quiet "$SERVICE" >/dev/null 2>&1 && WAS_ACTIVE=1 || true
systemctl is-enabled --quiet "$SERVICE" >/dev/null 2>&1 && WAS_ENABLED=1 || true
[[ -e "$AWG3_ROOT" ]] && HAD_RUNTIME=1 || true
[[ -f "$UNIT_TARGET" ]] && HAD_UNIT=1 || true

ACTIVE_CLIENTS="$($PYTHON - "$DATABASE" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
try:
    row = db.execute(
        """
        SELECT COUNT(*)
        FROM device_credentials dc
        JOIN devices d ON d.id = dc.device_id
        JOIN clients c ON c.id = d.client_id
        WHERE dc.engine = 'amneziawg3'
          AND dc.status != 'disabled'
          AND c.enabled = 1
          AND d.enabled = 1
        """
    ).fetchone()
finally:
    db.close()
print(int(row[0] if row else 0))
PY
)"
[[ "$ACTIVE_CLIENTS" =~ ^[0-9]+$ ]] || { echo "Не удалось определить активные AWG3-клиенты" >&2; exit 1; }

TMP="$(mktemp -d /tmp/sg-gateway-awg3-repair.XXXXXX)"
install -d -m 0755 "$STAGE_ROOT/bin"
if (( HAD_UNIT == 1 )); then
  UNIT_BACKUP="$TMP/sg-gateway-awg3.service.previous"
  cp -a -- "$UNIT_TARGET" "$UNIT_BACKUP"
fi

stage_vendor_file() {
  local name="$1" digest="$2" source="$VENDOR_DIR/$1" target="$TMP/$1"
  if [[ -f "$source" ]] && printf '%s  %s\n' "$digest" "$source" | sha256sum -c - >/dev/null 2>&1; then
    log "Использую локальный проверенный $name"
    cp -a -- "$source" "$target"
  else
    command -v curl >/dev/null 2>&1 || { echo "Локальный $name повреждён/отсутствует и curl недоступен" >&2; return 1; }
    log "Локальный $name недоступен — загружаю зафиксированную копию 22.04"
    curl -fL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 \
      "$RAW_BASE/$name" -o "$target"
  fi
  printf '%s  %s\n' "$digest" "$target" | sha256sum -c -
}

log "1/6 · Получаю зафиксированный AWG3 runtime"
stage_vendor_file "$TOOLS_FILE" "$TOOLS_SHA256"
stage_vendor_file "$GO_FILE" "$GO_SHA256"

log "2/6 · Собираю runtime в изолированном staging"
install -d -m 0755 "$TMP/tools"
tar -xzf "$TMP/$TOOLS_FILE" -C "$TMP/tools"
TOOLS_SRC="$(find "$TMP/tools" -maxdepth 1 -type d -name 'amneziawg-tools-*' -print -quit)"
[[ -n "$TOOLS_SRC" ]] || { echo "Не найден source directory AWG3 tools" >&2; exit 1; }
JOBS="$(nproc 2>/dev/null || echo 1)"
make -C "$TOOLS_SRC/src" PLATFORM=linux -j"$JOBS"
make -C "$TOOLS_SRC/src" \
  PLATFORM=linux WITH_WGQUICK=yes WITH_BASHCOMPLETION=no WITH_SYSTEMDUNITS=no \
  PREFIX="$STAGE_ROOT" SYSCONFDIR="$STAGE_ROOT/etc" install
install -m 0755 "$TMP/$GO_FILE" "$STAGE_ROOT/bin/amneziawg-go"

log "3/6 · Проверяю новый runtime до переключения"
for file in awg awg-quick amneziawg-go; do
  [[ -x "$STAGE_ROOT/bin/$file" ]] || { echo "Не создан $file" >&2; exit 1; }
done
"$STAGE_ROOT/bin/awg" --version
chown -R root:root "$STAGE_ROOT"
chmod -R a+rX "$STAGE_ROOT"

log "4/6 · Атомарно переключаю только AWG3 runtime"
MUTATED=1
systemctl stop "$SERVICE" >/dev/null 2>&1 || true
if (( HAD_RUNTIME == 1 )); then
  rm -rf -- "$BACKUP_ROOT"
  mv -- "$AWG3_ROOT" "$BACKUP_ROOT"
fi
mv -- "$STAGE_ROOT" "$AWG3_ROOT"
SWAPPED=1
chmod 0755 "$HELPER"
install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload

log "5/6 · Восстанавливаю только требуемое runtime-состояние"
if (( ACTIVE_CLIENTS > 0 )); then
  if [[ -s "$CONFIG" ]]; then
    systemctl enable "$SERVICE" >/dev/null
    systemctl restart "$SERVICE"
    systemctl is-active --quiet "$SERVICE"
    "$AWG3_ROOT/bin/awg" show awg3 >/dev/null
    log "AWG3 runtime запущен для активных клиентов: $ACTIVE_CLIENTS"
  else
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    systemctl disable "$SERVICE" >/dev/null 2>&1 || true
    log "AWG3 runtime восстановлен. Активные AWG3-клиенты есть, но generated-конфигурация отсутствует. Откройте Clients и нажмите «Проверить и применить»."
  fi
else
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  systemctl disable "$SERVICE" >/dev/null 2>&1 || true
  log "Активных AWG3-клиентов нет — runtime восстановлен, сервис оставлен выключенным"
fi

log "6/6 · Runtime Contract AWG3"
PYTHONPATH="$PREFIX:$PREFIX/hostd" "$PYTHON" - <<'PY'
from sg_hostd.runtime_contracts import DEFAULT_SPECS, inspect_runtime_contract

result = inspect_runtime_contract(
    specs={"amneziawg3": DEFAULT_SPECS["amneziawg3"]},
    include_all_critical=True,
    strict_optional=True,
)
if not result.get("ok"):
    raise SystemExit(result.get("message") or "AWG3 Runtime Contract failed")
print("AWG3 Runtime Contract: OK")
PY

SUCCESS=1
log "AWG3 RUNTIME REPAIR: OK"
