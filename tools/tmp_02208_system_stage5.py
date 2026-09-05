from __future__ import annotations

import re
from pathlib import Path


BASE_SHA = "51a6b8037351b8c9ef0fc9630cfb23fc1200287c"

SYSTEM_CSS = (
    "sg-system-visual-v1.css",
    "sg-system-top-bars-v2.css",
    "sg-cpu-breakdown-v1.css",
    "sg-cpu-dial-layout-v3.css",
    "sg-refresh-buttons-unify-v2.css",
    "sg-refresh-buttons-unify-v5.css",
    "sg-disk-breakdown-v1.css",
    "sg-system-unified-free-color-v2.css",
    "sg-system-cpu-summary-header-v1.css",
    "sg-system-memory-row-bars-v1.css",
    "sg-system-top-dividers-remove-v2.css",
    "sg-system-memory-legend-divider-remove-v1.css",
    "sg-system-light-theme-v3.css",
    "sg-system-simple-dials-v1.css",
    "sg-system-activity-v3.css",
    "sg-ui-system-v22-08.css",
)

SYSTEM_JS = (
    "sg-cpu-breakdown-v1.js",
    "sg-disk-breakdown-v2.js",
    "sg-system-unified-free-color-v2.js",
    "sg-system-cpu-summary-header-v1.js",
    "sg-system-memory-row-bars-v1.js",
    "sg-system-activity-v3.js",
    "sg-system-resource-labels-v2.js",
    "sg-memory-card-refresh-v1.js",
)


