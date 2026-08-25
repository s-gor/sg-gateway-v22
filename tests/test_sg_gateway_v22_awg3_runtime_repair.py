from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import runtime_ui
from app.engines import provisioning

ROOT = Path(__file__).resolve().parents[1]


def test_awg3_repair_is_pinned_verified_local_first_and_runtime_only() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert 'VENDOR_COMMIT="56df9a7b4fe509282e37374dd6ef3bccdc1b1100"' in body
    assert 'VENDOR_DIR="$PREFIX/vendor/cores"' in body
    assert 'TOOLS_SHA256="090f9383532822a756d078890b447e00af7f46bd30a10f9f47c46d633d807b19"' in body
    assert 'GO_SHA256="131110027db6d5dc0e35b19eb5b8a2692676081366c34112088dc68bbb050bcd"' in body
    assert "stage_vendor_file" in body
    assert "sha256sum -c -" in body
    assert 'PREFIX="$STAGE_ROOT" SYSCONFDIR="$STAGE_ROOT/etc" install' in body
    assert 'mv -- "$AWG3_ROOT" "$BACKUP_ROOT"' in body
    assert 'mv -- "$STAGE_ROOT" "$AWG3_ROOT"' in body
    assert "AWG3 Runtime Contract: OK" in body
    assert "apt-get" not in body
    assert "install.sh" not in body
    assert "UPDATE device_credentials" not in body
    assert "DELETE FROM" not in body


def test_awg3_repair_checks_build_toolchain_before_staging_or_mutation() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    marker = "for command in tar make cc pkg-config sha256sum find install cp mv systemctl; do"
    assert marker in body
    preflight_at = body.index(marker)
    staging_at = body.index('TMP="$(mktemp -d /tmp/sg-gateway-awg3-repair.')
    mutation_at = body.index("MUTATED=1")
    assert preflight_at < staging_at < mutation_at


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


def test_awg3_repair_respects_empty_client_state_and_guides_partial_recovery() -> None:
    body = (ROOT / "deploy/repair-awg3-runtime.sh").read_text(encoding="utf-8")
    assert "ACTIVE_CLIENTS" in body
    assert "dc.engine = 'amneziawg3'" in body
    assert "if (( ACTIVE_CLIENTS > 0 ))" in body
    assert 'systemctl disable "$SERVICE"' in body
    assert "Активных AWG3-клиентов нет" in body
    assert "Откройте Clients и нажмите «Проверить и применить»" in body


def test_awg3_userspace_helper_splits_dual_stack_address_values() -> None:
    body = (ROOT / "deploy/sg-gateway-awg3-userspace.sh").read_text(encoding="utf-8")
    assert 'done < <(config_values Address)' in body
    assert "IFS=',' read -r -a addresses <<< \"$address_line\"" in body
    assert 'for address in "${addresses[@]}"' in body
    assert 'if [[ "$address" == *:* ]]' in body
    assert 'ip -6 address add "$address" dev "$IFACE"' in body
    assert 'ip -4 address add "$address" dev "$IFACE"' in body


