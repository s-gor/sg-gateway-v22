from __future__ import annotations

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
