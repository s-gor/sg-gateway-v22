from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_help_visual_v1_uses_existing_context():
    template = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")
    for marker in (
        "topics",
        "topic",
        "item.slug",
        "item.title",
        "item.summary",
        "item.body",
        "topic.body",
    ):
        assert marker in template


def test_help_visual_v1_uses_existing_routes():
    template = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")
    for route in (
        "help_index",
        "help_topic",
        "system",
        "clients",
        "connections",
        "routing",
        "maintenance",
        "security",
        "recovery",
        "download_diagnostics",
    ):
        assert f"url_for('{route}'" in template


def test_help_visual_v1_has_reference_layout():
    template = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")
    for marker in (
        "hlpv1-summary",
        "hlpv1-search-panel",
        "hlpv1-topic-sidebar",
        "hlpv1-article-panel",
        "hlpv1-journey",
        "hlpv1-steps",
    ):
        assert marker in template


def test_help_visual_v1_keeps_search_client_side():
    template = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")
    assert 'id="help-search"' in template
    assert "data-help-topic" in template
    assert "applyFilter" in template


def test_help_visual_v1_does_not_claim_missing_features():
    template = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")
    for forbidden in (
        "Включить MFA",
        "Настроить firewall",
        "Обновить Xray",
        "Создать SG-Node",
        "Настроить Cascade",
        "Открыть Cluster",
    ):
        assert forbidden not in template


def test_help_02208_css_replaces_legacy_visual_asset_and_keeps_component_rules():
    legacy = ROOT / "app/web/static/sg-help-visual-v1.css"
    path = ROOT / "app/web/static/sg-ui-help-v22-08.css"
    assert not legacy.exists()
    assert path.is_file()
    css = path.read_text(encoding="utf-8")
    assert ".hlpv1-workspace" in css
    assert ".hlpv1-topic-list" in css
    assert ".hlpv1-journey" in css
    assert '[data-sg-ui-page="help"]' in css