def test_awg3_credential_preflight_stops_before_subprocess(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing-awg3"
    monkeypatch.setattr(provisioning, "AWG3_AWG", str(missing / "bin" / "awg"))
    monkeypatch.setattr(provisioning, "AWG3_AWG_QUICK", str(missing / "bin" / "awg-quick"))
    monkeypatch.setattr(provisioning, "AWG3_GO", str(missing / "bin" / "amneziawg-go"))
    monkeypatch.setattr(provisioning, "AWG3_HELPER", str(missing / "deploy" / "helper.sh"))
    monkeypatch.setattr(
        provisioning,
        "AWG3_UNIT_PATHS",
        (str(missing / "systemd" / "sg-gateway-awg3.service"),),
    )

    def unexpected_subprocess(*args, **kwargs):
        raise AssertionError("subprocess.run must not execute before AWG3 preflight passes")

    monkeypatch.setattr(provisioning.subprocess, "run", unexpected_subprocess)

    with pytest.raises(RuntimeError, match="AWG3 требует восстановления") as error:
        provisioning._awg3_keypair()

    assert "Откройте Maintenance → AWG3 Runtime" in str(error.value)


def test_runtime_ui_blocks_only_explicit_missing_awg3_and_exposes_deployment(monkeypatch) -> None:
    missing = SimpleNamespace(
        payload={
            "checks": [
                {
                    "engine": "amneziawg3",
                    "ready": False,
                    "missing": ["/opt/sg-gateway/awg3/bin/awg"],
                    "deployment": {
                        "required": True,
                        "ready": False,
                        "missing": ["generated config", "active service"],
                        "config_ready": False,
                        "service_active": False,
                    },
                }
            ]
        },
        message="Runtime Contract failed",
    )
    monkeypatch.setattr(runtime_ui, "run_hostd_command", lambda command, timeout=2: missing)
    state = runtime_ui.runtime_engine_state("amneziawg3")
    assert state["known"] is True
    assert state["ready"] is False
    assert state["missing"] == ["/opt/sg-gateway/awg3/bin/awg"]
    assert state["deployment"] == {
        "required": True,
        "ready": False,
        "missing": ["generated config", "active service"],
        "config_ready": False,
        "service_active": False,
    }

    unknown = SimpleNamespace(payload={}, message="sg-hostd unavailable")
    monkeypatch.setattr(runtime_ui, "run_hostd_command", lambda command, timeout=2: unknown)
    state = runtime_ui.runtime_engine_state("amneziawg3")
    assert state["known"] is False
    assert state["ready"] is True
    assert state["deployment"] == {}


def test_awg3_runtime_ui_prevents_new_access_but_preserves_selected_access() -> None:
    production = (ROOT / "app" / "production.py").read_text(encoding="utf-8")
    clients = (ROOT / "app" / "web" / "templates" / "clients.html").read_text(encoding="utf-8")
    dialogs = (ROOT / "app" / "web" / "templates" / "_client_edit_dialogs.html").read_text(encoding="utf-8")
    detail = (ROOT / "app" / "web" / "templates" / "client_detail.html").read_text(encoding="utf-8")
    assert "runtime_engine_state" in production
    assert "runtime_engine_state('amneziawg3')" in clients
    assert "AWG3 runtime требует восстановления в Maintenance" in clients
    assert "data-awg3-runtime-warning" in clients
    assert "runtime_engine_state('amneziawg3')" in dialogs
    assert "if (input.checked) return;" in dialogs
    assert "input.disabled = true;" in dialogs
    assert 'value="amneziawg3"' in detail


def test_02204_missing_awg3_can_update_then_repair_without_blocking_other_clients() -> None:
    updater = (ROOT / "deploy/update-from-github-core.sh").read_text(encoding="utf-8")
    panel_runtime = (ROOT / "hostd" / "sg_hostd" / "panel_update_runtime.py").read_text(encoding="utf-8")
    client_runtime = (ROOT / "hostd" / "sg_hostd" / "client_runtime.py").read_text(encoding="utf-8")
    commands = (ROOT / "hostd" / "sg_hostd" / "commands.py").read_text(encoding="utf-8")
    repair = (ROOT / "deploy" / "repair-awg3-runtime.sh").read_text(encoding="utf-8")

    assert "sparse-checkout set app hostd deploy" in updater
    assert '".venv"|"awg3") continue ;;' in updater
    assert "clients.apply" not in updater
    assert "runtime.contract" not in updater
    assert 'env["SG_GATEWAY_GITHUB_BRANCH"] = GITHUB_BRANCH' in panel_runtime
    assert '["/bin/bash", str(script)]' in panel_runtime

    apply_all = client_runtime.split("def apply_all_clients()", 1)[1]
    assert "include_all_critical=False" in apply_all

    runtime_status = commands.split("def _runtime_contract_status()", 1)[1].split("def ", 1)[0]
    assert "include_all_critical=True" in runtime_status

    assert 'VENDOR_DIR="$PREFIX/vendor/cores"' in repair
    assert 'RAW_BASE="https://raw.githubusercontent.com/s-gor/sg-gateway-v22/${VENDOR_COMMIT}/vendor/cores"' in repair
    assert "stage_vendor_file" in repair
    assert "UPDATE device_credentials" not in repair
    assert "DELETE FROM" not in repair


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
