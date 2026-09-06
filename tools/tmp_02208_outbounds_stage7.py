from __future__ import annotations

from pathlib import Path

CONTRACT_TEST = r'''from __future__ import annotations

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
'''

GEOMETRY_TEST = r'''from __future__ import annotations

import math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = ({"width": 1440, "height": 900}, {"width": 1024, "height": 820}, {"width": 390, "height": 760})


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def test_02208_outbounds_outer_rail_is_single_and_theme_invariant() -> None:
    foundation = (ROOT / "app/web/static/sg-ui-foundation-v22-08.css").read_text(encoding="utf-8")
    layout = (ROOT / "app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")
    components = (ROOT / "app/web/static/sg-ui-components-v22-08.css").read_text(encoding="utf-8")
    page_css = (ROOT / "app/web/static/sg-ui-outbounds-v22-08.css").read_text(encoding="utf-8")
    html = """<!doctype html><html><body style='margin:0'><main class='sg-content'>
      <section class='ob49-page sg-ui-page sg-ui-outbounds' data-sg-ui-page='outbounds'>
        <header class='ob49-heading sg-ui-page-head' data-sg-section='outbounds-head'><div>Outbounds</div><div class='sg-ui-actions'>Help</div></header>
        <section class='ob49-system-card sg-ui-section' data-sg-section='outbounds-system'><header class='sg-ui-section-head'>System</header></section>
        <section class='ob49-warp-card sg-ui-section' data-sg-section='outbounds-warp'><header class='ob49-warp-head sg-ui-section-head'>WARP</header></section>
        <section class='ob49-custom-card sg-ui-section' data-sg-section='outbounds-custom'><header class='sg-ui-section-head'>Custom</header></section>
      </section></main></body></html>"""
    selectors = ('[data-sg-ui-page="outbounds"]', '[data-sg-section="outbounds-head"]', '[data-sg-section="outbounds-system"]', '[data-sg-section="outbounds-warp"]', '[data-sg-section="outbounds-custom"]')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                by_theme = {}
                for theme in ("dark", "light"):
                    page = browser.new_page(viewport=viewport)
                    page.set_content(html)
                    page.add_style_tag(content=foundation)
                    page.add_style_tag(content=layout)
                    page.add_style_tag(content=components)
                    page.add_style_tag(content=page_css)
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                    boxes = {s: page.locator(s).bounding_box() for s in selectors}
                    root = boxes[selectors[0]]
                    assert root
                    for selector in selectors[1:]:
                        box = boxes[selector]
                        assert box
                        _close(root["x"], box["x"])
                        _close(root["width"], box["width"])
                    by_theme[theme] = boxes
                    page.close()
                for selector in selectors:
                    for key in ("x", "width"):
                        _close(by_theme["dark"][selector][key], by_theme["light"][selector][key])
        finally:
            browser.close()
'''


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_outbounds_contract_02208.py").write_text(CONTRACT_TEST, encoding="utf-8")
    Path("tests/test_sg_gateway_v22_outbounds_geometry_02208.py").write_text(GEOMETRY_TEST, encoding="utf-8")


def migrate() -> None:
    template_path = Path("app/web/templates/outbounds.html")
    text = template_path.read_text(encoding="utf-8")
    insertion = "{% block page_styles %}\n  <link rel=\"stylesheet\" href=\"{{ static_asset('sg-ui-outbounds-v22-08.css') }}\">\n{% endblock %}\n\n"
    marker = "{% block content %}\n"
    if marker not in text or "{% block page_styles %}" in text:
        raise RuntimeError("unexpected Outbounds asset block state")
    text = text.replace(marker, insertion + marker, 1)
    replacements = (
        ('<section class="ob49-page">', '<section class="ob49-page sg-ui-page sg-ui-outbounds" data-sg-ui-page="outbounds">'),
        ('<header class="ob49-heading">', '<header class="ob49-heading sg-ui-page-head" data-sg-section="outbounds-head">'),
        ('<a class="ob49-help"', '<a class="ob49-help sg-ui-button"'),
        ('<section class="ob49-system-card">', '<section class="ob49-system-card sg-ui-section" data-sg-section="outbounds-system">'),
        ('<section class="ob49-warp-card" id="warp">', '<section class="ob49-warp-card sg-ui-section" id="warp" data-sg-section="outbounds-warp">'),
        ('<header class="ob49-warp-head">', '<header class="ob49-warp-head sg-ui-section-head">'),
        ('<section class="ob49-custom-card">', '<section class="ob49-custom-card sg-ui-section" data-sg-section="outbounds-custom">'),
    )
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f"missing Outbounds marker: {old}")
        text = text.replace(old, new, 1)
    text = text.replace('<section class="ob49-system-card sg-ui-section" data-sg-section="outbounds-system">\n    <header>', '<section class="ob49-system-card sg-ui-section" data-sg-section="outbounds-system">\n    <header class="sg-ui-section-head">', 1)
    text = text.replace('<section class="ob49-custom-card sg-ui-section" data-sg-section="outbounds-custom">\n    <header>', '<section class="ob49-custom-card sg-ui-section" data-sg-section="outbounds-custom">\n    <header class="sg-ui-section-head">', 1)
    text = text.replace('class="ob49-warp-buttons ', 'class="ob49-warp-buttons sg-ui-actions ')
    text = text.replace('class="ob49-warp-buttons"', 'class="ob49-warp-buttons sg-ui-actions"')
    template_path.write_text(text, encoding="utf-8")

    base_path = Path("app/web/templates/base.html")
    base = base_path.read_text(encoding="utf-8")
    old = "  {% if active_page|default('') == 'outbounds' %}<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-outbounds-v49.css') }}\">{% endif %}\n"
    if old not in base:
        raise RuntimeError("Outbounds global asset marker missing")
    base_path.write_text(base.replace(old, "", 1), encoding="utf-8")

    legacy_path = Path("app/web/static/sg-outbounds-v49.css")
    css = legacy_path.read_text(encoding="utf-8")
    for declaration in (
        "  display: grid;\n",
        "  gap: 24px;\n",
        "  width: min(100%, 1500px);\n",
        "  margin: 0 auto;\n",
    ):
        if declaration not in css:
            raise RuntimeError(f"Outbounds legacy geometry declaration missing: {declaration.strip()}")
        css = css.replace(declaration, "", 1)
    css += '''\n/* 22.08 semantic rail ownership */\n[data-sg-ui-page="outbounds"] { --sg-ui-page-gap: 24px; width: 100%; margin-inline: 0; }\n[data-sg-ui-page="outbounds"] > .sg-ui-page-head,\n[data-sg-ui-page="outbounds"] > .sg-ui-section { width: 100%; margin-inline: 0; }\n'''
    Path("app/web/static/sg-ui-outbounds-v22-08.css").write_text(css, encoding="utf-8")
    legacy_path.unlink()
