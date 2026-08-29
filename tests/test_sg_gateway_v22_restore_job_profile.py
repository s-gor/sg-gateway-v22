from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.security import operation_jobs as panel_operation_jobs
from sg_hostd import full_backup_runtime, operation_jobs


def _write_restore_archive(path: Path, manifest: dict) -> None:
    payload = (json.dumps(manifest, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))


def test_full_restore_job_keeps_full_title(monkeypatch, tmp_path: Path) -> None:
    backup_dir = tmp_path / "full"
    monkeypatch.setattr(full_backup_runtime, "_backup_dir", lambda: backup_dir)
    _write_restore_archive(
        backup_dir / full_backup_runtime.RESTORE_UPLOAD_NAME,
        {"format": "sg-gateway-full-backup", "format_version": 1},
    )

    title, extra = operation_jobs._pending_restore_job_context()

    assert title == "Полное восстановление SG-Gateway"
    assert extra == {"restart_expected": True, "restore_profile": "full"}


def test_clients_keys_promoted_restore_gets_clients_title(monkeypatch, tmp_path: Path) -> None:
    backup_dir = tmp_path / "full"
    monkeypatch.setattr(full_backup_runtime, "_backup_dir", lambda: backup_dir)
    _write_restore_archive(
        backup_dir / full_backup_runtime.RESTORE_UPLOAD_NAME,
        {
            "format": "sg-gateway-full-backup",
            "format_version": 1,
            "data_profile": True,
            "clients_keys_profile": True,
            "promoted_from": "sg-gateway-clients-keys-backup",
        },
    )

    title, extra = operation_jobs._pending_restore_job_context()

    assert title == "Восстановление клиентов и ключей"
    assert extra == {
        "restart_expected": True,
        "restore_profile": "clients-and-keys",
    }


def test_restore_job_context_falls_back_safely_on_bad_archive(monkeypatch, tmp_path: Path) -> None:
    backup_dir = tmp_path / "full"
    backup_dir.mkdir(parents=True)
    monkeypatch.setattr(full_backup_runtime, "_backup_dir", lambda: backup_dir)
    (backup_dir / full_backup_runtime.RESTORE_UPLOAD_NAME).write_bytes(b"not-a-tar")

    title, extra = operation_jobs._pending_restore_job_context()

    assert title == "Полное восстановление SG-Gateway"
    assert extra["restore_profile"] == "full"


def test_start_restore_job_passes_detected_profile_to_persistent_job(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(
        operation_jobs,
        "_pending_restore_job_context",
        lambda: (
            "Восстановление клиентов и ключей",
            {"restart_expected": True, "restore_profile": "clients-and-keys"},
        ),
    )

    def fake_start(kind, title, target_url, back_url, extra=None, *, command=None):
        captured.update(
            kind=kind,
            title=title,
            target_url=target_url,
            back_url=back_url,
            extra=extra,
            command=command,
        )
        return {"ok": True, "job_id": "20260820224000-abcdef123456"}

    monkeypatch.setattr(operation_jobs, "_start", fake_start)

    result = operation_jobs.start_full_backup_restore_job()

    assert result["ok"] is True
    assert captured == {
        "kind": "full_backup_restore",
        "title": "Восстановление клиентов и ключей",
        "target_url": "/maintenance?tab=backups",
        "back_url": "/maintenance?tab=backups",
        "extra": {
            "restart_expected": True,
            "restore_profile": "clients-and-keys",
        },
        "command": None,
    }


def test_restore_profile_and_title_survive_panel_restart(monkeypatch, tmp_path: Path) -> None:
    jobs = tmp_path / "operation-jobs"
    jobs.mkdir()
    monkeypatch.setenv("SG_GATEWAY_OPERATION_JOB_DIR", str(jobs))
    job_id = "20260820224000-abcdef123456"
    meta = {
        "kind": "full_backup_restore",
        "title": "Восстановление клиентов и ключей",
        "target_url": "/maintenance?tab=backups",
        "back_url": "/maintenance?tab=backups",
        "created_at": "2026-08-20T22:40:00+00:00",
        "restart_expected": True,
        "restore_profile": "clients-and-keys",
    }
    (jobs / f"{job_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    (jobs / f"{job_id}.status").write_text("running\n", encoding="utf-8")
    (jobs / f"{job_id}.log").write_text(
        "[Restore 6/8] Адрес панели после переключения: https://new.example\n",
        encoding="utf-8",
    )

    restored = panel_operation_jobs.read_job(job_id)

    assert restored["kind"] == "full_backup_restore"
    assert restored["title"] == "Восстановление клиентов и ключей"
    assert restored["restart_expected"] is True
    assert restored["restore_profile"] == "clients-and-keys"
    assert restored["status"] == "running"
    assert "https://new.example" in restored["log"]
