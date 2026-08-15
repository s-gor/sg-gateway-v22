from pathlib import Path


def test_client_detail_loads_qr_modal_override():
    template = Path("app/web/templates/client_detail.html").read_text(encoding="utf-8")
    assert "sg-client-qr-modal-v1.css" in template


def test_qr_modal_escapes_clipped_page_frame():
    css = Path("app/web/static/sg-client-qr-modal-v1.css").read_text(encoding="utf-8")
    assert ".dv16-qr[open] .dv16-qr-popover" in css
    assert "position: fixed !important" in css
    assert "z-index: 9999 !important" in css
    assert "translate(-50%, -50%)" in css
    assert ".dv16-qr[open]::before" in css
