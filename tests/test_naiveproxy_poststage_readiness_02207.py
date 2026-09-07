from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def _run_naive_stage_with_readiness_result(hostd_rc: int, panel_rc: int) -> subprocess.CompletedProcess[str]:
    source = WRAPPER.read_text(encoding="utf-8")
    run_naive_stage = _shell_function(source, "run_naive_stage")
    script = f"""
set -u
PREFIX=/opt/sg-gateway
BRANCH=dev-02207
HOSTD_SERVICE=sg-hostd.service
PANEL_SERVICE=sg-gateway.service
stage_naive_hostd_unit() {{ return 0; }}
bash() {{ return 0; }}
wait_for_required_service() {{
  case "$1" in
    "$HOSTD_SERVICE") return {hostd_rc} ;;
    "$PANEL_SERVICE") return {panel_rc} ;;
    *) return 99 ;;
  esac
}}
dump_required_service_failure() {{ printf 'DIAG:%s\\n' "$1"; }}
log() {{ printf 'LOG:%s\\n' "$*"; }}
{run_naive_stage}
run_naive_stage
"""
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_post_naive_stage_refuses_success_when_hostd_is_not_ready():
    result = _run_naive_stage_with_readiness_result(hostd_rc=1, panel_rc=0)
    assert result.returncode != 0
    assert "DIAG:sg-hostd.service" in result.stdout


def test_post_naive_stage_refuses_success_when_panel_is_not_ready():
    result = _run_naive_stage_with_readiness_result(hostd_rc=0, panel_rc=1)
    assert result.returncode != 0
    assert "DIAG:sg-gateway.service" in result.stdout


def test_post_naive_stage_succeeds_only_after_both_required_services_are_ready():
    result = _run_naive_stage_with_readiness_result(hostd_rc=0, panel_rc=0)
    assert result.returncode == 0, result.stderr
