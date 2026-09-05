from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing expected test block: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    cumulative = Path("tests/test_sg_gateway_02110_cumulative.py")
    replace_once(
        cumulative,
        '''    assert "SG_DEVICE_COLLAPSE_V4_LAST_CSS" in base\n    assert base.index("SG_DEVICE_COLLAPSE_V4_LAST_CSS") > base.index("sg-mobile-sidebar-v1.css")\n    assert "sg-device-collapse-v1.js" in detail\n''',
        '''    clients = source("app/web/templates/clients.html")\n    assert "SG_DEVICE_COLLAPSE_V4_LAST_CSS" not in base\n    assert "{{ static_asset('sg-device-collapse-v4.css') }}" in clients\n    assert "{{ static_asset('sg-device-expanded-cleanup-v1.css') }}" in clients\n    assert "{{ static_asset('sg-device-collapse-v4.css') }}" in detail\n    assert "sg-device-collapse-v1.js" in detail\n''',
        "cumulative device css ownership",
    )

    publication = Path("tests/test_sg_gateway_021_full_publication_ru.py")
    replace_once(
        publication,
        '''def test_client_detail_uses_routing_frame_and_title_size():\n    css = (ROOT / "app/web/static/sg-page-frame-routing-v1.css").read_text(\n        encoding="utf-8"\n    )\n\n    assert "client detail uses the exact Routing page frame" in css\n    assert ".dv16-page" in css\n    assert ".dv16-heading h1" in css\n    assert "font-size: 27px !important" in css\n''',
        '''def test_client_detail_uses_02208_canonical_page_frame():\n    frame = (ROOT / "app/web/static/sg-page-frame-routing-v1.css").read_text(encoding="utf-8")\n    template = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")\n    clients_css = (ROOT / "app/web/static/sg-ui-clients-v22-08.css").read_text(encoding="utf-8")\n\n    assert ".dv16-page" not in frame\n    assert 'data-sg-ui-page="client-detail"' in template\n    assert 'class="dv16-heading sg-ui-page-head"' in template\n    assert '[data-sg-ui-page="client-detail"]' in clients_css\n''',
        "client detail routing-frame test",
    )

    picker = Path("tests/test_sg_gateway_v22_awg31_client_picker.py")
    replace_once(
        picker,
        '''    assert "devices-collapse-v4-dialog-layout-v2" in clients\n    assert "devices-collapse-v4-dialog-layout-v2" in (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")\n''',
        '''    dialogs = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")\n    assert "devices-collapse-v4-dialog-layout-v2" not in clients\n    assert "devices-collapse-v4-dialog-layout-v2" not in dialogs\n    assert "{{ static_asset('sg-device-collapse-v4.css') }}" in clients\n    assert "<link rel=\\\"stylesheet\\\"" not in dialogs\n''',
        "responsive picker asset ownership",
    )

    dual = Path("tests/test_sg_gateway_v22_sg_subscription_dual_ui.py")
    replace_once(
        dual,
        '''    devices = '<section class="dv16-devices" aria-label="Устройства клиента">'\n    assert text.count(marker) == 1\n    assert text.count(include) == 1\n    assert text.index(marker) < text.index(include) < text.index(devices)\n''',
        '''    devices = 'data-sg-section="devices"'\n    assert text.count(marker) == 1\n    assert text.count(include) == 1\n    assert text.index(marker) < text.index(include) < text.index(devices)\n''',
        "dual subscription placement selector",
    )


if __name__ == "__main__":
    main()
