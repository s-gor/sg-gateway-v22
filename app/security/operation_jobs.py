from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.config import load_config

JOB_ID_RE = re.compile(r"^[0-9]{14}-[0-9a-f]{12}$")


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
    return {**meta, "job_id": job_id, "status": status or "queued", "log": log[-240000:]}
