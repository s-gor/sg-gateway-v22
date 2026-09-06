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


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "security-browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    monkeypatch.setattr(main, "password_is_default", lambda: False)
    monkeypatch.setattr(main, "security_tls_overview", lambda: {
        "domain": "panel.example.com",
        "https_ready": False,
        "public_url": "",
        "dns": None,
        "certificate": None,
        "certbot_timer_enabled": False,
        "nginx_active": False,
        "public_port": 443,
        "backend_port": 8080,
        "backups": [],
        "nginx_config": "/etc/nginx/sites-enabled/sg-gateway",
        "certificate_path": None,
        "last_message": "",
    })
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


def test_02208_security_uses_canonical_rail_in_both_themes(tmp_path, monkeypatch):
    app = _setup_app(tmp_path, monkeypatch)
    selectors = (
        '[data-sg-ui-page="security"]',
        '[data-sg-section="security-head"]',
        '[data-sg-section="security-summary"]',
        '[data-sg-section="security-tls"]',
        '[data-sg-section="security-password"]',
        '[data-sg-section="security-status"]',
        '[data-sg-section="security-tech"]',
        '[data-sg-section="security-footer"]',
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
                    page.goto(f"{base_url}/security", wait_until="networkidle")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                    )
                    geometry = _same_rail(page, selectors)
                    assert page.locator('#secv2-domain-input').is_visible()
                    assert page.locator('input[name="current_password"]').is_visible()
                    assert page.locator('input[name="new_password"]').is_visible()
                    assert page.locator('input[name="confirm_password"]').is_visible()
                    theme_geometry[theme] = geometry
                    page.close()
                for selector in selectors:
                    for key in ("x", "width"):
                        _close(theme_geometry["dark"][selector][key], theme_geometry["light"][selector][key])
        finally:
            browser.close()
