from __future__ import annotations

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
