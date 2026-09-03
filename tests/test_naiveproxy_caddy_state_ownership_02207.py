from pathlib import Path


ROOT = Path(__file__).parents[1]
SERVICE = ROOT / "deploy" / "sg-gateway-naiveproxy.service"
INSTALLER = ROOT / "deploy" / "install-naiveproxy.sh"
UNINSTALLER = ROOT / "deploy" / "uninstall-naiveproxy.sh"
STATE_DIR = "/var/lib/sg-gateway/naiveproxy"


def test_reinstall_reclaims_private_caddy_state_after_retained_state_is_rooted():
    service = SERVICE.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    uninstaller = UNINSTALLER.read_text(encoding="utf-8")

    # Uninstall deliberately retains recovery state and roots it, so a later
    # install must not rely on stale ~/.local or ~/.config ownership.
    assert 'chown -R root:root "$STATE_DIR"' in uninstaller

    assert f"Environment=HOME={STATE_DIR}" in service
    assert f"Environment=XDG_DATA_HOME={STATE_DIR}/xdg-data" in service
    assert f"Environment=XDG_CONFIG_HOME={STATE_DIR}/xdg-config" in service

    assert 'CADDY_DATA_HOME="$STATE_DIR/xdg-data"' in installer
    assert 'CADDY_CONFIG_HOME="$STATE_DIR/xdg-config"' in installer
    assert (
        'install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 '
        '"$CADDY_DATA_HOME" "$CADDY_CONFIG_HOME"'
    ) in installer
    assert (
        'chown -R sg-naiveproxy:sg-naiveproxy '
        '"$CADDY_DATA_HOME" "$CADDY_CONFIG_HOME"'
    ) in installer
