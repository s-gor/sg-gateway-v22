from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATE_CORE = (ROOT / "deploy/update-from-github-core.sh").read_text(encoding="utf-8")


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
