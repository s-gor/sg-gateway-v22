from __future__ import annotations

import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from sg_hostd import full_backup_runtime as full_backup
from sg_hostd.full_backup_verify_runtime import VERIFY_UPLOAD_NAME, verify_uploaded_full_backup


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    backup_dir = data_dir / "backups" / "full"
    work_dir = data_dir / "full-backup-work"
    backup_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    monkeypatch.setattr(full_backup, "_data_dir", lambda: data_dir)
    monkeypatch.setattr(full_backup, "_backup_dir", lambda: backup_dir)
    monkeypatch.setattr(full_backup, "_work_dir", lambda: work_dir)
    monkeypatch.setattr(full_backup, "_ensure_dirs", lambda: None)
    return data_dir, backup_dir, work_dir


def _valid_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute("INSERT INTO clients(name) VALUES ('test')")
        connection.commit()
    finally:
        connection.close()


def _write_valid_archive(archive: Path, data_dir: Path) -> None:
    source_db = archive.parent / "source.sqlite"
    _valid_database(source_db)
    manifest = {
        "format": full_backup.FORMAT,
        "format_version": full_backup.FORMAT_VERSION,
        "created_at": "2026-08-15T20:00:00+00:00",
        "source_version": "0.1.0-021.12",
        "contains_private_keys": True,
        "contains_letsencrypt": True,
        "contains_letsencrypt_certificates": True,
        "certificate_domains": ["example.test"],
        "components": [str(data_dir / "sg-gateway.sqlite")],
    }
    manifest_bytes = (json.dumps(manifest) + "\n").encode("utf-8")
    manifest_info = tarfile.TarInfo("manifest.json")
    manifest_info.size = len(manifest_bytes)
    db_arcname = f"payload/{data_dir.relative_to('/')}/sg-gateway.sqlite"
    with tarfile.open(archive, "w:gz") as tar:
        tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
        tar.add(source_db, arcname=db_arcname, recursive=False)


def test_full_backup_verify_accepts_restore_compatible_archive(monkeypatch, tmp_path):
    data_dir, backup_dir, _ = _patch_paths(monkeypatch, tmp_path)
    archive = backup_dir / VERIFY_UPLOAD_NAME
    _write_valid_archive(archive, data_dir)
    payload = verify_uploaded_full_backup()
    assert payload["verified"] is True
    assert payload["format"] == full_backup.FORMAT
    assert payload["format_version"] == full_backup.FORMAT_VERSION
    assert payload["source_version"] == "0.1.0-021.12"
    assert payload["database_tables"] == 1
    assert payload["checks"] == {
        "gzip_tar": "ok",
        "safe_paths": "ok",
        "manifest": "ok",
        "sqlite_integrity": "ok",
    }
    assert len(payload["sha256"]) == 64
    assert not archive.exists()
    assert not (data_dir / "sg-gateway.sqlite").exists()


def test_full_backup_verify_rejects_broken_archive_and_cleans_upload(monkeypatch, tmp_path):
    _, backup_dir, _ = _patch_paths(monkeypatch, tmp_path)
    archive = backup_dir / VERIFY_UPLOAD_NAME
    archive.write_bytes(b"not a gzip tar archive")
    with pytest.raises((tarfile.TarError, OSError, RuntimeError)):
        verify_uploaded_full_backup()
    assert not archive.exists()


def test_full_backup_verify_rejects_archive_without_database(monkeypatch, tmp_path):
    data_dir, backup_dir, _ = _patch_paths(monkeypatch, tmp_path)
    archive = backup_dir / VERIFY_UPLOAD_NAME
    manifest = {
        "format": full_backup.FORMAT,
        "format_version": full_backup.FORMAT_VERSION,
        "created_at": "2026-08-15T20:00:00+00:00",
        "source_version": "0.1.0-021.12",
        "components": [],
    }
    raw = (json.dumps(manifest) + "\n").encode("utf-8")
    info = tarfile.TarInfo("manifest.json")
    info.size = len(raw)
    with tarfile.open(archive, "w:gz") as tar:
        tar.addfile(info, io.BytesIO(raw))
    with pytest.raises(RuntimeError, match="database"):
        verify_uploaded_full_backup()
    assert not archive.exists()
    assert not (data_dir / "sg-gateway.sqlite").exists()
