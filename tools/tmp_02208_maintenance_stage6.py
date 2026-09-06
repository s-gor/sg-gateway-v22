from __future__ import annotations

import re
from pathlib import Path

BASE_SHA = "2fb0f5783e276f0d616a943ec1c4bd8891ceea8a"

LEGACY_CSS = (
    "sg-maintenance-v2.css",
    "sg-maintenance-updates-v31.css",
    "sg-maintenance-updates-v32.css",
    "sg-full-backup-v1.css",
)

PAGE_CSS = r'''/* SG-Gateway 22.08 Maintenance page internals. Outer rail belongs to sg-ui-layout-v22-08.css. */
[data-sg-ui-page="maintenance"] {
  --sg-ui-page-gap: 18px;
}

.sg-ui-maintenance-head {
  margin-inline: 0;
  padding-inline: 0;
}

.sg-ui-maintenance-tabs {
  width: 100%;
  min-width: 0;
  margin: 0;
}

[data-sg-ui-page="maintenance"] > .sg-ui-section {
  width: 100%;
  margin-inline: 0;
}

[data-sg-ui-page="maintenance"] .sg-ui-section-head {
  width: 100%;
  margin-inline: 0;
}

@media (max-width: 760px) {
  .sg-ui-maintenance-tabs {
    overflow-x: auto;
    overscroll-behavior-inline: contain;
  }
}
'''


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_maintenance_contract_02208.py").write_text(r'''from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
LEGACY = (ROOT / "app/web/static/sg-maintenance-v2.css").read_text(encoding="utf-8")
PAGE_CSS = ROOT / "app/web/static/sg-ui-maintenance-v22-08.css"


def test_02208_maintenance_owns_page_assets_and_semantic_rails() -> None:
    assert "{% block page_styles %}" in TEMPLATE
    assert "{% block head %}" not in TEMPLATE
    for asset in (
        "sg-maintenance-v2.css",
        "sg-maintenance-updates-v31.css",
        "sg-maintenance-updates-v32.css",
        "sg-full-backup-v1.css",
        "sg-ui-maintenance-v22-08.css",
    ):
        assert f"static_asset('{asset}')" in TEMPLATE, asset
    assert 'data-sg-ui-page="maintenance"' in TEMPLATE
    assert 'data-sg-section="maintenance-head"' in TEMPLATE
    assert 'data-sg-section="maintenance-tabs"' in TEMPLATE
    assert "sg-ui-page" in TEMPLATE
    assert "sg-ui-page-head" in TEMPLATE
    assert "sg-ui-actions" in TEMPLATE
    assert "sg-ui-section" in TEMPLATE
    assert "sg-ui-section-head" in TEMPLATE
    assert PAGE_CSS.exists()


def test_02208_maintenance_behavior_contract_stays_intact() -> None:
    for endpoint in (
        "create_backup_route",
        "download_diagnostics",
        "panel_update_start",
        "xray_update_start",
        "awg3_runtime_repair_start",
        "create_full_backup_route",
        "restore_full_backup_route",
        "delete_old_backups_route",
        "restore_backup_route",
    ):
        assert f"url_for('{endpoint}'" in TEMPLATE, endpoint
    for marker in (
        'name="backup_action" value="verify"',
        'name="backup_action" value="restore_verified"',
        'data-sg-confirm=',
        'data-sg-full-upload',
        'data-sg-full-file',
        'data-sg-full-verify-button',
        'data-sg-full-restore-button',
    ):
        assert marker in TEMPLATE, marker
    assert "active_tab == 'backups'" in TEMPLATE
    assert "active_tab == 'updates'" in TEMPLATE


def test_02208_legacy_maintenance_css_no_longer_owns_page_or_heading_rail() -> None:
    assert not re.search(r"(?m)^\\.mtv2-page\\s*\\{", LEGACY)
    assert not re.search(r"(?m)^\\.mtv2-heading\\s*\\{", LEGACY)
''', encoding="utf-8")

    Path("tests/test_sg_gateway_v22_maintenance_geometry_02208.py").write_text(r'''from __future__ import annotations

