from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence

from sg_hostd.operation_jobs import _start


DATA_DIR = Path(os.getenv("SG_GATEWAY_DATA_DIR", "/var/lib/sg-gateway"))
JOB_DIR = Path(
    os.getenv("SG_GATEWAY_OPERATION_JOB_DIR", "/var/log/sg-gateway/operation-jobs")
)
STALE_JOB_DAYS = 14


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(max(0, int(value)))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(value)} B"


def _usage():
    target = DATA_DIR if DATA_DIR.exists() else Path("/")
    return shutil.disk_usage(str(target))


def _run_command(label: str, command: Sequence[str], timeout: int = 180) -> bool:
    print(f"[Disk Cleanup] {label}", flush=True)
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[Disk Cleanup] ПРЕДУПРЕЖДЕНИЕ: {exc}", flush=True)
        return False

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        print(stdout[-12000:], flush=True)
    if stderr:
        print(stderr[-12000:], flush=True)
    if result.returncode:
        print(
            f"[Disk Cleanup] ПРЕДУПРЕЖДЕНИЕ: команда завершилась с кодом {result.returncode}",
            flush=True,
        )
        return False
    return True


def _cleanup_old_job_files(days: int = STALE_JOB_DAYS) -> tuple[int, int]:
    cutoff = time.time() - max(1, int(days)) * 86400
    removed = 0
    removed_bytes = 0
    if not JOB_DIR.is_dir():
        return removed, removed_bytes

    for path in JOB_DIR.iterdir():
        if path.suffix not in {".json", ".status", ".log", ".sh"}:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if not path.is_file() or stat.st_mtime >= cutoff:
            continue
        try:
            path.unlink()
        except OSError as exc:
            print(
                f"[Disk Cleanup] ПРЕДУПРЕЖДЕНИЕ: не удалось удалить {path.name}: {exc}",
                flush=True,
            )
            continue
        removed += 1
        removed_bytes += max(0, int(stat.st_size))

    return removed, removed_bytes


def run_disk_cleanup() -> int:
    before = _usage()
    print("[Disk Cleanup] Безопасная очистка диска SG-Gateway", flush=True)
    print(
        f"[Disk Cleanup] До очистки: занято {_format_bytes(before.used)}, "
        f"свободно {_format_bytes(before.free)}",
        flush=True,
    )
    print(
        "[Disk Cleanup] Бэкапы, база данных, GeoFiles, клиенты и конфигурации "
        "не затрагиваются.",
        flush=True,
    )

    if shutil.which("apt-get"):
        _run_command("[1/4] Очищаю кэш загруженных пакетов APT", ("apt-get", "clean"))
    else:
        print("[Disk Cleanup] [1/4] APT не найден — пропускаю", flush=True)

    if shutil.which("journalctl"):
        _run_command(
            "[2/4] Удаляю systemd journal старше 7 дней",
            ("journalctl", "--vacuum-time=7d"),
        )
    else:
        print("[Disk Cleanup] [2/4] journalctl не найден — пропускаю", flush=True)

    if shutil.which("systemd-tmpfiles"):
        _run_command(
            "[3/4] Очищаю временные файлы по системным правилам",
            ("systemd-tmpfiles", "--clean"),
        )
    else:
        print("[Disk Cleanup] [3/4] systemd-tmpfiles не найден — пропускаю", flush=True)

    removed, removed_bytes = _cleanup_old_job_files()
    print(
        f"[Disk Cleanup] [4/4] Старые терминальные задачи SG-Gateway: "
        f"удалено {removed} файлов ({_format_bytes(removed_bytes)})",
        flush=True,
    )

    after = _usage()
    freed = max(0, int(after.free) - int(before.free))
    print(
        f"[Disk Cleanup] После очистки: занято {_format_bytes(after.used)}, "
        f"свободно {_format_bytes(after.free)}",
        flush=True,
    )
    print(f"[Disk Cleanup] Освобождено: {_format_bytes(freed)}", flush=True)
    print("[Disk Cleanup] Готово. Можно вернуться в Maintenance.", flush=True)
    return 0


def start_disk_cleanup_job() -> dict:
    return _start(
        "disk_cleanup",
        "Очистка диска SG-Gateway",
        "/maintenance?tab=backups",
        "/maintenance?tab=backups",
        {"restart_expected": False},
    )