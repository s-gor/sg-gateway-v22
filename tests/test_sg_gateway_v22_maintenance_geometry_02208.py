from __future__ import annotations

import math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = ({"width": 1440, "height": 900}, {"width": 1024, "height": 820}, {"width": 390, "height": 760})


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def test_02208_maintenance_outer_rail_is_single_and_theme_invariant() -> None:
    layout = (ROOT / "app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")
    page_css = (ROOT / "app/web/static/sg-ui-maintenance-v22-08.css").read_text(encoding="utf-8")
    html = """<!doctype html><html><body style='margin:0'><main class='sg-content'>
      <section class='sg-ui-page sg-ui-maintenance' data-sg-ui-page='maintenance'>
        <header class='sg-ui-page-head sg-ui-maintenance-head' data-sg-section='maintenance-head'><div>Maintenance</div><div class='sg-ui-actions'>A</div></header>
        <nav class='mtv31-tabs sg-ui-maintenance-tabs' data-sg-section='maintenance-tabs'><a>Backups</a><a>Updates</a></nav>
        <article class='sg-ui-section' data-sg-section='maintenance-panel-one'><header class='sg-ui-section-head'>One</header><div>Body</div></article>
        <article class='sg-ui-section' data-sg-section='maintenance-panel-two'><header class='sg-ui-section-head'>Two</header><div>Body</div></article>
      </section></main></body></html>"""
    selectors = ('[data-sg-ui-page="maintenance"]', '[data-sg-section="maintenance-head"]', '[data-sg-section="maintenance-tabs"]', '[data-sg-section="maintenance-panel-one"]', '[data-sg-section="maintenance-panel-two"]')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                theme_geometry = {}
                for theme in ("dark", "light"):
                    page = browser.new_page(viewport=viewport)
                    page.set_content(html)
                    page.add_style_tag(content=layout)
                    page.add_style_tag(content=page_css)
                    page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                    geometry = {s: page.locator(s).bounding_box() for s in selectors}
                    root = geometry[selectors[0]]
                    assert root
                    for selector in selectors[1:]:
                        box = geometry[selector]
                        assert box
                        _close(root["x"], box["x"])
                        _close(root["width"], box["width"])
                    theme_geometry[theme] = geometry
                    page.close()
                for selector in selectors:
                    for key in ("x", "width"):
                        _close(theme_geometry["dark"][selector][key], theme_geometry["light"][selector][key])
        finally:
            browser.close()
