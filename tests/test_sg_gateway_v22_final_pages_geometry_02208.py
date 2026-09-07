from __future__ import annotations
import math
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = ({"width":1440,"height":900},{"width":1024,"height":820},{"width":390,"height":760})


def close(a,b,t=1.0): assert math.isclose(a,b,abs_tol=t),(a,b)


def _shell_geometry(css_name: str, html: str, selectors: tuple[str,...]) -> None:
    foundation=(ROOT/"app/web/static/sg-ui-foundation-v22-08.css").read_text(encoding="utf-8")
    layout=(ROOT/"app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")
    components=(ROOT/"app/web/static/sg-ui-components-v22-08.css").read_text(encoding="utf-8")
    css=(ROOT/f"app/web/static/{css_name}").read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                by_theme={}
                for theme in ("dark","light"):
                    page=browser.new_page(viewport=viewport)
                    page.set_content(html)
                    for layer in (foundation,layout,components,css): page.add_style_tag(content=layer)
                    page.evaluate("t=>document.documentElement.dataset.theme=t",theme)
                    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                    boxes={s:page.locator(s).bounding_box() for s in selectors}; root=boxes[selectors[0]]; assert root
                    for s in selectors[1:]:
                        b=boxes[s]; assert b; close(root["x"],b["x"]); close(root["width"],b["width"])
                    by_theme[theme]=boxes; page.close()
                for s in selectors:
                    close(by_theme["dark"][s]["x"],by_theme["light"][s]["x"]); close(by_theme["dark"][s]["width"],by_theme["light"][s]["width"])
        finally: browser.close()


def test_02208_help_and_operation_outer_rails() -> None:
    _shell_geometry("sg-ui-help-v22-08.css", """<body style='margin:0'><main class='sg-content'><section class='sg-ui-page' data-sg-ui-page='help'><header class='sg-ui-page-head' data-sg-section='help-head'>H</header><section class='sg-ui-section' data-sg-section='help-search'>S</section><section class='sg-ui-section' data-sg-section='help-workspace'>W</section></section></main></body>""", ('[data-sg-ui-page="help"]','[data-sg-section="help-head"]','[data-sg-section="help-search"]','[data-sg-section="help-workspace"]'))
    _shell_geometry("sg-ui-operation-job-v22-08.css", """<body style='margin:0'><main class='sg-content'><section class='sg-ui-page' data-sg-ui-page='operation-job'><header class='sg-ui-page-head' data-sg-section='operation-head'>H</header><article data-sg-section='operation-terminal'>T</article><footer class='sg-ui-actions' data-sg-section='operation-actions'>A</footer></section></main></body>""", ('[data-sg-ui-page="operation-job"]','[data-sg-section="operation-head"]','[data-sg-section="operation-terminal"]','[data-sg-section="operation-actions"]'))


def test_02208_standalone_pages_have_responsive_theme_invariant_frame() -> None:
    foundation=(ROOT/"app/web/static/sg-ui-foundation-v22-08.css").read_text(encoding="utf-8")
    components=(ROOT/"app/web/static/sg-ui-components-v22-08.css").read_text(encoding="utf-8")
    standalone=(ROOT/"app/web/static/sg-ui-standalone-v22-08.css").read_text(encoding="utf-8")
    cases=(
      ("""<body class='sg-ui-standalone-body'><main class='sg-ui-standalone sg-ui-standalone--login' data-sg-standalone-page='login'><section class='sg-ui-card sg-ui-login-card'>Login</section></main></body>""",'[data-sg-standalone-page="login"]','.sg-ui-login-card'),
      ("""<body class='sg-ui-standalone-body'><main class='sg-ui-standalone sg-ui-standalone--recovery' data-sg-standalone-page='recovery'><header class='sg-ui-recovery-head'>Recovery</header><section class='tool-panel'>Health</section><section class='table-panel'>Backups</section></main></body>""",'[data-sg-standalone-page="recovery"]','.tool-panel'),
    )
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                for html,root_sel,child_sel in cases:
                    geom={}
                    for theme in ("dark","light"):
                        page=browser.new_page(viewport=viewport); page.set_content(html)
                        for layer in (foundation,components,standalone): page.add_style_tag(content=layer)
                        page.evaluate("t=>document.documentElement.dataset.theme=t",theme)
                        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
                        root=page.locator(root_sel).bounding_box(); child=page.locator(child_sel).bounding_box(); assert root and child
                        assert root["x"] >= -1 and root["x"]+root["width"] <= viewport["width"]+1
                        assert child["x"] >= root["x"]-1 and child["x"]+child["width"] <= root["x"]+root["width"]+1
                        geom[theme]=(root,child); page.close()
                    for idx in (0,1):
                        close(geom["dark"][idx]["x"],geom["light"][idx]["x"]); close(geom["dark"][idx]["width"],geom["light"][idx]["width"])
        finally: browser.close()