def write_tests() -> None:
    Path("tests/test_sg_gateway_v22_system_contract_02208.py").write_text(r'''from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = (ROOT / "app/web/templates/system.html").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
VISUAL = (ROOT / "app/web/static/sg-system-visual-v1.css").read_text(encoding="utf-8")
FRAME = (ROOT / "app/web/static/sg-page-frame-routing-v1.css").read_text(encoding="utf-8")
PAGE_CSS = ROOT / "app/web/static/sg-ui-system-v22-08.css"

SYSTEM_CSS = (
    "sg-system-visual-v1.css",
    "sg-system-top-bars-v2.css",
    "sg-cpu-breakdown-v1.css",
    "sg-cpu-dial-layout-v3.css",
    "sg-refresh-buttons-unify-v2.css",
    "sg-refresh-buttons-unify-v5.css",
    "sg-disk-breakdown-v1.css",
    "sg-system-unified-free-color-v2.css",
    "sg-system-cpu-summary-header-v1.css",
    "sg-system-memory-row-bars-v1.css",
    "sg-system-top-dividers-remove-v2.css",
    "sg-system-memory-legend-divider-remove-v1.css",
    "sg-system-light-theme-v3.css",
    "sg-system-simple-dials-v1.css",
    "sg-system-activity-v3.css",
    "sg-ui-system-v22-08.css",
)
SYSTEM_JS = (
    "sg-cpu-breakdown-v1.js",
    "sg-disk-breakdown-v2.js",
    "sg-system-unified-free-color-v2.js",
    "sg-system-cpu-summary-header-v1.js",
    "sg-system-memory-row-bars-v1.js",
    "sg-system-activity-v3.js",
    "sg-system-resource-labels-v2.js",
    "sg-memory-card-refresh-v1.js",
)


def test_02208_system_owns_all_page_assets_and_preserves_runtime_hooks() -> None:
    assert "{% block page_styles %}" in SYSTEM
    assert "{% block scripts %}" in SYSTEM
    assert "{% block head %}" not in SYSTEM
    for asset in SYSTEM_CSS + SYSTEM_JS:
        assert f"static_asset('{asset}')" in SYSTEM, asset
        assert asset not in BASE, asset
    assert "active_page|default('') == 'system'" not in BASE
    assert "url_for('static', filename='sg-system" not in SYSTEM
    assert "url_for('static', filename='sg-memory-card-refresh-v1.js')" not in SYSTEM

    assert 'data-sg-ui-page="system"' in SYSTEM
    for section in ("system-head", "system-summary", "system-resources", "system-lower", "system-footer"):
        assert f'data-sg-section="{section}"' in SYSTEM

    for hook in (
        'data-sg-memory-card="1"',
        'data-sg-memory-refresh',
        'data-sg-memory-breakdown',
        'data-sg-disk-card="1"',
        'data-sg-disk-refresh',
        'data-sg-disk-breakdown',
        'data-sg-cpu-card="1"',
        'data-sg-cpu-refresh',
        'data-sg-cpu-breakdown',
        'data-system-activity',
        'data-activity-url="{{ url_for(\'system_activity_api\') }}"',
    ):
        assert hook in SYSTEM
    assert "url_for('download_diagnostics')" in SYSTEM
    assert "url_for('maintenance')" in SYSTEM
    assert "url_for('api_status')" in SYSTEM


def test_02208_system_legacy_styles_no_longer_own_outer_rails() -> None:
    for selector in (".sv1-page", ".sv1-heading", ".sv1-kicker", ".sv1-heading-actions"):
        assert selector not in FRAME
    assert not re.search(r"\.sv1-page\s*\{", VISUAL)
    assert not re.search(r"\.sv1-heading\s*\{", VISUAL)
    assert not re.search(r"\.sv1-heading-actions\s*\{", VISUAL)
    assert PAGE_CSS.exists()
    page_css = PAGE_CSS.read_text(encoding="utf-8")
    assert '[data-sg-ui-page="system"]' in page_css
    assert '.sg-ui-system-head' in page_css
    assert "margin-inline: 0" in page_css
''', encoding="utf-8")

    Path("tests/test_sg_gateway_v22_system_geometry_02208.py").write_text(r'''from __future__ import annotations

import math

from playwright.sync_api import sync_playwright

import app.main as main
from tests.ui.browser_harness import login_panel, rect, serve_app, set_theme

VIEWPORTS = (
    {"width": 1440, "height": 1000},
    {"width": 1024, "height": 900},
    {"width": 390, "height": 844},
)


def _system_context():
    return {
        "report": {
            "health": "ok",
            "hostd": {"status": "ok"},
            "generated_at": "2026-09-05 20:00:00",
            "version": "0.1.0-022.08",
        },
        "health_checks": [],
        "resources": {
            "memory": {
                "percent": 30,
                "percent_text": "30%",
                "gradient": "conic-gradient(#60a9f3 0 30%, transparent 30% 100%)",
                "used": "1.2 GiB",
                "total": "4.0 GiB",
                "available": "2.8 GiB",
                "swap_used": "0 B",
                "rows": [],
            },
            "disk": {
                "percent": 25,
                "percent_text": "25%",
                "gradient": "conic-gradient(#60a9f3 0 25%, transparent 25% 100%)",
                "used": "10 GiB",
                "total": "40 GiB",
                "free": "30 GiB",
                "free_percent": 75,
                "filesystem": "ext4",
                "mount_point": "/",
                "rows": [],
            },
            "cpu": {
                "state": "normal",
                "state_label": "Норма",
                "percent": 10,
                "count": 2,
                "load": "0.10 / 0.08 / 0.05",
                "uptime": "1 день",
                "processes": 80,
                "running": 1,
                "rows": [],
            },
        },
        "client_total": 0,
        "backup_total": 0,
        "connections": [],
    }


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "system-browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    monkeypatch.setattr(main, "_sg_gateway_system_context", _system_context)
    monkeypatch.setattr(main, "collect_system_activity", lambda: {})
    monkeypatch.setattr(main, "list_clients", lambda: [])
    return main.create_app()


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def _same_rail(page, selectors):
    geometry = {selector: rect(page, selector) for selector in selectors}
    root = geometry[selectors[0]]
    for selector in selectors[1:]:
        _close(root["x"], geometry[selector]["x"])
        _close(root["width"], geometry[selector]["width"])
    return geometry


def test_02208_system_uses_canonical_rail_in_both_themes(tmp_path, monkeypatch):
    app = _setup_app(tmp_path, monkeypatch)
    selectors = (
        '[data-sg-ui-page="system"]',
        '[data-sg-section="system-head"]',
        '[data-sg-section="system-summary"]',
        '[data-sg-section="system-resources"]',
        '[data-sg-section="system-lower"]',
        '[data-sg-section="system-footer"]',
    )
    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                theme_geometry = {}
                for theme in ("dark", "light"):
                    page = browser.new_page(viewport=viewport)
                    login_panel(page, base_url, password="secret")
                    set_theme(page, theme)
                    page.goto(f"{base_url}/system", wait_until="networkidle")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                    )
                    geometry = _same_rail(page, selectors)
                    assert page.locator('[data-sg-memory-refresh]').is_visible()
                    assert page.locator('[data-sg-disk-refresh]').is_visible()
                    assert page.locator('[data-sg-cpu-refresh]').is_visible()
                    theme_geometry[theme] = geometry
                    page.close()
                for selector in selectors:
                    for key in ("x", "width"):
                        _close(theme_geometry["dark"][selector][key], theme_geometry["light"][selector][key])
        finally:
            browser.close()
''', encoding="utf-8")


