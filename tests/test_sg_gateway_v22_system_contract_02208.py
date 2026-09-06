from __future__ import annotations

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
