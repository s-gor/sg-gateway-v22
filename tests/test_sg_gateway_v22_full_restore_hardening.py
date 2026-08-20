from __future__ import annotations

import inspect
import io
import sqlite3
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sg_hostd import full_backup_runtime
from sg_hostd import restore_hardening_patch
from sg_hostd import runtime_contracts


def _test_archive(path: Path, size: int = 4096) -> None:
    payload = b"x" * size
    info = tarfile.TarInfo("payload/var/lib/sg-gateway/sg-gateway.sqlite")
    info.size = len(payload)
    with tarfile.open(path, "w:gz") as tar:
        tar.addfile(info, io.BytesIO(payload))


def _fake_full(tmp_path: Path):
    data = tmp_path / "data"
    work = tmp_path / "work"
    data.mkdir()
    work.mkdir()
    database = data / "sg-gateway.sqlite"
    database.write_bytes(b"d" * 2048)
    root_state = tmp_path / "root-state.bin"
    root_state.write_bytes(b"r" * 8192)
    return SimpleNamespace(
        TRANSIENT_SECURITY_DIRS={"backups", "jobs"},
        _is_internal_history_member=lambda name: False,
        _work_dir=lambda: work,
        _data_dir=lambda: data,
        _archive_sources=lambda: ([root_state], []),
        _validate_members=lambda tar, root, members: None,
    )


def test_full_restore_space_preflight_runs_before_extract_and_safety_backup() -> None:
    source = inspect.getsource(restore_hardening_patch._restore_uploaded_full_backup)
    assert source.index("_preflight_full_restore(full, archive)") < source.index(
        "full._extract_archive(archive, temp)"
    )
    assert source.index("_preflight_full_restore(full, archive)") < source.index(
        "full.create_full_backup_archive(prefix=\"SG-Gateway-SAFETY\")"
    )


def test_full_restore_space_preflight_counts_restore_and_two_safety_working_sets(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "restore-upload.sgbackup"
    _test_archive(archive, 4096)
    fake = _fake_full(tmp_path)

    free = 10 * 1024 * 1024 * 1024
    monkeypatch.setattr(
        restore_hardening_patch.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=free, used=0, free=free),
    )
    plan = restore_hardening_patch._restore_space_plan(fake, archive)

    current = 8192 + 2048
    assert plan["archive_unpacked_bytes"] == 4096
    assert plan["current_state_bytes"] == current
    assert plan["required_free_bytes"] >= 4096 + 2 * current
    assert plan["margin_bytes"] >= restore_hardening_patch.RESTORE_MARGIN_MIN_BYTES


def test_full_restore_space_preflight_blocks_without_mutating_server(
    tmp_path: Path, monkeypatch
) -> None:
    archive = tmp_path / "restore-upload.sgbackup"
    _test_archive(archive, 4096)
    fake = _fake_full(tmp_path)
    monkeypatch.setattr(
        restore_hardening_patch.shutil,
        "disk_usage",
        lambda path: SimpleNamespace(total=1, used=0, free=1),
    )

    with pytest.raises(RuntimeError, match="Недостаточно свободного места") as exc:
        restore_hardening_patch._preflight_full_restore(fake, archive)
    assert "Сервер не изменён" in str(exc.value)


def test_post_restart_health_wait_does_not_accept_pre_restart_process(monkeypatch) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def health(full) -> None:
        attempts.append("health")
        if len(attempts) == 1:
            raise RuntimeError("panel is still restarting")

    monkeypatch.setattr(restore_hardening_patch, "_local_panel_health", health)
    monkeypatch.setattr(
        restore_hardening_patch.time,
        "sleep",
        lambda seconds: sleeps.append(float(seconds)),
    )

    restore_hardening_patch._wait_for_panel_after_scheduled_restart(SimpleNamespace())

    assert attempts == ["health", "health"]
    assert sleeps[0] == restore_hardening_patch.PANEL_RESTART_GRACE_SECONDS
    assert sleeps[1] == restore_hardening_patch.PANEL_RESTART_HEALTH_POLL_SECONDS


def test_safety_rollback_is_validated_before_and_after_panel_restart() -> None:
    source = inspect.getsource(restore_hardening_patch._restore_uploaded_full_backup)
    rollback = source.split("except Exception as restore_exc:", 1)[1]
    validate = rollback.index("full._validate_runtime_after_restore()")
    runtime_restart = rollback.index("full._restart_runtime(schedule_panel=False)")
    pre_health = rollback.index("_local_panel_health(full)")
    schedule = rollback.index("full._schedule_panel_restart()")
    post_health = rollback.index("_wait_for_panel_after_scheduled_restart(full)")
    assert validate < runtime_restart < pre_health < schedule < post_health
    assert "Safety Rollback выполнен и проверен после restart" in rollback
    assert "Safety Rollback также" in rollback
    assert "не прошёл проверку" in rollback


