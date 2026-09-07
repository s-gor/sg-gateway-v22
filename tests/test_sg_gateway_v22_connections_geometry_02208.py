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

SELECTORS = (
    ".sg-ui-page",
    ".sg-ui-page-head",
    ".cnv1-engine-xray",
    ".cnv1-engine-pair",
    ".cnv1-note-panel",
)


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "browser-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    return main.create_app()


def _assert_close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def test_02208_connections_real_browser_geometry_is_canonical_and_theme_stable(tmp_path, monkeypatch):
    app = _setup_app(tmp_path, monkeypatch)

    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                snapshots: dict[str, dict[str, dict[str, float]]] = {}
                for theme in ("dark", "light"):
                    page = browser.new_page(viewport=viewport)
                    login_panel(page, base_url, password="secret")
                    set_theme(page, theme)
                    page.goto(f"{base_url}/connections", wait_until="networkidle")

                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
                    )

                    geometry = {selector: rect(page, selector) for selector in SELECTORS}
                    snapshots[theme] = geometry

                    page_rect = geometry[".sg-ui-page"]
                    heading_rect = geometry[".sg-ui-page-head"]
                    xray_rect = geometry[".cnv1-engine-xray"]
                    pair_rect = geometry[".cnv1-engine-pair"]
                    note_rect = geometry[".cnv1-note-panel"]

                    _assert_close(page_rect["x"], heading_rect["x"])
                    _assert_close(page_rect["x"], xray_rect["x"])
                    _assert_close(page_rect["x"], pair_rect["x"])
                    _assert_close(page_rect["x"], note_rect["x"])
                    _assert_close(page_rect["width"], heading_rect["width"])
                    _assert_close(page_rect["width"], xray_rect["width"])
                    _assert_close(page_rect["width"], pair_rect["width"])
                    _assert_close(page_rect["width"], note_rect["width"])

                    page.close()

                for selector in SELECTORS:
                    for key in ("x", "y", "width", "height"):
                        _assert_close(
                            snapshots["dark"][selector][key],
                            snapshots["light"][selector][key],
                        )
        finally:
            browser.close()
