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

    # Recovery state is retained and rooted on uninstall. Caddy's own private
    # XDG state is disposable here because SG-Gateway supplies the TLS cert/key,
    # so it must be separated from recovery state and recreated writable.
    assert 'chown -R root:root "$STATE_DIR"' in uninstaller
    assert 'rm -rf -- "$STATE_DIR/xdg-data" "$STATE_DIR/xdg-config"' in uninstaller

    assert f"Environment=HOME={STATE_DIR}" in service
    assert f"Environment=XDG_DATA_HOME={STATE_DIR}/xdg-data" in service
    assert f"Environment=XDG_CONFIG_HOME={STATE_DIR}/xdg-config" in service

    assert 'CADDY_DATA_HOME="$STATE_DIR/xdg-data"' in installer
    assert 'CADDY_CONFIG_HOME="$STATE_DIR/xdg-config"' in installer
    assert (
        'install -d -o sg-naiveproxy -g sg-naiveproxy -m 0700 '
        '"$CADDY_DATA_HOME" "$CADDY_CONFIG_HOME"'
    ) in installer
