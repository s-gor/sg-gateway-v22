from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_clean_and_update_wrappers_pass_dev_channel_into_transaction():
    clean = (ROOT / "deploy/install-from-github-02207.sh").read_text()
    update = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    assert 'SG_GATEWAY_UPDATE_BRANCH="$BRANCH"' in clean
    assert 'SG_GATEWAY_UPDATE_BRANCH="$BRANCH"' in update
    assert clean.index('SG_GATEWAY_UPDATE_BRANCH="$BRANCH"') < clean.index(
        'bash "$patched_installer"'
    )
    assert update.index('SG_GATEWAY_UPDATE_BRANCH="$BRANCH"') < update.index(
        'bash "$PREFIX/deploy/install-naiveproxy.sh"'
    )


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
