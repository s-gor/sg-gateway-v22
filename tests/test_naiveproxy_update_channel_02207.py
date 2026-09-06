from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_runtime_installer_accepts_current_02208_release_channels():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'stable-02208' in source
    assert 'release/02208-*' in source
    assert 'feature/02208-*' in source
    assert 'Refusing invalid 22.08 update channel' in source
    assert 'Refusing invalid 22.07 update channel' not in source


def test_runtime_installer_persists_channel_as_data_and_restarts_panel():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'PANEL_ENV="/etc/sg-gateway/sg-gateway.env"' in source
    assert 'key = "SG_GATEWAY_UPDATE_BRANCH"' in source
    assert "path.read_text" in source
    assert "source \"$PANEL_ENV\"" not in source
    assert 'os.replace(temporary, path)' in source
    assert 'systemctl restart "$PANEL_SERVICE"' in source
    assert 'systemctl is-active --quiet "$PANEL_SERVICE"' in source


def test_failed_channel_migration_restores_exact_env_and_service_state():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'snapshot_path "$PANEL_ENV" panel-env HAD_PANEL_ENV' in source
    assert 'restore_path "$PANEL_ENV" panel-env "$HAD_PANEL_ENV"' in source
    assert "PANEL_WAS_ACTIVE" in source
    assert "PANEL_WAS_ENABLED" in source
    assert 'restore_service_state "$PANEL_SERVICE" "$PANEL_WAS_ENABLED" "$PANEL_WAS_ACTIVE"' in source
    assert source.index("persist_update_channel") < source.index("INSTALL_OK=1")
