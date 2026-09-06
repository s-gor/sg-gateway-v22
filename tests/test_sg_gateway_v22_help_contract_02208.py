from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = (ROOT / "app/web/templates/help.html").read_text(encoding="utf-8")


def test_02208_help_assets_semantics_and_behavior() -> None:
    assert "{% block page_styles %}" in T
    assert "{% block head %}" not in T
    assert "static_asset('sg-ui-help-v22-08.css')" in T
    assert not (ROOT / "app/web/static/sg-help-visual-v1.css").exists()
    assert (ROOT / "app/web/static/sg-ui-help-v22-08.css").exists()
    for marker in ('data-sg-ui-page="help"', 'data-sg-section="help-head"', 'data-sg-section="help-summary"', 'data-sg-section="help-search"', 'data-sg-section="help-workspace"', 'sg-ui-page', 'sg-ui-page-head', 'sg-ui-actions', 'sg-ui-section'):
        assert marker in T, marker
    for marker in ('id="help-search"', 'id="help-clear"', 'id="help-no-results"', 'data-help-topic', 'data-search=', 'input.addEventListener("input"', 'clear.addEventListener("click"'):
        assert marker in T, marker
    for endpoint in ("system", "maintenance", "connections", "routing", "clients", "security", "help_topic", "help_index", "recovery", "download_diagnostics"):
        assert f"url_for('{endpoint}'" in T, endpoint
