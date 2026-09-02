from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
HOSTD_UNIT = ROOT / "hostd/systemd/sg-hostd.service"
OPERATION_JOBS = ROOT / "hostd/sg_hostd/operation_jobs.py"
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_operation_jobs_use_sg_gateway_log_tree():
    source = OPERATION_JOBS.read_text(encoding="utf-8")

    assert 'DEFAULT_JOB_DIR = "/var/log/sg-gateway/operation-jobs"' in source
    assert "JOB_DIR.mkdir(parents=True, exist_ok=True)" in source


def test_02207_hostd_sandbox_exposes_systemd_managed_log_directory():
    unit = HOSTD_UNIT.read_text(encoding="utf-8")

    assert "ProtectSystem=strict" in unit
    assert "LogsDirectory=sg-gateway" in unit


def test_02207_wrapper_rejects_hostd_unit_without_operation_job_log_access():
    source = WRAPPER.read_text(encoding="utf-8")
    preflight = _shell_function(source, "prepare_hostd_preflight_bridge")
    staged = _shell_function(source, "stage_naive_hostd_unit")

    assert "LogsDirectory=sg-gateway" in preflight
    assert "LogsDirectory=sg-gateway" in staged
