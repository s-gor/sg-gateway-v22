from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_uninstall_removes_only_managed_firewall_rule():
    source = (ROOT / "deploy/uninstall-naiveproxy.sh").read_text()
    assert 'firewall.get("managed") is not True' in source
    assert 'ufw --force delete allow "${managed_port}/tcp"' in source
    assert 'ufw --force reset' not in source


def test_uninstall_removes_runtime_identity_and_unit():
    source = (ROOT / "deploy/uninstall-naiveproxy.sh").read_text()
    assert 'systemctl disable --now "$SERVICE"' in source
    assert 'rm -f -- "$UNIT"' in source
    assert 'rm -rf -- "$PREFIX" "$CONFIG_DIR"' in source
    assert "userdel sg-naiveproxy" in source
    assert "groupdel sg-naiveproxy" in source


def test_uninstall_retains_recovery_state_without_stale_firewall_claim():
    source = (ROOT / "deploy/uninstall-naiveproxy.sh").read_text()
    assert 'rm -rf -- "$PREFIX" "$CONFIG_DIR"' in source
    assert 'rm -rf -- "$STATE_DIR"' not in source
    assert 'state["firewall"] = {"active": False, "managed": False, "port": None}' in source
    assert 'chown -R root:root "$STATE_DIR"' in source