def test_restore_failure_after_mutation_executes_and_validates_safety_rollback(
    tmp_path: Path, monkeypatch
) -> None:
    backup_dir = tmp_path / "backups"
    work_dir = tmp_path / "work"
    backup_dir.mkdir()
    work_dir.mkdir()
    restore_upload = backup_dir / "restore-upload.sgbackup"
    restore_upload.write_bytes(b"staged")
    safety_path = backup_dir / "SG-Gateway-SAFETY-test.sgbackup"
    safety_path.write_bytes(b"safety")
    events: list[tuple] = []

    def extract(archive: Path, target: Path) -> dict:
        payload = target / "payload" / "var" / "lib" / "sg-gateway"
        payload.mkdir(parents=True, exist_ok=True)
        if archive == restore_upload:
            database = sqlite3.connect(payload / "sg-gateway.sqlite")
            try:
                database.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY)")
                database.commit()
            finally:
                database.close()
            return {
                "source_version": "0.1.0-test",
                "clients_keys_profile": False,
            }
        return {"source_version": "safety"}

    def restore_payload(payload: Path, preserve_machine_env: bool) -> None:
        events.append(("restore_payload", preserve_machine_env))

    def fail_after_mutation() -> None:
        events.append(("apply_client_runtime",))
        raise RuntimeError("injected runtime failure")

    fake = SimpleNamespace(
        RESTORE_UPLOAD_NAME="restore-upload.sgbackup",
        _ensure_dirs=lambda: None,
        _backup_dir=lambda: backup_dir,
        _restore_progress=lambda text: events.append(("progress", text)),
        _work_dir=lambda: work_dir,
        _extract_archive=extract,
        _data_dir=lambda: Path("/var/lib/sg-gateway"),
        create_full_backup_archive=lambda prefix: {
            "path": str(safety_path),
            "name": safety_path.name,
        },
        _restore_payload=restore_payload,
        _normalize_panel_data_permissions=lambda: events.append(("normalize",)),
        _validate_database_as_panel_user=lambda: events.append(("db_user",)),
        _restored_certificate_ready=lambda: (False, ""),
        _restored_tls_state=lambda: {},
        _refresh_restored_https_from_local_files=lambda **kwargs: events.append(
            ("refresh_https", kwargs)
        ),
        _apply_client_runtime_required=fail_after_mutation,
        _normalize_xray_full_access=lambda: events.append(("normalize_xray",)),
        _restart_xray_required=lambda: events.append(("restart_xray",)),
        _validate_runtime_after_restore=lambda: events.append(("validate_runtime",)),
        _schedule_panel_restart=lambda: events.append(("schedule_panel",)),
        _restart_runtime=lambda schedule_panel=False: events.append(
            ("restart_runtime", schedule_panel)
        ),
        _probe=lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="", stderr=""
        ),
    )

    monkeypatch.setattr(
        restore_hardening_patch,
        "_preflight_full_restore",
        lambda full, archive: {
            "archive_unpacked_bytes": 1,
            "current_state_bytes": 1,
            "margin_bytes": 1,
            "required_free_bytes": 3,
            "free_bytes": 100,
        },
    )
    monkeypatch.setattr(runtime_contracts, "assert_runtime_contract", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        restore_hardening_patch,
        "_local_panel_health",
        lambda full: events.append(("panel_health_pre",)),
    )
    monkeypatch.setattr(
        restore_hardening_patch,
        "_wait_for_panel_after_scheduled_restart",
        lambda full: events.append(("panel_health_post",)),
    )

    with pytest.raises(RuntimeError, match="Safety Rollback выполнен и проверен после restart"):
        restore_hardening_patch._restore_uploaded_full_backup(fake)

    assert ("restore_payload", True) in events
    assert ("restore_payload", False) in events
    rollback_restore = events.index(("restore_payload", False))
    runtime_restart = events.index(("restart_runtime", False))
    pre_health = events.index(("panel_health_pre",))
    panel_restart = events.index(("schedule_panel",))
    post_health = events.index(("panel_health_post",))
    assert rollback_restore < runtime_restart < pre_health < panel_restart < post_health
    assert any(
        item[0] == "progress"
        and "Safety Rollback выполнен и проверен после restart" in item[1]
        for item in events
    )


def test_success_path_requires_post_restart_health_before_final_success() -> None:
    source = inspect.getsource(restore_hardening_patch._restore_uploaded_full_backup)
    success = source.split("try:", 1)[1].split("except Exception as restore_exc:", 1)[0]
    pre_health = success.index("_local_panel_health(full)")
    schedule = success.index("full._schedule_panel_restart()")
    post_health = success.index("_wait_for_panel_after_scheduled_restart(full)")
    final = success.index("[Restore 8/8]")
    assert pre_health < schedule < post_health < final
    assert '"panel_post_restart_health_validated": True' in source


def test_restore_outcome_and_errors_are_profile_aware() -> None:
    source = inspect.getsource(restore_hardening_patch._restore_uploaded_full_backup)
    assert 'manifest.get("clients_keys_profile") is True' in source
    assert 'restore_profile = "clients-and-keys" if clients_keys_profile else "full"' in source
    assert "Восстановление клиентов и ключей завершено" in source
    assert "Восстановление клиентов и ключей завершилось ошибкой" in source
    assert '"restore_profile": restore_profile' in source
    assert "Clients & Keys restored; destination server settings preserved" in source
    assert "Full backup restored; destination public IP preserved" in source


def test_dev_full_restore_runtime_is_replaced_by_hardened_contract() -> None:
    assert hasattr(full_backup_runtime, "restore_space_plan")
    assert hasattr(full_backup_runtime, "validate_local_panel_health")
    assert full_backup_runtime.restore_uploaded_full_backup.__module__ == (
        "sg_hostd.restore_hardening_patch"
    )
