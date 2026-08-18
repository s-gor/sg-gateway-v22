from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config
from app.db import get_database_path, init_db
from app.maintenance.operations import log_operation


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    size_bytes: int
    created_at: str
    kind: str


@dataclass(frozen=True)
class RestoreResult:
    ok: bool
    backup: BackupInfo | None
    safety_backup: BackupInfo | None
    message: str


@dataclass(frozen=True)
class BackupCleanupPreview:
    total_count: int
    total_size_bytes: int
    delete_count: int
    delete_size_bytes: int
    keep_count: int
    total_size_label: str
    delete_size_label: str


@dataclass(frozen=True)
class BackupCleanupResult:
    deleted_count: int
    freed_bytes: int
    kept_count: int
    failed_names: tuple[str, ...]


BACKUP_RETENTION = 2


def get_backup_dir() -> Path:
    directory = load_config().data_dir / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _next_backup_path(prefix: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = get_backup_dir()
    candidate = backup_dir / f"{prefix}-{timestamp}.sqlite"
    counter = 1
    while candidate.exists():
        candidate = backup_dir / f"{prefix}-{timestamp}-{counter}.sqlite"
        counter += 1
    return candidate


def create_backup() -> BackupInfo:
    init_db()
    source = get_database_path()
    destination = _next_backup_path("sg-gateway")
    shutil.copy2(source, destination)
    backup = _backup_info(destination)
    log_operation("backup.create", f"backup:{backup.name}", f"Создана резервная копия {backup.name}")
    return backup


def list_backups() -> list[BackupInfo]:
    backup_dir = get_backup_dir()
    paths = [
        *backup_dir.glob("sg-gateway-*.sqlite"),
        *backup_dir.glob("pre-restore-*.sqlite"),
    ]
    backups = [_backup_info(path) for path in paths]
    return sorted(backups, key=lambda item: item.name, reverse=True)


def backup_cleanup_preview(backups: list[BackupInfo] | None = None) -> BackupCleanupPreview:
    backups = list_backups() if backups is None else backups
    old_backups = backups[BACKUP_RETENTION:]
    total_size = sum(item.size_bytes for item in backups)
    delete_size = sum(item.size_bytes for item in old_backups)
    return BackupCleanupPreview(
        total_count=len(backups),
        total_size_bytes=total_size,
        delete_count=len(old_backups),
        delete_size_bytes=delete_size,
        keep_count=min(len(backups), BACKUP_RETENTION),
        total_size_label=_format_size(total_size),
        delete_size_label=_format_size(delete_size),
    )


def delete_old_backups() -> BackupCleanupResult:
    backups = list_backups()
    old_backups = backups[BACKUP_RETENTION:]
    deleted_count = 0
    freed_bytes = 0
    failed_names: list[str] = []

    for backup in old_backups:
        try:
            backup.path.unlink()
        except OSError:
            failed_names.append(backup.name)
            continue
        deleted_count += 1
        freed_bytes += backup.size_bytes

    kept_count = len(backups) - deleted_count
    status = "error" if failed_names else "ok"
    message = (
        f"Удалены старые резервные копии: {deleted_count}; "
        f"освобождено {freed_bytes} B; сохранено последних: {kept_count}"
    )
    if failed_names:
        message += f"; не удалены: {', '.join(failed_names)}"
    log_operation("backup.cleanup", "backup:old", message, status=status)
    return BackupCleanupResult(
        deleted_count=deleted_count,
        freed_bytes=freed_bytes,
        kept_count=kept_count,
        failed_names=tuple(failed_names),
    )


def get_backup(name: str) -> BackupInfo | None:
    if "/" in name or "\\" in name or ".." in name:
        return None

    path = get_backup_dir() / name
    if not path.exists() or not path.is_file():
        return None

    return _backup_info(path)


def restore_backup_transaction(name: str) -> RestoreResult:
    """Restore the database and return the pre-restore safety copy.

    Runtime application is intentionally performed by the caller. If the
    rebuilt Xray candidate fails, restore_safety_backup() returns the database
    to the exact state that existed before this restore attempt.
    """
    backup = get_backup(name)
    if backup is None:
        message = "Резервная копия не найдена"
        log_operation("backup.restore", f"backup:{name}", message, status="error")
        return RestoreResult(False, None, None, message)

    target = get_database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    safety: BackupInfo | None = None
    if target.exists():
        safety_path = _next_backup_path("pre-restore")
        shutil.copy2(target, safety_path)
        safety = _backup_info(safety_path)

    try:
        shutil.copy2(backup.path, target)
        init_db()
    except Exception as exc:
        if safety is not None and safety.path.is_file():
            shutil.copy2(safety.path, target)
            init_db()
        message = f"Не удалось восстановить базу: {exc}"
        log_operation("backup.restore", f"backup:{backup.name}", message, status="error")
        return RestoreResult(False, backup, safety, message)

    message = f"База восстановлена из {backup.name}; ожидается проверка runtime"
    log_operation("backup.restore.stage", f"backup:{backup.name}", message)
    return RestoreResult(True, backup, safety, message)


def restore_safety_backup(safety: BackupInfo | str | None) -> bool:
    if safety is None:
        return False
    info = safety if isinstance(safety, BackupInfo) else get_backup(str(safety))
    if info is None or not info.path.is_file():
        return False
    target = get_database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(info.path, target)
    init_db()
    log_operation(
        "backup.restore.rollback",
        f"backup:{info.name}",
        "Восстановление отменено; возвращена страховочная база",
    )
    return True


def confirm_restore_runtime(name: str) -> None:
    log_operation(
        "backup.restore",
        f"backup:{name}",
        f"Восстановлена резервная копия {name}; Xray candidate проверен и применён",
    )


def restore_backup(name: str) -> bool:
    """Backward-compatible database-only restore used by existing callers/tests."""
    result = restore_backup_transaction(name)
    if not result.ok or result.backup is None:
        return False
    log_operation(
        "backup.restore",
        f"backup:{result.backup.name}",
        f"Восстановлена резервная копия {result.backup.name}",
    )
    return True


def _backup_kind(path: Path) -> str:
    if path.name.startswith("pre-restore-"):
        return "Страховочная копия перед восстановлением"
    return "Ручная резервная копия"


def _backup_info(path: Path) -> BackupInfo:
    stat = path.stat()
    created_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return BackupInfo(
        name=path.name,
        path=path,
        size_bytes=stat.st_size,
        created_at=created_at,
        kind=_backup_kind(path),
    )


def _format_size(size_bytes: int) -> str:
    value = float(max(0, size_bytes))
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} Б"
