from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, body: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str, marker: str) -> None:
    body = read(path)
    if marker in body:
        return
    if old not in body:
        raise SystemExit(f"anchor not found in {path}: {old[:160]!r}")
    write(path, body.replace(old, new, 1))


REPAIR_SCRIPT = r'''#!/usr/bin/env bash
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
VENDOR_COMMIT="56df9a7b4fe509282e37374dd6ef3bccdc1b1100"
TOOLS_FILE="amneziawg-tools-3.0.20260805.tar.gz"
GO_FILE="amneziawg-go-linux-amd64-v3.0.0"
TOOLS_SHA256="090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19"
GO_SHA256="131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd"
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
for command in tar make sha256sum find install cp mv; do
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
  PREFIX="$STAGE_ROOT" install
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
  systemctl enable "$SERVICE" >/dev/null
  if [[ -s "$CONFIG" ]]; then
    systemctl restart "$SERVICE"
    systemctl is-active --quiet "$SERVICE"
    "$AWG3_ROOT/bin/awg" show awg3 >/dev/null
    log "AWG3 runtime запущен для активных клиентов: $ACTIVE_CLIENTS"
  else
    log "Активные AWG3-клиенты есть, но конфигурация отсутствует; runtime восстановлен, конфигурацию создаст штатный Client Apply"
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
'''
write("deploy/repair-awg3-runtime.sh", REPAIR_SCRIPT)

replace_once(
    "hostd/sg_hostd/operation_jobs.py",
    'PANEL_UPDATE_SCRIPT = Path("/opt/sg-gateway/deploy/update-from-github.sh")\n',
    'PANEL_UPDATE_SCRIPT = Path("/opt/sg-gateway/deploy/update-from-github.sh")\nAWG3_REPAIR_SCRIPT = Path("/opt/sg-gateway/deploy/repair-awg3-runtime.sh")\n',
    "AWG3_REPAIR_SCRIPT =",
)

replace_once(
    "hostd/sg_hostd/operation_jobs.py",
    'def start_core_update_job(engine: str) -> dict[str, Any]:\n',
    '''# SG_GATEWAY_02206_AWG3_REPAIR_JOB_V2\ndef start_awg3_repair_job() -> dict[str, Any]:\n    if not AWG3_REPAIR_SCRIPT.is_file():\n        raise RuntimeError(f"Не найден {AWG3_REPAIR_SCRIPT}")\n    return _start(\n        "awg3_runtime_repair",\n        "Восстановление AWG3 runtime",\n        "/maintenance?tab=updates&refresh=1",\n        "/maintenance?tab=updates",\n        {"engine": "amneziawg3"},\n        command=("/bin/bash", str(AWG3_REPAIR_SCRIPT)),\n    )\n\n\ndef start_core_update_job(engine: str) -> dict[str, Any]:\n''',
    "SG_GATEWAY_02206_AWG3_REPAIR_JOB_V2",
)

replace_once(
    "hostd/sg_hostd/commands.py",
    '    start_full_backup_restore_job,\n)\n',
    '    start_full_backup_restore_job,\n    start_awg3_repair_job,\n)\n',
    "start_awg3_repair_job,",
)

replace_once(
    "hostd/sg_hostd/commands.py",
    'def _data_backup_create() -> HostCommandResult:\n',
    '''# SG_GATEWAY_02206_AWG3_REPAIR_COMMAND_V2\ndef _awg3_runtime_repair_start() -> HostCommandResult:\n    try:\n        payload = start_awg3_repair_job()\n    except Exception as exc:\n        return HostCommandResult(\n            command="runtime.awg3.repair.start",\n            status="error",\n            message=f"Не удалось запустить восстановление AWG3 runtime: {exc}",\n            payload={},\n        )\n    return HostCommandResult(\n        command="runtime.awg3.repair.start",\n        status="ok",\n        message="Восстановление AWG3 runtime запущено",\n        payload=payload,\n    )\n\n\ndef _data_backup_create() -> HostCommandResult:\n''',
    "SG_GATEWAY_02206_AWG3_REPAIR_COMMAND_V2",
)

replace_once(
    "hostd/sg_hostd/commands.py",
    '    "runtime.contract": _runtime_contract_status,\n',
    '    "runtime.contract": _runtime_contract_status,\n    "runtime.awg3.repair.start": _awg3_runtime_repair_start,\n',
    '"runtime.awg3.repair.start":',
)

replace_once(
    "app/main.py",
    '''        elif kind == "full_backup_restore" or kind.startswith("xray_update_"):\n            active = "maintenance"\n''',
    '''        elif (\n            kind in {"full_backup_restore", "awg3_runtime_repair", "panel_update_channel"}\n            or kind.startswith("xray_update_")\n            or kind.startswith("core_update_")\n        ):\n            active = "maintenance"\n''',
    '"awg3_runtime_repair", "panel_update_channel"',
)

