from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/sg-device-collapse-v1.js"


def _source() -> str:
    return JS.read_text(encoding="utf-8")


def test_device_protocol_order_matches_certificate_availability() -> None:
    body = _source()
    match = re.search(r"const protocolOrder = \[(.*?)\];", body, re.DOTALL)
    assert match is not None
    assert re.findall(r"'([^']+)'", match.group(1)) == [
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "amneziawg",
        "amneziawg3",
        "amneziawg31",
        "mihomo",
        "xray_xhttp_tls",
        "xray_hysteria2",
        "anytls",
        "tuic",
    ]


def test_device_dialog_uses_client_visual_contract() -> None:
    body = _source()
    required = (
        "sg-unified-dialog",
        "sg-unified-client-device-dialog-v1",
        "repeat(5,minmax(0,1fr))",
        "repeat(2,minmax(0,1fr))",
        "addDialog.querySelector('.dv16-recommended')?.remove()",
        "picker.replaceWith(...picker.childNodes)",
        "#dv-edit-client-dialog, [id^=\"dv-edit-device-\"]",
    )
    for token in required:
        assert token in body


def test_awg_only_warning_is_preserved_for_device_forms() -> None:
    body = _source()
    assert "При выборе только AWG-профилей подписка не создаётся." in body
    assert "Используйте QR-коды или файлы конфигурации для каждого соединения." in body
    assert "selected.length > 0 && selected.every" in body
    assert "amneziawg31" in body
