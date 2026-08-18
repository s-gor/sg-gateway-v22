from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / 'app/web/static/sg-low-resolution-v1.css'
BASE = ROOT / 'app/web/templates/base.html'

def test_accepted_low_resolution_css_is_preserved_exactly() -> None:
    body = CSS.read_text(encoding='utf-8')
    assert '@media (min-width: 981px) and (max-width: 1366px),' in body
    assert '(min-width: 981px) and (max-height: 820px)' in body
    assert '@media (min-width: 761px) and (max-width: 980px)' in body
    assert 'never removes actions' in body
    assert 'display: none' not in body

def test_low_resolution_css_is_source_native_and_ordered_after_mobile_sidebar() -> None:
    body = BASE.read_text(encoding='utf-8')
    mobile = "filename='sg-mobile-sidebar-v1.css'"
    low = "filename='sg-low-resolution-v1.css'"
    assert body.count(mobile) == 1
    assert body.count(low) == 1
    assert body.index(mobile) < body.index(low)
    assert 'low-resolution-v1' in body
    assert not (ROOT / 'deploy/sg-gateway-02204-low-resolution.sh').exists()

def test_low_resolution_recovery_preserves_current_runtime_features() -> None:
    base = BASE.read_text(encoding='utf-8')
    connections = (ROOT / 'app/web/templates/connections.html').read_text(encoding='utf-8')
    assert (ROOT / 'app/xray/xmux.py').exists()
    assert 'sg-xmux-settings-v1.js' in connections
    assert 'value="gecko"' in connections
    assert (ROOT / 'app/production.py').exists()
    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').is_file()
    assert 'sg-low-resolution-v1.css' in base
