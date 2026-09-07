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
    assert 'wait_for_required_service "$service"' in recovery
    assert 'ROLLBACK INCOMPLETE' in recovery
    assert 'ROLLBACK VERIFIED' in recovery
    assert 'return "$recovery_failed"' in recovery


def test_02207_wrapper_waits_for_real_hostd_readiness_not_transient_active_state():
    source = WRAPPER.read_text(encoding="utf-8")
    waiter = _shell_function(source, "wait_for_required_service")

    assert 'HOSTD_HEALTH_URL="http://127.0.0.1:8090/health"' in source
    assert 'systemctl is-active --quiet "$service"' in waiter
    assert '"$HOSTD_HEALTH_URL"' in waiter
    assert "curl -4fsS" in waiter
    assert "sleep" in waiter
    assert "return 1" in waiter


def test_02207_wrapper_installs_exact_hostd_bridge_before_base_preflight():
    source = WRAPPER.read_text(encoding="utf-8")
    bridge = _shell_function(source, "prepare_hostd_preflight_bridge")
    runner = _shell_function(source, "run_panel_update")

    assert 'REQUESTED_SOURCE_COMMIT="${SG_GATEWAY_SOURCE_COMMIT:-}"' in source
    assert 'hostd/systemd/sg-hostd.service' in bridge
    assert '${REQUESTED_SOURCE_COMMIT}' in bridge
    assert 'Environment=PYTHONPATH=/opt/sg-gateway:/opt/sg-gateway/hostd' in bridge
    assert 'install -o root -g root -m 0644 "$staged" "$HOSTD_UNIT"' in bridge
    assert 'systemctl daemon-reload' in bridge
    assert 'systemctl restart "$HOSTD_SERVICE"' in bridge
    assert 'wait_for_required_service "$HOSTD_SERVICE"' in bridge
    assert runner.index("prepare_hostd_preflight_bridge") < runner.index(
        "prepare_panel_update_core"
    ) < runner.index("bash -c")


def test_02207_wrapper_checks_recovery_when_base_updater_fails():
    source = WRAPPER.read_text(encoding="utf-8")
    runner = _shell_function(source, "run_panel_update")

    assert "set +e" in runner
    assert 'SG_GATEWAY_GITHUB_BRANCH="$BRANCH"' in runner
    assert "prepare_panel_update_core" in runner
    assert "SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1" in runner
    assert "bash -c" in runner
    assert "panel_rc=$?" in runner
    assert "set -e" in runner
    assert "if (( panel_rc != 0 )); then" in runner
    assert "recover_required_services_after_panel_failure" in runner
    assert 'return "$panel_rc"' in runner


def test_02207_main_flow_uses_guarded_panel_update_runner():
    source = WRAPPER.read_text(encoding="utf-8")
    marker = "capture_naive_prestate\nrun_panel_update\nresolve_safety_backup"

    assert marker in source
