from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.config import load_config

JOB_ID_RE = re.compile(r"^[0-9]{14}-[0-9a-f]{12}$")
_STAGE_RE = re.compile(r"\[SG-Gateway Update\] \[(\d+)/6\]\s+(.+)")
_ERROR_RE = re.compile(r"\[SG-Gateway Update\] ERROR:\s*(.+)")
_EXIT_RE = re.compile(r"\[SG-Gateway\] ОШИБКА: код\s+(\d+)")
_VERSION_RE = re.compile(r"\[SG-Gateway Update\] VERSION:\s*(\S+)")
_BASELINE_RE = re.compile(r"Panel Update baseline:\s*([0-9a-f]{7,40})\s*\(([^)]+)\)")
_BACKUP_RE = re.compile(r"ROLLBACK OK\.\s*Backup:\s*(\S+)")


def _jobs_dir() -> Path:
    override = os.getenv("SG_GATEWAY_OPERATION_JOB_DIR", "").strip()
    return Path(override) if override else load_config().log_dir / "operation-jobs"


def _legacy_jobs_dir() -> Path:
    return load_config().data_dir / "security" / "jobs"


def _job_roots() -> tuple[Path, ...]:
    primary = _jobs_dir()
    if os.getenv("SG_GATEWAY_OPERATION_JOB_DIR", "").strip():
        return (primary,)
    legacy = _legacy_jobs_dir()
    return (primary,) if legacy == primary else (primary, legacy)


def _panel_update_result(status: str, log: str) -> dict[str, Any]:
    stages = list(_STAGE_RE.finditer(log))
    stage_number = int(stages[-1].group(1)) if stages else 0
    stage_label = stages[-1].group(2).strip() if stages else "Подготовка"

    errors = list(_ERROR_RE.finditer(log))
    reason = errors[-1].group(1).strip() if errors else ""
    exits = list(_EXIT_RE.finditer(log))
    exit_code = int(exits[-1].group(1)) if exits else (0 if status == "success" else None)

    versions = list(_VERSION_RE.finditer(log))
    version = versions[-1].group(1).strip() if versions else ""
    baselines = list(_BASELINE_RE.finditer(log))
    commit = baselines[-1].group(1).strip() if baselines else ""
    channel = baselines[-1].group(2).strip() if baselines else ""

    rollback_started = "[SG-Gateway Update] ROLLBACK:" in log
    rollback_ok = "[SG-Gateway Update] ROLLBACK OK." in log
    backups = list(_BACKUP_RE.finditer(log))
    backup = backups[-1].group(1).strip() if backups else ""

    stage6_ok = "[SG-Gateway Update] [OK] Проверка HTTPS, Clients, Nginx и runtime" in log
    checks = {
        "panel": "ok" if status == "success" and stage6_ok else "unknown",
        "clients": "ok" if status == "success" and stage6_ok else "unknown",
        "https": "ok" if status == "success" and stage6_ok else "unknown",
    }

    restored = ""
    if rollback_ok:
        restored = (
            "Восстановлены код SG-Gateway, конфигурация, база и клиенты, HTTPS/TLS, "
            "Nginx, AWG3 runtime и исходные состояния служб."
        )
    elif rollback_started:
        restored = "Rollback был запущен, но в журнале нет подтверждения его завершения."
    elif status == "failed":
        restored = "Safety Backup ещё не был применён или rollback не требовался."

    tail_lines = [line for line in log.splitlines() if line.strip()][-18:]
    return {
        "stage_number": stage_number,
        "stage_label": stage_label,
        "reason": reason,
        "exit_code": exit_code,
        "version": version,
        "commit": commit,
        "channel": channel,
        "rollback_started": rollback_started,
        "rollback_ok": rollback_ok,
        "backup": backup,
        "restored": restored,
        "checks": checks,
        "log_tail": "\n".join(tail_lines),
    }


def read_job(job_id: str) -> dict[str, Any]:
    if not JOB_ID_RE.fullmatch(job_id or ""):
        raise FileNotFoundError(job_id)

    root = None
    meta_path = None
    for candidate in _job_roots():
        current = candidate / f"{job_id}.json"
        if current.is_file():
            root = candidate
            meta_path = current
            break
    if root is None or meta_path is None:
        raise FileNotFoundError(job_id)

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise FileNotFoundError(job_id) from exc
    try:
        status = (root / f"{job_id}.status").read_text(encoding="utf-8").strip()
    except OSError:
        status = "queued"
    try:
        log = (root / f"{job_id}.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        log = ""

    payload: dict[str, Any] = {
        **meta,
        "job_id": job_id,
        "status": status or "queued",
        "log": log[-240000:],
    }
    if str(meta.get("kind") or "") == "panel_update_channel":
        payload["update_result"] = _panel_update_result(payload["status"], log)
    return payload
