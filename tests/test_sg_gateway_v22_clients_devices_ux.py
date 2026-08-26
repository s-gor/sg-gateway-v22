from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/sg-device-collapse-v1.js"
COLLAPSE = ROOT / "app/web/static/sg-device-collapse-v4.css"
DEVICE_CSS = ROOT / "app/web/static/sg-devices-v46.css"


def test_protocol_picker_distinguishes_awg30_and_awg31() -> None:
    body = JS.read_text(encoding="utf-8")
    expected = ["xray_reality_tcp", "xray_xhttp_reality", "xray_xhttp_tls", "xray_hysteria2", "amneziawg", "amneziawg3", "amneziawg31", "mihomo", "anytls", "tuic"]
    for value in expected:
        assert f"'{value}'" in body
    assert "protocolOrder" in body
    assert "normalizeProtocolPickers()" in body
    assert "picker.open = true" in body
    assert "setLabelTitle(byValue.get('amneziawg'), 'AmneziaWG 2.0')" in body
    assert "setLabelTitle(byValue.get('amneziawg3'), 'AmneziaWG 3.0')" in body
    assert "setLabelTitle(byValue.get('amneziawg31'), 'AmneziaWG 3.1')" in body
    assert "setAvailableNote(byValue.get('amneziawg3'), 'UDP 586 · userspace-конфигурация и QR')" in body
    assert "setAvailableNote(byValue.get('amneziawg31'), 'UDP 587 · userspace-конфигурация')" in body


def test_device_cards_start_collapsed_without_layout_jump() -> None:
    js = JS.read_text(encoding="utf-8")
    css = COLLAPSE.read_text(encoding="utf-8")
    assert "card.classList.toggle('sg-device-expanded', expanded)" in js
    assert "setExpanded(card, button, false)" in js
    assert 'data-sg-collapse-ready="1"' in css
    assert ".dv16-device:not(.sg-device-expanded)" in css
    assert "Reserve the toggle slot before deferred JS runs" in css


def test_disable_actions_are_protected_and_visually_distinct() -> None:
    js = JS.read_text(encoding="utf-8")
    css = DEVICE_CSS.read_text(encoding="utf-8")
    assert "function prepareDisableActions()" in js
    assert "form.dataset.sgConfirmTitle = 'Отключить устройство'" in js
    assert "form.dataset.sgConfirmTitle = 'Отключить клиента'" in js
    assert "form.dataset.sgConfirmTone = 'warning'" in js
    assert "button.classList.add('sg-warm-action')" in js
    assert ".button.sg-warm-action" in css


def test_add_and_edit_protocol_grids_use_five_two_one_responsive_layout() -> None:
    css = COLLAPSE.read_text(encoding="utf-8")
    assert "SG_CLIENT_PROTOCOL_DIALOG_LAYOUT_V2" in css
    assert "#cv2-dialog.cv10-dialog" in css
    assert "max-width: 1120px !important;" in css
    assert ".dv16-dialog .dv16-protocol-list" in css
    assert "@media (min-width: 981px)" in css
    assert "grid-template-columns: repeat(5, minmax(0, 1fr)) !important;" in css
    assert "@media (min-width: 721px) and (max-width: 980px)" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important;" in css
    assert "@media (max-width: 720px)" in css
    assert "grid-template-columns: 1fr !important;" in css
    assert "grid-auto-rows: 1fr !important;" in css
    assert "grid-template-columns: 18px minmax(0, 1fr) !important;" in css


def test_current_xmux_gecko_subscription_and_low_resolution_layers_survive() -> None:
    assert (ROOT / "app/xray/xmux.py").exists()
    connections = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert 'value="gecko"' in connections
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    assert "sg-low-resolution-v1.css" in base
    assert (ROOT / "app/clients/sg_subscription_http_v4.py").exists()
    assert (ROOT / "hostd/sg_hostd/awg3_runtime.py").exists()
