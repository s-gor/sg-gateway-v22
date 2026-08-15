from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_system_visual_v1_uses_existing_context():
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    for marker in (
        "report.health",
        "resources.memory",
        "resources.disk",
        "resources.cpu",
        "health_checks",
        "connections",
        "client_total",
        "backup_total",
    ):
        assert marker in template


def test_system_visual_v1_has_compact_user_layout():
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    for marker in (
        "sv1-summary",
        "sg-ljd-system-summary",
        "sv1-resource-grid",
        "sv1-health-panel",
        "sa2-panel",
        "Трафик и активность",
    ):
        assert marker in template
    for removed in (
        "sv1-connections-panel",
        "Панель и hostd",
        "Управление системой",
        "sv1-action-grid",
        "Частые операции",
    ):
        assert removed not in template


def test_system_visual_v1_activity_panel_replaces_quick_actions():
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    for marker in (
        "data-system-activity",
        "url_for('system_activity_api')",
        "data-activity=\"today-total\"",
        "data-activity=\"month-total\"",
        "data-activity=\"clients-total\"",
        "data-activity=\"devices-total\"",
        "Последние 24 часа",
    ):
        assert marker in template
    for removed in (
        "Создать клиента",
        "Настроить подключение",
        "Создать резервную копию",
        "url_for('create_backup_route')",
        "url_for('clients', new='1')",
        "url_for('connections')",
        "sv1-action-grid",
    ):
        assert removed not in template


def test_system_visual_v1_uses_current_routes():
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    for route in (
        "download_diagnostics",
        "maintenance",
        "api_status",
        "system_activity_api",
    ):
        assert f"url_for('{route}'" in template


def test_system_visual_v1_does_not_invent_live_traffic():
    template = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
    for forbidden in (
        "11.51 GB",
        "Last seen",
        "Текущая скорость",
        "SG-Node",
        "Controller",
    ):
        assert forbidden not in template


def test_system_visual_v1_css_exists():
    path = ROOT / "app/web/static/sg-system-visual-v1.css"
    assert path.is_file()
    css = path.read_text(encoding="utf-8")
    assert ".sv1-resource-grid" in css
    assert ".sv1-donut" in css
    assert ".sv1-check-list" in css
    assert ".sv1-action-button" in css