replace_once(
    "app/main.py",
    '''        geofiles_updates = None\n        if tab == "updates":\n''',
    '''        geofiles_updates = None\n        runtime_contract = None\n        if tab == "updates":\n''',
    "runtime_contract = None",
)

replace_once(
    "app/main.py",
    '''            core_updates = core_update_overview(refresh=refresh_updates)\n            geofiles_updates = geofiles_overview()\n''',
    '''            core_updates = core_update_overview(refresh=refresh_updates)\n            geofiles_updates = geofiles_overview()\n            runtime_result = run_hostd_command("runtime.contract", timeout=20)\n            runtime_contract = dict(runtime_result.payload or {})\n            if not runtime_contract:\n                runtime_contract = {\n                    "ok": False,\n                    "checks": [],\n                    "message": runtime_result.message or "Runtime Contract недоступен",\n                }\n''',
    'runtime_result = run_hostd_command("runtime.contract", timeout=20)',
)

replace_once(
    "app/main.py",
    '''            geofiles_updates=geofiles_updates,\n            diagnostics=collect_diagnostics(),\n''',
    '''            geofiles_updates=geofiles_updates,\n            runtime_contract=runtime_contract,\n            diagnostics=collect_diagnostics(),\n''',
    "runtime_contract=runtime_contract,",
)

replace_once(
    "app/main.py",
    '    @app.post("/maintenance/core/update/<engine>")\n',
    '''    # SG_GATEWAY_02206_AWG3_REPAIR_ROUTE_V2\n    @app.post("/maintenance/runtime/awg3/repair")\n    def awg3_runtime_repair_start():\n        result = run_hostd_command("runtime.awg3.repair.start", timeout=20)\n        if result.status != "ok":\n            flash(result.message or "Восстановление AWG3 runtime не запущено", "error")\n            return redirect(url_for("maintenance", tab="updates", refresh="1"))\n        return redirect(\n            url_for(\n                "operation_job",\n                job_id=str(result.payload.get("job_id") or ""),\n            )\n        )\n\n    @app.post("/maintenance/core/update/<engine>")\n''',
    "SG_GATEWAY_02206_AWG3_REPAIR_ROUTE_V2",
)

AWG3_CARD = r'''  {# SG_GATEWAY_02206_AWG3_REPAIR_CARD_V2 #}
  {% set awg3_state = namespace(item=None) %}
  {% if runtime_contract %}
    {% for check in runtime_contract.get('checks', []) %}
      {% if check.get('engine') == 'amneziawg3' %}{% set awg3_state.item = check %}{% endif %}
    {% endfor %}
  {% endif %}
  <article class="mtv2-panel sg-ljd-card-large">
    <header class="mtv2-panel-head">
      <div>
        <div class="mtv2-card-kicker">RUNTIME CONTRACT</div>
        <h2>AWG3 Runtime</h2>
        <p>Проверка серверных компонентов AWG3. Повреждённый runtime восстанавливается отдельно — клиенты, ключи и настройки не меняются.</p>
      </div>
      {% if awg3_state.item and awg3_state.item.get('ready') %}
        <span class="mtv31-update-badge">READY</span>
      {% else %}
        <span class="mtv31-update-badge">ТРЕБУЕТ ВОССТАНОВЛЕНИЯ</span>
      {% endif %}
    </header>
    <div class="sg-ljd-nested" style="margin-top:12px">
      {% if awg3_state.item %}
        {% if awg3_state.item.get('ready') %}
          <div class="sg-full-backup-detail">AWG3: все обязательные runtime-компоненты на месте.</div>
        {% else %}
          <div class="sg-full-backup-warning">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3.5 19h17zM12 9v4m0 3h.01"/></svg>
            <span><strong>AWG3 требует восстановления.</strong> {% if awg3_state.item.get('missing') %}{{ awg3_state.item.get('missing') | join(' · ') }}{% endif %}</span>
          </div>
          <form method="post" action="{{ url_for('awg3_runtime_repair_start') }}" style="margin-top:12px"
                data-sg-confirm="Восстановить только AWG3 runtime? Клиенты, ключи и настройки не изменяются."
                data-sg-confirm-title="Восстановить AWG3 runtime" data-sg-confirm-button="Восстановить">
            <button class="button primary" type="submit">Восстановить AWG3 runtime</button>
          </form>
        {% endif %}
      {% else %}
        <div class="sg-full-backup-detail">{{ runtime_contract.get('message', 'Runtime Contract недоступен') if runtime_contract else 'Runtime Contract недоступен' }}</div>
      {% endif %}
    </div>
  </article>

'''
replace_once(
    "app/web/templates/maintenance.html",
    '''  <article class="mtv2-panel mtv32-update-panel sg-ljd-card-large">\n    <header class="mtv2-panel-head">\n      <div>\n        <div class="mtv2-card-kicker">OTHER CORES</div>\n''',
    AWG3_CARD + '''  <article class="mtv2-panel mtv32-update-panel sg-ljd-card-large">\n    <header class="mtv2-panel-head">\n      <div>\n        <div class="mtv2-card-kicker">OTHER CORES</div>\n''',
    "SG_GATEWAY_02206_AWG3_REPAIR_CARD_V2",
)

