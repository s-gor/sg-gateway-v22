from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        source,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_02207_wrapper_recovers_required_services_after_base_update_failure():
    source = WRAPPER.read_text(encoding="utf-8")
    recovery = _shell_function(source, "recover_required_services_after_panel_failure")

    assert 'for service in "$HOSTD_SERVICE" "$PANEL_SERVICE"' in recovery
    assert 'if ! systemctl is-active --quiet "$service"' in recovery
    assert 'if ! systemctl start "$service"' in recovery
    assert 'ROLLBACK INCOMPLETE' in recovery
    assert 'ROLLBACK VERIFIED' in recovery
    assert 'return "$recovery_failed"' in recovery


def test_02207_wrapper_checks_recovery_when_base_updater_fails():
    source = WRAPPER.read_text(encoding="utf-8")
    runner = _shell_function(source, "run_panel_update")

    assert "set +e" in runner
    assert 'SG_GATEWAY_GITHUB_BRANCH="$BRANCH" bash "$PREFIX/deploy/update-from-github.sh"' in runner
    assert "panel_rc=$?" in runner
    assert "set -e" in runner
    assert "if (( panel_rc != 0 )); then" in runner
    assert "recover_required_services_after_panel_failure" in runner
    assert 'return "$panel_rc"' in runner


def test_02207_main_flow_uses_guarded_panel_update_runner():
    source = WRAPPER.read_text(encoding="utf-8")
    marker = "capture_naive_prestate\nrun_panel_update\nresolve_safety_backup"

    assert marker in source
