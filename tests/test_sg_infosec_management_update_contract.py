from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPDATE_CORE_PATH = ROOT / "deploy/update-from-github-core.sh"
COMPLETE_UPDATE_PATH = ROOT / "deploy/update-infosec-complete-from-github.sh"
UPDATE_CORE = UPDATE_CORE_PATH.read_text(encoding="utf-8")
COMPLETE_UPDATE = COMPLETE_UPDATE_PATH.read_text(encoding="utf-8")


def test_update_tracks_bridge_service_state():
    assert 'INFOSEC_SERVICE="sg-infosec.service"' in UPDATE_CORE
    assert 'INFOSEC_BRIDGE_SERVICE="sg-infosec-management-bridge.service"' in UPDATE_CORE
    assert '"$INFOSEC_BRIDGE_SERVICE"' in UPDATE_CORE
    assert '"$PANEL_SERVICE"|"$HOSTD_SERVICE"|"$AWG31_SERVICE"|"$INFOSEC_BRIDGE_SERVICE")' in UPDATE_CORE


def test_safety_backup_archives_bridge_external_files():
    for relative in (
        "etc/sg-infosec/sources.d/sg-gateway-management.yaml",
        "etc/systemd/system/sg-infosec-management-bridge.service",
        "usr/lib/tmpfiles.d/sg-infosec-management-bridge.conf",
    ):
        assert relative in UPDATE_CORE


def test_rollback_stops_bridge_and_removes_new_external_files():
    assert 'systemctl stop "$PANEL_SERVICE" "$HOSTD_SERVICE" "$INFOSEC_BRIDGE_SERVICE"' in UPDATE_CORE
    for variable in (
        '"$INFOSEC_BRIDGE_SOURCE"',
        '"$INFOSEC_BRIDGE_UNIT"',
        '"$INFOSEC_BRIDGE_TMPFILES"',
    ):
        assert variable in UPDATE_CORE


def test_rollback_reloads_restored_sg_infosec_role_state():
    assert 'systemctl is-active --quiet "$INFOSEC_SERVICE"' in UPDATE_CORE
    assert 'systemctl restart "$INFOSEC_SERVICE"' in UPDATE_CORE


def test_complete_update_activates_bridge_and_persistent_guard_paths():
    assert 'SOURCE_SHA="${SG_GATEWAY_SOURCE_COMMIT:-${1:-}}"' in COMPLETE_UPDATE
    assert 'SG_GATEWAY_SOURCE_COMMIT="$SOURCE_SHA"' in COMPLETE_UPDATE
    assert "app.security.sg_infosec_unit_migration" in COMPLETE_UPDATE
    assert '"$PREFIX/deploy/install-sg-infosec-management-bridge.sh"' in COMPLETE_UPDATE
    assert 'systemctl restart "$PANEL_SERVICE"' in COMPLETE_UPDATE
    assert '[[ -S /run/sg-infosec-bridge/management.sock ]]' in COMPLETE_UPDATE
    for environment in (
        "SG_INFOSEC_GUARD_SETTINGS=/var/lib/sg-gateway/infosec/guard.json",
        "SG_INFOSEC_REPUTATION_FILE=/var/lib/sg-gateway/infosec/reputation.json",
        "SG_INFOSEC_ALERTS_FILE=/var/lib/sg-gateway/infosec/alerts.jsonl",
    ):
        assert environment in COMPLETE_UPDATE


def test_complete_update_has_post_update_rollback_and_no_curl_pipe_bash():
    assert "rollback_integration()" in COMPLETE_UPDATE
    assert 'integration-state.tar' in COMPLETE_UPDATE
    assert 'restore_path "$PANEL_UNIT"' in COMPLETE_UPDATE
    assert 'restore_path "$BRIDGE_SOURCE"' in COMPLETE_UPDATE
    assert 'restore_path "$BRIDGE_UNIT"' in COMPLETE_UPDATE
    assert 'restore_path "$BRIDGE_TMPFILES"' in COMPLETE_UPDATE
    assert "bash -n \"$CORE\"" in COMPLETE_UPDATE
    assert "| bash" not in COMPLETE_UPDATE


def test_complete_update_shell_syntax_is_valid():
    subprocess.run(["bash", "-n", str(COMPLETE_UPDATE_PATH)], check=True)
