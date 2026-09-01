from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_naiveproxy_runtime_installer_restores_every_managed_path_on_error():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert "trap rollback_install ERR" in source
    assert 'snapshot_path "$PREFIX" prefix HAD_PREFIX' in source
    assert 'snapshot_path "$CONFIG_DIR" config HAD_CONFIG' in source
    assert 'snapshot_path "$STATE_DIR" state HAD_STATE' in source
    assert 'snapshot_path "$SERVICE_PATH" unit HAD_UNIT' in source
    assert 'restore_path "$PREFIX" prefix "$HAD_PREFIX"' in source
    assert 'restore_path "$CONFIG_DIR" config "$HAD_CONFIG"' in source
    assert 'restore_path "$STATE_DIR" state "$HAD_STATE"' in source
    assert 'restore_path "$SERVICE_PATH" unit "$HAD_UNIT"' in source


def test_naiveproxy_runtime_installer_restores_identity_and_service_state():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert "HAD_USER" in source
    assert "HAD_GROUP" in source
    assert "WAS_ACTIVE" in source
    assert "WAS_ENABLED" in source
    assert "userdel sg-naiveproxy" in source
    assert "groupdel sg-naiveproxy" in source
    assert 'systemctl start "$SERVICE"' in source
    assert 'systemctl disable "$SERVICE"' in source


def test_clean_install_injects_naiveproxy_before_installer_success_boundary():
    source = (ROOT / "deploy/install-from-github-02207.sh").read_text()
    assert 'marker = "  INSTALL_SUCCESS=1\\n"' in source
    assert "cannot locate unique installer success boundary" in source
    assert "source.replace(marker, hook + marker)" in source
    assert 'bash "$patched_installer"' in source
    assert 'bash "$TMP/source/install.sh"' not in source


def test_clean_install_does_not_run_naiveproxy_after_successful_main_install():
    source = (ROOT / "deploy/install-from-github-02207.sh").read_text()
    post_install = source.split('bash "$patched_installer"', 1)[1]
    assert "install-naiveproxy.sh" not in post_install
    assert "ufw allow 8447/tcp ||" in post_install
