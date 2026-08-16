from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'app/web/static/sg-device-collapse-v1.js'
COLLAPSE = ROOT / 'app/web/static/sg-device-collapse-v4.css'
LIST_CSS = ROOT / 'app/web/static/sg-clients-readable-small-v1.css'
DEVICE_CSS = ROOT / 'app/web/static/sg-devices-v46.css'

def test_protocol_picker_is_unified_for_current_eight_protocols_only() -> None:
    body = JS.read_text(encoding='utf-8')
    expected = ['xray_reality_tcp','xray_xhttp_reality','xray_xhttp_tls','xray_hysteria2','amneziawg','amneziawg3','mihomo','anytls','tuic']
    for value in expected:
        assert f"'{value}'" in body
    assert 'protocolOrder' in body
    assert 'normalizeProtocolPickers()' in body
    assert 'picker.open = true' in body
    assert "setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0')" in body
    assert "setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0')" in body
    assert "setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR')" in body

def test_device_cards_start_collapsed_without_layout_jump() -> None:
    js = JS.read_text(encoding='utf-8')
    css = COLLAPSE.read_text(encoding='utf-8')
    assert "card.classList.toggle('sg-device-expanded', expanded)" in js
    assert 'setExpanded(card, button, false)' in js
    assert 'data-sg-collapse-ready="1"' in css
    assert '.dv16-device:not(.sg-device-expanded)' in css
    assert 'Reserve the toggle slot before deferred JS runs' in css

def test_disable_actions_are_protected_and_visually_distinct() -> None:
    js = JS.read_text(encoding='utf-8')
    css = DEVICE_CSS.read_text(encoding='utf-8')
    assert 'function prepareDisableActions()' in js
    assert "form.dataset.sgConfirmTitle = 'Отключить устройство'" in js
    assert "form.dataset.sgConfirmTitle = 'Отключить клиента'" in js
    assert "form.dataset.sgConfirmTone = 'warning'" in js
    assert "button.classList.add('sg-warm-action')" in js
    assert '.button.sg-warm-action' in css

def test_add_and_edit_protocol_grids_use_three_columns_with_responsive_fallback() -> None:
    add_css = LIST_CSS.read_text(encoding='utf-8')
    edit_css = DEVICE_CSS.read_text(encoding='utf-8')
    assert '#cv2-dialog.cv10-dialog .cv12-protocols' in add_css
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in add_css
    assert '.dv16-dialog .dv16-protocol-list' in edit_css
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in edit_css
    assert '@media(max-width:900px)' in edit_css
    assert '@media(max-width:620px)' in edit_css

def test_current_xmux_gecko_subscription_and_low_resolution_layers_survive() -> None:
    assert (ROOT / 'app/xray/xmux.py').exists()
    connections = (ROOT / 'app/web/templates/connections.html').read_text(encoding='utf-8')
    assert 'value="gecko"' in connections
    base = (ROOT / 'app/web/templates/base.html').read_text(encoding='utf-8')
    assert 'sg-low-resolution-v1.css' in base
    assert (ROOT / 'app/clients/sg_subscription_http_v4.py').exists()
    assert (ROOT / 'hostd/sg_hostd/awg3_runtime.py').exists()
