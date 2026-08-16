from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_gecko_contract_is_three_mode_and_requires_current_xray() -> None:
    body = (ROOT / 'app/xray/salamander.py').read_text(encoding='utf-8')
    assert 'GECKO_MODE = "gecko"' in body
    assert 'GECKO_MINIMUM_VERSION = "26.6.27"' in body
    assert 'GECKO_PACKET_SIZE = "512-1200"' in body
    assert 'SALAMANDER_MODES = (SALAMANDER_MODE_NONE, SALAMANDER_MODE, GECKO_MODE)' in body

def test_gecko_integration_preserves_xmux_alongside_isolated_awg3() -> None:
    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').is_file()
    assert (ROOT / 'deploy/sg-gateway-awg3.service').is_file()
    assert (ROOT / 'app/xray/xmux.py').is_file()
    connections = (ROOT / 'app/web/templates/connections.html').read_text(encoding='utf-8')
    assert 'sg-xmux-settings-v1.js' in connections
    assert 'value="gecko"' in connections
    exports = (ROOT / 'app/clients/exports.py').read_text(encoding='utf-8')
    assert 'obfs_mode in {"salamander", "gecko"}' in exports

def test_gecko_recovery_does_not_change_release_identity() -> None:
    assert (ROOT / 'VERSION').read_text(encoding='utf-8').strip() == '0.1.0-021.12'
    assert (ROOT / 'BUILD-ID').read_text(encoding='utf-8').strip() == 'MAIN-02112'