TEST = r'''from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_awg3_repair_is_pinned_verified_local_first_and_runtime_only() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert 'VENDOR_COMMIT="56df9a7b4fe509282e37374dd6ef3bccdc1b1100"' in body
    assert 'VENDOR_DIR="$PREFIX/vendor/cores"' in body
    assert 'TOOLS_SHA256="090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19"' in body
    assert 'GO_SHA256="131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd"' in body
    assert "stage_vendor_file" in body
    assert "sha256sum -c -" in body
    assert 'PREFIX="$STAGE_ROOT" install' in body
    assert 'mv -- "$AWG3_ROOT" "$BACKUP_ROOT"' in body
    assert 'mv -- "$STAGE_ROOT" "$AWG3_ROOT"' in body
    assert "AWG3 Runtime Contract: OK" in body
    assert "apt-get" not in body
    assert "install.sh" not in body
    assert "UPDATE device_credentials" not in body
    assert "DELETE FROM" not in body


def test_awg3_repair_stops_before_swap_and_rolls_back_runtime_unit_and_service_state() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    stop_at = body.index('systemctl stop "$SERVICE"')
    swap_at = body.index('mv -- "$STAGE_ROOT" "$AWG3_ROOT"')
    assert stop_at < swap_at
    assert "SUCCESS == 0 && MUTATED == 1" in body
    assert 'rm -rf -- "$AWG3_ROOT"' in body
    assert 'mv -- "$BACKUP_ROOT" "$AWG3_ROOT"' in body
    assert 'cp -a -- "$UNIT_BACKUP" "$UNIT_TARGET"' in body
    assert "WAS_ACTIVE" in body
    assert "WAS_ENABLED" in body


def test_awg3_repair_respects_empty_client_state() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert "ACTIVE_CLIENTS" in body
    assert "dc.engine = 'amneziawg3'" in body
    assert "if (( ACTIVE_CLIENTS > 0 ))" in body
    assert 'systemctl disable "$SERVICE"' in body
    assert "Активных AWG3-клиентов нет" in body


def test_awg3_repair_is_background_job_and_maintenance_route() -> None:
    jobs = (ROOT / "hostd" / "sg_hostd" / "operation_jobs.py").read_text(encoding="utf-8")
    commands = (ROOT / "hostd" / "sg_hostd" / "commands.py").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    template = (ROOT / "app" / "web" / "templates" / "maintenance.html").read_text(encoding="utf-8")
    assert "def start_awg3_repair_job()" in jobs
    assert '"awg3_runtime_repair"' in jobs
    assert 'command=("/bin/bash", str(AWG3_REPAIR_SCRIPT))' in jobs
    assert '"runtime.awg3.repair.start": _awg3_runtime_repair_start' in commands
    assert '"/maintenance/runtime/awg3/repair"' in main
    assert "Восстановить AWG3 runtime" in template
    assert "клиенты, ключи и настройки не меняются" in template


def test_maintenance_fetches_runtime_contract_and_keeps_update_jobs_on_maintenance() -> None:
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    template = (ROOT / "app" / "web" / "templates" / "maintenance.html").read_text(encoding="utf-8")
    assert 'run_hostd_command("runtime.contract", timeout=20)' in main
    assert "runtime_contract=runtime_contract" in main
    assert '"awg3_runtime_repair", "panel_update_channel"' in main
    assert 'kind.startswith("core_update_")' in main
    assert "RUNTIME CONTRACT" in template
    assert "AWG3 Runtime" in template
'''
write("tests/test_sg_gateway_v22_awg3_runtime_repair.py", TEST)

replace_once(
    ".github/workflows/dev-02206-guard.yml",
    '''      - name: Run focused Mieru registration regressions\n        run: |\n          python -m pytest \\\n            tests/test_sg_gateway_v22_02206_hardening.py \\\n            tests/test_sg_gateway_v22_production_entrypoint_v4.py \\\n            tests/test_sg_gateway_v22_router_subscription.py \\\n            tests/test_sg_gateway_v22_sg_subscription_dual_ui.py\n''',
    '''      - name: Run focused dev-02206 regressions\n        run: |\n          bash -n deploy/repair-awg3-runtime.sh\n          python -m pytest \\\n            tests/test_sg_gateway_v22_02206_hardening.py \\\n            tests/test_sg_gateway_v22_awg3_runtime_repair.py \\\n            tests/test_sg_gateway_v22_runtime_contract_data_backup.py \\\n            tests/test_sg_gateway_v22_production_entrypoint_v4.py \\\n            tests/test_sg_gateway_v22_router_subscription.py \\\n            tests/test_sg_gateway_v22_sg_subscription_dual_ui.py\n''',
    "Run focused dev-02206 regressions",
)

print("dev-02206 AWG3 repair integration staged")
