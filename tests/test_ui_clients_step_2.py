from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_clients_page_uses_real_client_and_device_fields():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    for field in (
        "client.id",
        "client.name",
        "client.enabled",
        "client.expires_at",
        "client.device_count",
        "client.active_device_count",
    ):
        assert field in template


def test_clients_page_has_current_simple_layout():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    for marker in (
        "cv15-clarity-page",
        "cv15-filter-panel",
        "cv2-list-panel cv15-list-panel",
        "cv15-device-count",
        "cv2-dialog",
    ):
        assert marker in template
    assert "cv2-detail cv35-detail" not in template


def test_clients_page_does_not_invent_traffic():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    assert "11.51 GB" not in template
    assert "6.03 GB" not in template
    assert "Трафик Controller" not in template


def test_clients_actions_use_current_routes():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    assert "url_for('client_detail'" in template
    assert "url_for('apply_clients')" in template
    assert "url_for('add_client')" in template


def test_clients_clarity_stylesheet_exists():
    stylesheet = ROOT / "app/web/static/sg-clients-clarity-hotfix2.css"
    assert stylesheet.is_file()
    text = stylesheet.read_text(encoding="utf-8")
    assert ".cv15-list-panel" in text
    assert "Clean Luxury Jade" in text
