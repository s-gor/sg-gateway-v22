from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_clients_visual_uses_only_real_client_fields():
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


def test_clients_visual_has_simple_reference_layout():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    for marker in (
        "cv2-filter-panel",
        "cv2-list-panel cv15-list-panel",
        "cv15-table",
        "cv15-row-actions",
    ):
        assert marker in template
    for removed in ("cv2-detail cv35-detail", "cv35-access-list", "cv35-detail-actions", "cv2-dots-button"):
        assert removed not in template


def test_clients_visual_does_not_fake_traffic_or_nodes():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    for forbidden in ("11.51 GB", "603.25 MB", "SG-Node", "Controller traffic", "Последняя активность"):
        assert forbidden not in template


def test_clients_visual_uses_existing_routes():
    template = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    assert "url_for('client_detail'" in template
    assert "url_for('apply_clients')" in template
    assert "url_for('add_client')" in template


def test_clients_visual_v2_and_clarity_css_exist():
    legacy = ROOT / "app/web/static/sg-clients-visual-v2.css"
    clarity = ROOT / "app/web/static/sg-clients-clarity-hotfix2.css"
    assert legacy.is_file()
    assert clarity.is_file()
    assert ".cv2-workspace" in legacy.read_text(encoding="utf-8")
    assert ".cv15-list-panel" in clarity.read_text(encoding="utf-8")
