from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/outbounds.html").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
PAGE_CSS = ROOT / "app/web/static/sg-ui-outbounds-v22-08.css"
LEGACY_CSS = ROOT / "app/web/static/sg-outbounds-v49.css"


def test_02208_outbounds_owns_assets_and_semantic_rails() -> None:
    assert "{% block page_styles %}" in TEMPLATE
    assert "static_asset('sg-ui-outbounds-v22-08.css')" in TEMPLATE
    assert "active_page|default('') == 'outbounds'" not in BASE
    assert "sg-outbounds-v49.css" not in BASE
    assert 'data-sg-ui-page="outbounds"' in TEMPLATE
    for section in ("outbounds-head", "outbounds-system", "outbounds-warp", "outbounds-custom"):
        assert f'data-sg-section="{section}"' in TEMPLATE
    for marker in ("sg-ui-page", "sg-ui-page-head", "sg-ui-section", "sg-ui-section-head", "sg-ui-actions"):
        assert marker in TEMPLATE, marker
    assert PAGE_CSS.exists()
    assert not LEGACY_CSS.exists()


def test_02208_outbounds_warp_behavior_contract_stays_intact() -> None:
    for endpoint in ("outbounds_warp_create", "outbounds_warp_json", "outbounds_warp_test", "outbounds_warp_disable", "outbounds_warp_enable", "outbounds_warp_recreate", "outbounds_warp_remove", "routing"):
        assert f"url_for('{endpoint}'" in TEMPLATE, endpoint
    assert "url_for('help_topic', slug='routing')" in TEMPLATE
    for marker in ('data-sg-confirm=', 'data-sg-confirm-title=', 'data-sg-confirm-button='):
        assert marker in TEMPLATE


def test_02208_outbounds_page_css_does_not_own_outer_width() -> None:
    css = PAGE_CSS.read_text(encoding="utf-8")
    assert 'width: 100%; margin-inline: 0' not in css
