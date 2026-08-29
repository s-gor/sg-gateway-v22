from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import restore_hardening_patch, runtime_contracts


def _restore_fixture(tmp_path: Path, *, clients_keys: bool = False):
    backup_dir = tmp_path / "backups"
    work_dir = tmp_path / "work"
    backup_dir.mkdir()
    work_dir.mkdir()
    restore_upload = backup_dir / "restore-upload.sgbackup"
    restore_upload.write_bytes(b"staged")
    safety = backup_dir / "SG-Gateway-SAFETY-test.sgbackup"
    safety.write_bytes(b"safety")
    events: list[tuple] = []

    def extract(archive: Path, target: Path) -> dict:
        events.append(("extract", archive.name))
        if archive == restore_upload:
            data = target / "payload" / "var" / "lib" / "sg-gateway"
            data.mkdir(parents=True, exist_ok=True)
            database = sqlite3.connect(data / "sg-gateway.sqlite")
            try:
                database.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY)")
                database.commit()
            finally:
                database.close()
            return {
                "source_version": "0.1.0-source",
                "clients_keys_profile": clients_keys,
            }
        return {"source_version": "0.1.0-safety"}

    fake = SimpleNamespace(
        RESTORE_UPLOAD_NAME="restore-upload.sgbackup",
        _ensure_dirs=lambda: events.append(("ensure_dirs",)),
        _backup_dir=lambda: backup_dir,
        _restore_progress=lambda text: events.append(("progress", text)),
        _work_dir=lambda: work_dir,
        _extract_archive=extract,
        _data_dir=lambda: Path("/var/lib/sg-gateway"),
        create_full_backup_archive=lambda prefix: {
            "path": str(safety),
            "name": safety.name,
        },
        _restore_payload=lambda payload, preserve_machine_env: events.append(
            ("restore_payload", preserve_machine_env)
        ),
        _normalize_panel_data_permissions=lambda: events.append(("normalize",)),
        _validate_database_as_panel_user=lambda: events.append(("db_user",)),
        _restored_certificate_ready=lambda: (False, ""),
        _restored_tls_state=lambda: {},
        _refresh_restored_https_from_local_files=lambda **kwargs: events.append(
            ("refresh_https", kwargs)
        ),
        _apply_client_runtime_required=lambda: events.append(("clients_runtime",)),
        _normalize_xray_full_access=lambda: events.append(("normalize_xray",)),
        _restart_xray_required=lambda: events.append(("restart_xray",)),
        _validate_runtime_after_restore=lambda: events.append(("validate_runtime",)),
        _restart_runtime=lambda schedule_panel=False: events.append(
            ("restart_runtime", schedule_panel)
        ),
        _probe=lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="", stderr=""
        ),
    )
    return fake, restore_upload, safety, events


def _patch_transaction_dependencies(monkeypatch, events: list[tuple]) -> None:
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
    monkeypatch.setattr(
        runtime_contracts,
        "assert_runtime_contract",
        lambda **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        restore_hardening_patch,
        "_local_panel_health",
        lambda full: events.append(("panel_health_pre",)),
    )
    monkeypatch.setattr(
        restore_hardening_patch,
        "_panel_service_generation",
        lambda full: events.append(("panel_generation",)) or 100,
    )
    monkeypatch.setattr(
        restore_hardening_patch,
        "_schedule_panel_restart_required",
        lambda full: events.append(("schedule_panel",)),
    )


def test_success_is_reported_only_after_post_restart_validation(
    tmp_path: Path, monkeypatch
) -> None:
    fake, restore_upload, safety, events = _restore_fixture(tmp_path)
    _patch_transaction_dependencies(monkeypatch, events)
    monkeypatch.setattr(
        restore_hardening_patch,
        "_wait_for_panel_after_scheduled_restart",
        lambda full, previous_generation: events.append(
            ("panel_health_post", previous_generation)
        ),
    )

    result = restore_hardening_patch._restore_uploaded_full_backup(fake)

    assert result["restore_profile"] == "full"
    assert result["panel_health_validated"] is True
    assert result["panel_post_restart_health_validated"] is True
    assert result["panel_restart_generation_changed"] is True
    assert result["safety_backup"] == safety.name
    assert result["source_version"] == "0.1.0-source"
    assert ("restore_payload", True) in events
    assert ("restore_payload", False) not in events

    pre_health = events.index(("panel_health_pre",))
    generation = events.index(("panel_generation",))
    schedule = events.index(("schedule_panel",))
    post_health = events.index(("panel_health_post", 100))
    final = next(
        index
        for index, item in enumerate(events)
        if item[0] == "progress" and "[Restore 8/8]" in item[1]
    )
    assert pre_health < generation < schedule < post_health < final
    assert not restore_upload.exists()
    assert safety.exists()


def test_post_restart_failure_forces_safety_rollback_and_validates_new_panel(
    tmp_path: Path, monkeypatch
) -> None:
    fake, restore_upload, safety, events = _restore_fixture(tmp_path)
    _patch_transaction_dependencies(monkeypatch, events)
    waits = {"count": 0}

    def wait(full, previous_generation: int) -> None:
        waits["count"] += 1
        events.append(("panel_health_post", waits["count"], previous_generation))
        if waits["count"] == 1:
            raise RuntimeError("injected post-restart panel failure")

    monkeypatch.setattr(
        restore_hardening_patch,
        "_wait_for_panel_after_scheduled_restart",
        wait,
    )

    with pytest.raises(
        RuntimeError,
        match="Safety Rollback выполнен и проверен после restart",
    ) as exc:
        restore_hardening_patch._restore_uploaded_full_backup(fake)

    assert "injected post-restart panel failure" in str(exc.value)
    assert waits["count"] == 2
    assert ("restore_payload", True) in events
    assert ("restore_payload", False) in events
    assert ("restart_runtime", False) in events

    main_post = events.index(("panel_health_post", 1, 100))
    rollback_restore = events.index(("restore_payload", False))
    rollback_restart = events.index(("restart_runtime", False))
    rollback_post = events.index(("panel_health_post", 2, 100))
    verified = next(
        index
        for index, item in enumerate(events)
        if item[0] == "progress"
        and "Safety Rollback выполнен и проверен после restart" in item[1]
    )
    assert main_post < rollback_restore < rollback_restart < rollback_post < verified
    assert restore_upload.exists()
    assert safety.exists()
