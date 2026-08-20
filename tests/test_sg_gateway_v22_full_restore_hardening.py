from __future__ import annotations

import inspect
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from sg_hostd import full_backup_runtime
from sg_hostd import restore_hardening_patch


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


def test_safety_rollback_is_validated_before_panel_restart_and_reports_outcome() -> None:
    source = inspect.getsource(restore_hardening_patch._restore_uploaded_full_backup)
    rollback = source.split("except Exception as restore_exc:", 1)[1]
    assert rollback.index("full._validate_runtime_after_restore()") < rollback.index(
        "full._restart_runtime(schedule_panel=False)"
    )
    assert rollback.index("full._restart_runtime(schedule_panel=False)") < rollback.index(
        "_local_panel_health(full)"
    )
    assert rollback.index("_local_panel_health(full)") < rollback.index(
        "full._schedule_panel_restart()"
    )
    assert "Safety Rollback выполнен и проверен" in rollback
    assert "Safety Rollback также не прошёл проверку" in rollback


def test_dev_full_restore_runtime_is_replaced_by_hardened_contract() -> None:
    assert hasattr(full_backup_runtime, "restore_space_plan")
    assert hasattr(full_backup_runtime, "validate_local_panel_health")
    assert full_backup_runtime.restore_uploaded_full_backup.__module__ == (
        "sg_hostd.restore_hardening_patch"
    )
