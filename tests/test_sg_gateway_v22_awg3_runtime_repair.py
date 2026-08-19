from __future__ import annotations

from pathlib import Path

import pytest

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
