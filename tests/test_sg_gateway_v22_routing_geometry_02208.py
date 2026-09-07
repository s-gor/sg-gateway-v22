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
    monkeypatch.setenv('SG_GATEWAY_ADMIN_PASSWORD', 'secret')
    monkeypatch.setenv('SG_GATEWAY_SECRET_KEY', 'routing-browser-secret')
    monkeypatch.setenv('SG_GATEWAY_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('SG_GATEWAY_LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setenv('SG_GATEWAY_PUBLIC_ADDRESS', '203.0.113.10')
    monkeypatch.setenv('SG_GATEWAY_COUNTRY_CODE', 'fr')
    monkeypatch.setattr(main, 'list_connections', lambda: [])
    monkeypatch.setattr(main, 'get_connection_settings', lambda _engine: {})
    monkeypatch.setattr(main, 'xray_profiles_overview', lambda: {})
    monkeypatch.setattr(main, 'routing_templates_overview', lambda: {
        'candidate': None,
        'active': None,
        'capabilities': {'direct6': False, 'warp4': False, 'warp6': False},
        'geoip_count': 0,
        'geosite_count': 0,
        'backups': [],
    })
    monkeypatch.setattr(main, 'geofiles_overview', lambda: {
        'candidate': None,
        'active': None,
        'sources': [
            {'id': 'sg_client', 'label': 'Комплектные', 'note': 'Встроенный набор', 'available': True},
            {'id': 'loyalsoldier', 'label': 'Loyalsoldier', 'note': 'Удалённый набор', 'available': True},
            {'id': 'roscomvpn', 'label': 'RoscomVPN', 'note': 'Совместимый набор', 'available': True},
            {'id': 'custom_url', 'label': 'URL', 'note': 'Свои URL', 'available': True},
            {'id': 'upload', 'label': 'Upload', 'note': 'Загрузка файлов', 'available': True},
            {'id': 'local', 'label': 'Local', 'note': 'Локальные пути', 'available': True},
        ],
        'backups': [],
    })
    monkeypatch.setattr(main, 'warp_overview', lambda: {
        'status_label': 'Выключен', 'ipv4_ready': False, 'ipv6_ready': False, 'last_test': None,
    })
    monkeypatch.setattr(main, 'mihomo_overview', lambda: {})
    monkeypatch.setattr(main, 'count_clients', lambda: 0)
    return main.create_app()


def _close(a: float, b: float, tolerance: float = 1.0) -> None:
    assert math.isclose(a, b, abs_tol=tolerance), (a, b)


def _same_rail(page, selectors):
    geometry = {selector: rect(page, selector) for selector in selectors}
    root = geometry[selectors[0]]
    for selector in selectors[1:]:
        _close(root['x'], geometry[selector]['x'])
        _close(root['width'], geometry[selector]['width'])
    return geometry


def test_02208_routing_and_geofiles_share_canonical_rail_and_theme_geometry(tmp_path, monkeypatch):
    app = _setup_app(tmp_path, monkeypatch)
    with serve_app(app) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                theme_geometry = {}
                for theme in ('dark', 'light'):
                    page = browser.new_page(viewport=viewport)
                    login_panel(page, base_url, password='secret')
                    set_theme(page, theme)
                    page.goto(f'{base_url}/routing', wait_until='networkidle')
                    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
                    main_selectors = (
                        '[data-sg-ui-page="routing"]',
                        '[data-sg-ui-page="routing"] > .sg-ui-page-head',
                        '[data-sg-section="routing-tabs"]',
                        '[data-sg-section="routing-main"]',
                    )
                    geometry = _same_rail(page, main_selectors)
                    page.locator('[data-r096-tab="geofiles"]').click()
                    page.locator('[data-sg-section="routing-geofiles"]').wait_for(state='visible')
                    geo = rect(page, '[data-sg-section="routing-geofiles"]')
                    root = geometry[main_selectors[0]]
                    _close(root['x'], geo['x'])
                    _close(root['width'], geo['width'])
                    assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')
                    geometry['[data-sg-section="routing-geofiles"]'] = geo
                    theme_geometry[theme] = geometry
                    page.close()
                for selector in theme_geometry['dark']:
                    for key in ('x', 'width'):
                        _close(theme_geometry['dark'][selector][key], theme_geometry['light'][selector][key])
        finally:
            browser.close()
