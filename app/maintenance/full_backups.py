from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config


FULL_BACKUP_SUFFIX = ".sgbackup"
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
VERIFIED_METADATA_NAME = "verified-upload.json"
_TRANSIENT_UPLOAD_NAMES = {RESTORE_UPLOAD_NAME, VERIFY_UPLOAD_NAME, VERIFIED_UPLOAD_NAME}


@dataclass(frozen=True)
class FullBackupInfo:
    name: str
    path: Path
    size_bytes: int
    created_at: str


def get_full_backup_dir() -> Path:
    directory = load_config().data_dir / "backups" / "full"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _valid_name(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name and ".." not in name and name.endswith(FULL_BACKUP_SUFFIX)


def _info(path: Path) -> FullBackupInfo:
    stat = path.stat()
    return FullBackupInfo(
        name=path.name,
        path=path,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def list_full_backups() -> list[FullBackupInfo]:
    directory = get_full_backup_dir()
    paths = [
        path
        for path in directory.glob("SG-Gateway-FULL-*.sgbackup")
        if path.is_file() and path.name not in _TRANSIENT_UPLOAD_NAMES
    ]
    return sorted((_info(path) for path in paths), key=lambda item: item.name, reverse=True)


def get_full_backup(name: str) -> FullBackupInfo | None:
    if not _valid_name(name):
        return None
    path = get_full_backup_dir() / name
    if not path.is_file() or path.name in _TRANSIENT_UPLOAD_NAMES:
        return None
    return _info(path)


def _stage_uploaded_full_backup(file_storage, destination_name: str) -> Path:
    if destination_name not in _TRANSIENT_UPLOAD_NAMES:
        raise ValueError("Недопустимое имя временного backup")

    original = str(getattr(file_storage, "filename", "") or "").strip()
    if not original.lower().endswith(FULL_BACKUP_SUFFIX):
        raise ValueError("Нужен файл SG-Gateway с расширением .sgbackup")

    directory = get_full_backup_dir()
    destination = directory / destination_name
    temporary = directory / f".{destination_name}.tmp"
    temporary.unlink(missing_ok=True)

    total = 0
    with temporary.open("wb") as handle:
        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())

    if total < 128:
        temporary.unlink(missing_ok=True)
        raise ValueError("Файл backup пустой или повреждён")

    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def stage_uploaded_full_backup(file_storage) -> Path:
    return _stage_uploaded_full_backup(file_storage, RESTORE_UPLOAD_NAME)


def stage_uploaded_full_backup_for_verification(file_storage) -> Path:
    clear_verified_full_backup()
    return _stage_uploaded_full_backup(file_storage, VERIFY_UPLOAD_NAME)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clear_verified_full_backup() -> None:
    directory = get_full_backup_dir()
    (directory / VERIFIED_UPLOAD_NAME).unlink(missing_ok=True)
    (directory / VERIFIED_METADATA_NAME).unlink(missing_ok=True)


def save_verified_full_backup(original_name: str, payload: dict) -> dict:
    directory = get_full_backup_dir()
    archive = directory / VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Проверенный backup не найден")

    expected_sha256 = str(payload.get("sha256") or "").strip().lower()
    actual_sha256 = _sha256(archive)
    if not expected_sha256 or actual_sha256 != expected_sha256:
        clear_verified_full_backup()
        raise RuntimeError("SHA-256 проверенного backup не совпал")

    metadata = {
        "original_name": str(original_name or VERIFIED_UPLOAD_NAME),
        "size_bytes": archive.stat().st_size,
        "sha256": actual_sha256,
        "source_version": str(payload.get("source_version") or "unknown"),
        "created_at": str(payload.get("created_at") or "не указано"),
        "database_tables": int(payload.get("database_tables") or 0),
        "database_size_bytes": int(payload.get("database_size_bytes") or 0),
        "contains_letsencrypt_certificates": bool(payload.get("contains_letsencrypt_certificates")),
    }
    destination = directory / VERIFIED_METADATA_NAME
    temporary = directory / f".{VERIFIED_METADATA_NAME}.tmp"
    temporary.unlink(missing_ok=True)
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return metadata


def get_verified_full_backup() -> dict | None:
    directory = get_full_backup_dir()
    archive = directory / VERIFIED_UPLOAD_NAME
    metadata_path = directory / VERIFIED_METADATA_NAME
    if not archive.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        if int(metadata.get("size_bytes") or -1) != archive.stat().st_size:
            return None
        if len(str(metadata.get("sha256") or "")) != 64:
            return None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return metadata


def stage_verified_full_backup_for_restore() -> dict:
    metadata = get_verified_full_backup()
    if metadata is None:
        raise RuntimeError("Сначала выберите и проверьте файл .sgbackup")

    directory = get_full_backup_dir()
    archive = directory / VERIFIED_UPLOAD_NAME
    actual_sha256 = _sha256(archive)
    if actual_sha256 != str(metadata.get("sha256") or ""):
        clear_verified_full_backup()
        raise RuntimeError("Проверенный backup изменился: выберите и проверьте файл заново")

    os.replace(archive, directory / RESTORE_UPLOAD_NAME)
    (directory / VERIFIED_METADATA_NAME).unlink(missing_ok=True)
    return metadata
# SG_GATEWAY_02206_DATA_BACKUP_PROFILE_V1
DATA_BACKUP_SUFFIX = ".sgbackup"
DATA_VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
DATA_VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
DATA_RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
DATA_VERIFIED_METADATA_NAME = "verified-upload.json"
_DATA_TRANSIENT_UPLOAD_NAMES = {
    DATA_VERIFY_UPLOAD_NAME,
    DATA_VERIFIED_UPLOAD_NAME,
    DATA_RESTORE_UPLOAD_NAME,
}


def get_data_backup_dir() -> Path:
    directory = load_config().data_dir / "backups" / "data"
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def list_data_backups() -> list[FullBackupInfo]:
    directory = get_data_backup_dir()
    paths = [
        path
        for path in directory.glob("SG-Gateway-DATA-*.sgbackup")
        if path.is_file() and path.name not in _DATA_TRANSIENT_UPLOAD_NAMES
    ]
    return sorted((_info(path) for path in paths), key=lambda item: item.name, reverse=True)


def get_data_backup(name: str) -> FullBackupInfo | None:
    if not _valid_name(name) or not name.startswith("SG-Gateway-DATA-"):
        return None
    path = get_data_backup_dir() / name
    if not path.is_file() or path.name in _DATA_TRANSIENT_UPLOAD_NAMES:
        return None
    return _info(path)


def clear_verified_data_backup() -> None:
    directory = get_data_backup_dir()
    (directory / DATA_VERIFIED_UPLOAD_NAME).unlink(missing_ok=True)
    (directory / DATA_VERIFIED_METADATA_NAME).unlink(missing_ok=True)


def stage_uploaded_data_backup_for_verification(file_storage) -> Path:
    clear_verified_data_backup()
    original = str(getattr(file_storage, "filename", "") or "").strip()
    if not original.lower().endswith(DATA_BACKUP_SUFFIX):
        raise ValueError("Нужен файл SG-Gateway с расширением .sgbackup")

    directory = get_data_backup_dir()
    destination = directory / DATA_VERIFY_UPLOAD_NAME
    temporary = directory / f".{DATA_VERIFY_UPLOAD_NAME}.tmp"
    temporary.unlink(missing_ok=True)
    total = 0
    with temporary.open("wb") as handle:
        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    if total < 128:
        temporary.unlink(missing_ok=True)
        raise ValueError("Файл backup пустой или повреждён")
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination


def save_verified_data_backup(original_name: str, payload: dict) -> dict:
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Проверенный DATA backup не найден")
    expected_sha256 = str(payload.get("sha256") or "").strip().lower()
    actual_sha256 = _sha256(archive)
    if not expected_sha256 or actual_sha256 != expected_sha256:
        clear_verified_data_backup()
        raise RuntimeError("SHA-256 проверенного DATA backup не совпал")
    metadata = {
        "original_name": str(original_name or DATA_VERIFIED_UPLOAD_NAME),
        "size_bytes": archive.stat().st_size,
        "sha256": actual_sha256,
        "source_version": str(payload.get("source_version") or "unknown"),
        "created_at": str(payload.get("created_at") or "не указано"),
        "database_tables": int(payload.get("database_tables") or 0),
        "database_size_bytes": int(payload.get("database_size_bytes") or 0),
        "contains_letsencrypt_certificates": bool(payload.get("contains_letsencrypt_certificates")),
        "profile": "clients-and-settings",
    }
    destination = directory / DATA_VERIFIED_METADATA_NAME
    temporary = directory / f".{DATA_VERIFIED_METADATA_NAME}.tmp"
    temporary.unlink(missing_ok=True)
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return metadata


def get_verified_data_backup() -> dict | None:
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    metadata_path = directory / DATA_VERIFIED_METADATA_NAME
    if not archive.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        if int(metadata.get("size_bytes") or -1) != archive.stat().st_size:
            return None
        if len(str(metadata.get("sha256") or "")) != 64:
            return None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return metadata


def stage_verified_data_backup_for_restore() -> dict:
    metadata = get_verified_data_backup()
    if metadata is None:
        raise RuntimeError("Сначала выберите и проверьте DATA .sgbackup")
    directory = get_data_backup_dir()
    archive = directory / DATA_VERIFIED_UPLOAD_NAME
    actual_sha256 = _sha256(archive)
    if actual_sha256 != str(metadata.get("sha256") or ""):
        clear_verified_data_backup()
        raise RuntimeError("Проверенный DATA backup изменился: выберите файл заново")
    os.replace(archive, directory / DATA_RESTORE_UPLOAD_NAME)
    (directory / DATA_VERIFIED_METADATA_NAME).unlink(missing_ok=True)
    return metadata
