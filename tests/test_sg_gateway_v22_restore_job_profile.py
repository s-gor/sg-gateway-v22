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
