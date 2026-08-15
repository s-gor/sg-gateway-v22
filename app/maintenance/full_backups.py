from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config


FULL_BACKUP_SUFFIX = ".sgbackup"
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024


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
        if path.is_file() and path.name != RESTORE_UPLOAD_NAME
    ]
    return sorted((_info(path) for path in paths), key=lambda item: item.name, reverse=True)


def get_full_backup(name: str) -> FullBackupInfo | None:
    if not _valid_name(name):
        return None
    path = get_full_backup_dir() / name
    if not path.is_file() or path.name == RESTORE_UPLOAD_NAME:
        return None
    return _info(path)


def stage_uploaded_full_backup(file_storage) -> Path:
    original = str(getattr(file_storage, "filename", "") or "").strip()
    if not original.lower().endswith(FULL_BACKUP_SUFFIX):
        raise ValueError("Нужен файл SG-Gateway с расширением .sgbackup")

    directory = get_full_backup_dir()
    destination = directory / RESTORE_UPLOAD_NAME
    temporary = directory / f".{RESTORE_UPLOAD_NAME}.tmp"
    temporary.unlink(missing_ok=True)

    total = 0
    with temporary.open("wb") as handle:
        while True:
            chunk = file_storage.stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                handle.close()
                temporary.unlink(missing_ok=True)
                raise ValueError("Полный backup больше допустимых 512 MiB")
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())

    if total < 128:
        temporary.unlink(missing_ok=True)
        raise ValueError("Файл backup пустой или повреждён")

    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)
    return destination