def migrate_template() -> None:
    path = Path("app/web/templates/system.html")
    text = path.read_text(encoding="utf-8")
    head_start = text.index("{% block head %}")
    head_end = text.index("{% endblock %}", head_start) + len("{% endblock %}")

    styles = "{% block page_styles %}\n" + "\n".join(
        f"  <link rel=\"stylesheet\" href=\"{{{{ static_asset('{asset}') }}}}\">" for asset in SYSTEM_CSS
    ) + "\n{% endblock %}"
    text = text[:head_start] + styles + text[head_end:]

    replacements = {
        '<section class="sv1-page">': '<section class="sv1-page sg-ui-page sg-ui-system" data-sg-ui-page="system">',
        '<header class="sv1-heading">': '<header class="sv1-heading sg-ui-page-head sg-ui-system-head" data-sg-section="system-head">',
        '<div class="sv1-heading-actions">': '<div class="sv1-heading-actions sg-ui-actions">',
        '<section class="sv1-summary sg-ljd-system-summary">': '<section class="sv1-summary sg-ljd-system-summary" data-sg-section="system-summary">',
        '<section class="sv1-resource-grid">': '<section class="sv1-resource-grid" data-sg-section="system-resources">',
        '<section class="sv1-two-column sv1-primary-lower-grid">': '<section class="sv1-two-column sv1-primary-lower-grid" data-sg-section="system-lower">',
        '<footer class="sv1-page-footer">': '<footer class="sv1-page-footer" data-sg-section="system-footer">',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f"System template marker missing: {old}")
        text = text.replace(old, new, 1)

    inline_assets = (
        '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'sg-system-activity-v3.css\') }}?v={{ app_version }}">\n',
        '    <script src="{{ url_for(\'static\', filename=\'sg-system-activity-v3.js\') }}?v={{ app_version }}" defer></script>\n',
        '<script src="{{ url_for(\'static\', filename=\'sg-system-resource-labels-v2.js\') }}?v={{ app_version }}" defer></script>\n',
        '<script src="{{ url_for(\'static\', filename=\'sg-memory-card-refresh-v1.js\') }}?v={{ app_version }}" defer></script>\n',
    )
    for marker in inline_assets:
        if marker not in text:
            raise RuntimeError(f"System inline asset marker missing: {marker.strip()}")
        text = text.replace(marker, "", 1)

    if "{% block scripts %}" in text:
        raise RuntimeError("System already owns a scripts block unexpectedly")
    scripts = "\n{% block scripts %}\n{{ super() }}\n" + "\n".join(
        f"<script src=\"{{{{ static_asset('{asset}') }}}}\" defer></script>" for asset in SYSTEM_JS
    ) + "\n{% endblock %}\n"
    text = text.rstrip() + scripts
    path.write_text(text, encoding="utf-8")


def migrate_base() -> None:
    path = Path("app/web/templates/base.html")
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\n?\s*{% if active_page\|default\(''\) == 'system' %}.*?{% endif %}\n?",
        re.S,
    )
    text, count = pattern.subn("\n", text)
    if count != 7:
        raise RuntimeError(f"expected 7 System base asset blocks, removed {count}")
    path.write_text(text, encoding="utf-8")


def migrate_visual_css() -> None:
    path = Path("app/web/static/sg-system-visual-v1.css")
    text = path.read_text(encoding="utf-8")
    for block in (
        '''.sv1-page {\n  display: grid;\n  gap: 18px;\n  min-width: 0;\n}\n\n''',
        '''.sv1-heading {\n  display: flex;\n  align-items: flex-end;\n  justify-content: space-between;\n  gap: 24px;\n  padding: 0 4px 2px;\n}\n\n''',
        '''.sv1-heading-actions {\n  display: flex;\n  gap: 9px;\n  flex-wrap: wrap;\n}\n\n''',
    ):
        if block not in text:
            raise RuntimeError(f"System visual ownership block missing: {block.splitlines()[0]}")
        text = text.replace(block, "", 1)
    path.write_text(text, encoding="utf-8")


def migrate_legacy_frame() -> None:
    path = Path("app/web/static/sg-page-frame-routing-v1.css")
    text = path.read_text(encoding="utf-8")
    for token in (".sv1-page, ", ".sv1-heading, ", ".sv1-kicker, ", ".sv1-heading-actions, "):
        if token not in text:
            raise RuntimeError(f"System legacy frame selector missing: {token}")
        text = text.replace(token, "")
    path.write_text(text, encoding="utf-8")


def write_page_css() -> None:
    Path("app/web/static/sg-ui-system-v22-08.css").write_text(r'''/* SG-Gateway 22.08 System page ownership. Shared layout owns horizontal rails. */
[data-sg-ui-page="system"] {
  width: 100%;
  max-width: none;
  min-width: 0;
  margin: 0;
  padding: 0;
}

[data-sg-ui-page="system"] > .sg-ui-page-head,
[data-sg-ui-page="system"] > [data-sg-section] {
  box-sizing: border-box;
  width: 100%;
  max-width: none;
  min-width: 0;
  margin-inline: 0;
}

.sg-ui-system-head {
  min-height: 68px;
  padding-block: 4px 10px;
  border-bottom: 1px solid var(--sg-ui-border);
}

.sg-ui-system-head > div:first-child {
  min-width: 0;
}

.sg-ui-system-head h1 {
  font-size: 27px;
  line-height: 1.05;
}

.sg-ui-system-head .sg-ui-actions {
  min-width: 0;
}

@media (max-width: 760px) {
  .sg-ui-system-head {
    min-height: 0;
  }

  .sg-ui-system-head .sg-ui-actions {
    width: 100%;
  }
}
''', encoding="utf-8")


def migrate() -> None:
    migrate_template()
    migrate_base()
    migrate_visual_css()
    migrate_legacy_frame()
    write_page_css()