import math
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = (
    {"width": 1440, "height": 900},
    {"width": 1024, "height": 820},
    {"width": 390, "height": 760},
)


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def test_02208_maintenance_outer_rail_is_single_and_theme_invariant() -> None:
    layout = (ROOT / "app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")
    page_css = (ROOT / "app/web/static/sg-ui-maintenance-v22-08.css").read_text(encoding="utf-8")
    html = '''<!doctype html><html><body style="margin:0"><main class="sg-content">
      <section class="sg-ui-page sg-ui-maintenance" data-sg-ui-page="maintenance">
        <header class="sg-ui-page-head sg-ui-maintenance-head" data-sg-section="maintenance-head"><div>Maintenance</div><div class="sg-ui-actions">A</div></header>
        <nav class="mtv31-tabs sg-ui-maintenance-tabs" data-sg-section="maintenance-tabs"><a>Backups</a><a>Updates</a></nav>
        <article class="sg-ui-section" data-sg-section="maintenance-panel-one"><header class="sg-ui-section-head">One</header><div>Body</div></article>
        <article class="sg-ui-section" data-sg-section="maintenance-panel-two"><header class="sg-ui-section-head">Two</header><div>Body</div></article>
      </section></main></body></html>'''
    selectors = (
        '[data-sg-ui-page="maintenance"]',
        '[data-sg-section="maintenance-head"]',
        '[data-sg-section="maintenance-tabs"]',
        '[data-sg-section="maintenance-panel-one"]',
        '[data-sg-section="maintenance-panel-two"]',
    )
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
''', encoding="utf-8")


def _remove_top_level_rule(text: str, selector: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(selector)}\s*\{{.*?^\}}\s*\n?")
    text, count = pattern.subn("", text)
    if count != 1:
        raise RuntimeError(f"expected exactly one top-level rule for {selector}, found {count}")
    return text


def migrate() -> None:
    template_path = Path("app/web/templates/maintenance.html")
    text = template_path.read_text(encoding="utf-8")

    head_start = text.index("{% block head %}")
    head_end = text.index("{% endblock %}", head_start) + len("{% endblock %}")
    styles = "{% block page_styles %}\n" + "\n".join(
        f"  <link rel=\"stylesheet\" href=\"{{{{ static_asset('{asset}') }}}}\">"
        for asset in (*LEGACY_CSS, "sg-ui-maintenance-v22-08.css")
    ) + "\n{% endblock %}"
    text = text[:head_start] + styles + text[head_end:]

    replacements = (
        ('<section class="mtv2-page">', '<section class="mtv2-page sg-ui-page sg-ui-maintenance" data-sg-ui-page="maintenance">'),
        ('<header class="mtv2-heading">', '<header class="mtv2-heading sg-ui-page-head sg-ui-maintenance-head" data-sg-section="maintenance-head">'),
        ('<div class="mtv2-heading-actions">', '<div class="mtv2-heading-actions sg-ui-actions">'),
        ('<nav class="mtv31-tabs" aria-label="Разделы Maintenance">', '<nav class="mtv31-tabs sg-ui-maintenance-tabs" data-sg-section="maintenance-tabs" aria-label="Разделы Maintenance">'),
    )
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f"Maintenance marker missing: {old}")
        text = text.replace(old, new)

    text = text.replace('class="mtv2-panel ', 'class="mtv2-panel sg-ui-section ')
    text = text.replace('class="mtv2-panel"', 'class="mtv2-panel sg-ui-section"')
    text = text.replace('class="mtv2-panel-head ', 'class="mtv2-panel-head sg-ui-section-head ')
    text = text.replace('class="mtv2-panel-head"', 'class="mtv2-panel-head sg-ui-section-head"')
    template_path.write_text(text, encoding="utf-8")

    legacy_path = Path("app/web/static/sg-maintenance-v2.css")
    legacy = legacy_path.read_text(encoding="utf-8")
    legacy = _remove_top_level_rule(legacy, ".mtv2-page")
    legacy = _remove_top_level_rule(legacy, ".mtv2-heading")
    legacy_path.write_text(legacy, encoding="utf-8")

    Path("app/web/static/sg-ui-maintenance-v22-08.css").write_text(PAGE_CSS, encoding="utf-8")
