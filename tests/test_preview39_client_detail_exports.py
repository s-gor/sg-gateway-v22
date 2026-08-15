from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preview39_client_detail_layout_and_copy_fallback():
    template = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-client-detail-v10.css").read_text(encoding="utf-8")
    assert "async function copyText" in template
    assert "document.execCommand('copy')" in template
    assert "grid-template-columns: repeat(2,minmax(0,1fr));" in css or "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "width: min(86vw, 334px);" in css
    assert "width: min(76vw, 292px);" in css


def test_preview40_mieru_keeps_working_profile_and_client_name():
    exports = (ROOT / "app/clients/exports.py").read_text(encoding="utf-8")
    assert '"profile": "default"' in exports
    assert "#{quote(_label(client, device), safe='')}" in exports
