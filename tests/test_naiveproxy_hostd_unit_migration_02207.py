from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_runtime_installer_installs_naiveproxy_capable_hostd_unit():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'HOSTD_SERVICE="sg-hostd.service"' in source
    assert 'HOSTD_SERVICE_PATH="/etc/systemd/system/$HOSTD_SERVICE"' in source
    assert '"$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE"' in source
    assert 'install -m 0644 "$SOURCE_ROOT/hostd/systemd/$HOSTD_SERVICE" "$HOSTD_SERVICE_PATH"' in source
    assert 'systemctl restart "$HOSTD_SERVICE"' in source
    assert 'systemctl is-active --quiet "$HOSTD_SERVICE"' in source


def test_runtime_installer_rolls_back_hostd_unit_and_state():
    source = (ROOT / "deploy/install-naiveproxy.sh").read_text()
    assert 'snapshot_path "$HOSTD_SERVICE_PATH" hostd-unit HAD_HOSTD_UNIT' in source
    assert 'restore_path "$HOSTD_SERVICE_PATH" hostd-unit "$HAD_HOSTD_UNIT"' in source
    assert 'HOSTD_WAS_ACTIVE' in source
    assert 'HOSTD_WAS_ENABLED' in source
    assert 'restore_service_state "$HOSTD_SERVICE" "$HOSTD_WAS_ENABLED" "$HOSTD_WAS_ACTIVE"' in source


def test_stable_hostd_sandbox_requires_02207_unit_migration():
    unit = (ROOT / "hostd/systemd/sg-hostd.service").read_text()
    assert "-/etc/sg-gateway/naiveproxy" in unit
    assert "-/var/lib/sg-gateway" in unit
