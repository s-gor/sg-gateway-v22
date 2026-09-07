from __future__ import annotations

import math

from playwright.sync_api import sync_playwright

import app.main as main
from app.clients.repository import create_client, create_device
from tests.ui.browser_harness import login_panel, rect, serve_app, set_theme

VIEWPORTS = (
    {"width": 1440, "height": 1000},
    {"width": 1024, "height": 900},
    {"width": 390, "height": 844},
)


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    app = main.create_app()
    app.jinja_env.globals.update(
        {
            "sg_subscription_universal_url": lambda current_client: f"/contracts/{current_client.id}/universal",
            "sg_subscription_native_url": lambda current_client: f"/contracts/{current_client.id}/native",
            "openwrt_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/openwrt",
            "keenetic_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/keenetic",
            "router_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router",
            "router_subscription_download_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router.json",
        }
    )
    client_id = create_client("Browser Client", "xray")
    assert client_id
    device_id = create_device(client_id, "Phone", "xray")
    assert device_id
    return app, client_id


def _assert_close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def _assert_same_rail(page, selectors):
    geometry = {selector: rect(page, selector) for selector in selectors}
    root = geometry[selectors[0]]
    for selector in selectors[1:]:
        _assert_close(root["x"], geometry[selector]["x"])
        _assert_close(root["width"], geometry[selector]["width"])
    return geometry


def test_02208_clients_and_detail_share_canonical_rail_and_theme_geometry(tmp_path, monkeypatch):
    app, client_id = _setup_app(tmp_path, monkeypatch)
    pages = (
        ("/clients", (
            '[data-sg-ui-page="clients"]',
            '[data-sg-ui-page="clients"] > .sg-ui-page-head',
            '[data-sg-section="clients-filters"]',
            '[data-sg-section="clients-list"]',
        )),
        (f"/clients/{client_id}", (
            '[data-sg-ui-page="client-detail"]',
            '[data-sg-ui-page="client-detail"] > .sg-ui-page-head',
            '[data-sg-section="devices"]',
        )),
    )
    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                for path, selectors in pages:
                    theme_geometry = {}
                    for theme in ("dark", "light"):
                        page = browser.new_page(viewport=viewport)
                        login_panel(page, base_url, password="secret")
                        set_theme(page, theme)
                        page.goto(f"{base_url}{path}", wait_until="networkidle")
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                        )
                        theme_geometry[theme] = _assert_same_rail(page, selectors)
                        page.close()
                    for selector in selectors:
                        for key in ("x", "width"):
                            _assert_close(
                                theme_geometry["dark"][selector][key],
                                theme_geometry["light"][selector][key],
                            )
        finally:
            browser.close()
