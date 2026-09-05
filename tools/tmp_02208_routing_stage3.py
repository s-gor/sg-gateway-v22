from __future__ import annotations

from pathlib import Path

ROOT = Path('.')


def _replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'marker not found in {path}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def write_tests() -> None:
    Path('tests/test_sg_gateway_v22_routing_contract_02208.py').write_text(r'''from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTING = (ROOT / 'app/web/templates/routing.html').read_text(encoding='utf-8')
GEO = (ROOT / 'app/web/templates/_geofiles_panel.html').read_text(encoding='utf-8')
TEMPLATES = (ROOT / 'app/web/templates/_routing_templates_panel.html').read_text(encoding='utf-8')
BASE = (ROOT / 'app/web/templates/base.html').read_text(encoding='utf-8')
LEGACY = (ROOT / 'app/web/static/sg-routing-client096.css').read_text(encoding='utf-8')
COMPONENTS = (ROOT / 'app/web/static/sg-ui-components-v22-08.css').read_text(encoding='utf-8')


def test_02208_routing_keeps_behavior_contract_and_owns_assets_on_page() -> None:
    assert "{% block page_styles %}" in ROUTING
    assert "static_asset('sg-routing-client096.css')" in ROUTING
    assert "static_asset('sg-ui-routing-v22-08.css')" in ROUTING
    assert 'data-sg-ui-page="routing"' in ROUTING
    assert 'data-sg-section="routing-tabs"' in ROUTING
    assert 'data-sg-section="routing-main"' in ROUTING
    assert 'data-sg-section="routing-geofiles"' in ROUTING
    assert 'data-r096-tab="routing"' in ROUTING
    assert 'data-r096-tab="geofiles"' in ROUTING
    assert 'data-r096-panel="routing"' in ROUTING
    assert 'data-r096-panel="geofiles"' in ROUTING
    assert 'id="r096-smart-form"' in ROUTING
    assert "url_for('routing_smart_preview')" in ROUTING
    for name in ('preset', 'local_action', 'russia_scope', 'russia_action', 'blocked_action', 'ads_action', 'default_action'):
        assert f'name="{name}"' in ROUTING
    for hook in ('data-r096-user-rules', 'data-r096-user-rules-toggle', 'data-r096-rule-tab', 'data-r096-rule-panel', 'data-open-r096-tab'):
        assert hook in ROUTING
    assert "url_for('routing_template_apply')" in ROUTING
    assert "url_for('routing_template_rollback')" in ROUTING
    assert "active_page|default('') == 'routing'" not in BASE
    assert "sg-routing-client096.css" not in BASE


def test_02208_geofiles_and_template_forms_are_frozen() -> None:
    assert 'id="r096-geofiles-form"' in GEO
    assert "url_for('geofiles_check')" in GEO
    assert 'enctype="multipart/form-data"' in GEO
    for token in (
        'name="source_id"', 'name="roscom_block_ads"', 'name="roscom_block_windows"',
        'name="roscom_block_torrent"', 'data-source-info="roscomvpn"',
        'data-source-fields="custom_url"', 'name="geoip_url"', 'name="geosite_url"',
        'data-source-fields="upload"', 'name="geoip_file"', 'name="geosite_file"',
        'data-source-fields="local"', 'name="local_geoip"', 'name="local_geosite"', '[data-copy]'
    ):
        assert token in GEO
    assert "url_for('geofiles_apply')" in GEO
    assert "url_for('geofiles_rollback')" in GEO
    assert "url_for('routing_template_preview')" in TEMPLATES
    assert "url_for('routing_template_apply')" in TEMPLATES
    assert "url_for('routing_template_rollback')" in TEMPLATES
    assert 'name="template_id"' in TEMPLATES
    assert 'name="mode" value="replace_managed"' in TEMPLATES
    assert 'data-open-routing-tab="outbounds"' in TEMPLATES


def test_02208_legacy_routing_css_no_longer_owns_shell_or_page_rails() -> None:
    for forbidden in (
        'body.page-routing .sg-workspace',
        'body.page-routing .sg-content',
        'body.page-routing .sg-sidebar',
        'body.page-routing .sg-global-topbar',
        '.r096-page',
        '.r096-heading',
        '.r096-tabs',
        '.r096-panel',
    ):
        assert forbidden not in LEGACY
    assert '.sg-ui-tabs' in COMPONENTS
    assert '.sg-ui-tab' in COMPONENTS
''', encoding='utf-8')

    Path('tests/test_sg_gateway_v22_routing_geometry_02208.py').write_text(r'''from __future__ import annotations

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
''', encoding='utf-8')


def migrate_template() -> None:
    path = Path('app/web/templates/routing.html')
    text = path.read_text(encoding='utf-8')
    title = '{% block title %}SG-Gateway · Routing{% endblock %}\n'
    styles = '''{% block title %}SG-Gateway · Routing{% endblock %}\n\n{% block page_styles %}\n  <link rel="stylesheet" href="{{ static_asset('sg-routing-client096.css') }}">\n  <link rel="stylesheet" href="{{ static_asset('sg-ui-routing-v22-08.css') }}">\n{% endblock %}\n'''
    if '{% block page_styles %}' not in text:
        if title not in text:
            raise RuntimeError('routing title marker missing')
        text = text.replace(title, styles, 1)
    replacements = {
        '<section class="r096-page">': '<section class="r096-page sg-ui-page sg-ui-routing" data-sg-ui-page="routing">',
        '<header class="r096-heading">': '<header class="r096-heading sg-ui-page-head sg-ui-routing-head">',
        '<nav class="r096-tabs" aria-label="Разделы Routing">': '<nav class="r096-tabs sg-ui-tabs sg-ui-routing-tabs" data-sg-section="routing-tabs" aria-label="Разделы Routing">',
        '<button type="button" data-r096-tab="routing" class="active">Routing</button>': '<button type="button" data-r096-tab="routing" class="sg-ui-tab active">Routing</button>',
        '<button type="button" data-r096-tab="geofiles">GeoFiles</button>': '<button type="button" data-r096-tab="geofiles" class="sg-ui-tab">GeoFiles</button>',
        '<section class="r096-panel" data-r096-panel="routing">': '<section class="r096-panel sg-ui-section sg-ui-routing-panel" data-sg-section="routing-main" data-r096-panel="routing">',
        '<section class="r096-panel" data-r096-panel="geofiles" hidden>': '<section class="r096-panel sg-ui-section sg-ui-routing-panel" data-sg-section="routing-geofiles" data-r096-panel="geofiles" hidden>',
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError(f'routing marker missing: {old}')
        text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8')


def migrate_base() -> None:
    path = Path('app/web/templates/base.html')
    text = path.read_text(encoding='utf-8')
    old = "  {% if active_page|default('') == 'routing' %}<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='sg-routing-client096.css') }}\">{% endif %}\n"
    if old not in text:
        raise RuntimeError('legacy Routing base asset marker missing')
    path.write_text(text.replace(old, '', 1), encoding='utf-8')


def migrate_legacy_css() -> None:
    import tinycss2

    path = Path('app/web/static/sg-routing-client096.css')
    text = path.read_text(encoding='utf-8')
    forbidden = (
        'body.page-routing .sg-workspace',
        'body.page-routing .sg-content',
        'body.page-routing .sg-sidebar',
        'body.page-routing .sg-global-topbar',
        '.r096-page',
        '.r096-heading',
        '.r096-tabs',
        '.r096-panel',
    )

    def clean_rules(rules):
        cleaned = []
        for rule in rules:
            if rule.type == 'qualified-rule':
                selector = tinycss2.serialize(rule.prelude)
                if any(token in selector for token in forbidden):
                    continue
            elif rule.type == 'at-rule' and rule.content is not None:
                inner = tinycss2.parse_rule_list(rule.content, skip_whitespace=False, skip_comments=False)
                inner = clean_rules(inner)
                rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(inner))
            cleaned.append(rule)
        return cleaned

    rules = tinycss2.parse_stylesheet(text, skip_whitespace=False, skip_comments=False)
    text = tinycss2.serialize(clean_rules(rules))
    path.write_text(text, encoding='utf-8')


def extend_components() -> None:
    path = Path('app/web/static/sg-ui-components-v22-08.css')
    text = path.read_text(encoding='utf-8')
    marker = '/* SG-Gateway 22.08 canonical tabs. Structural rail ownership remains in sg-ui-layout. */'
    if marker in text:
        return
    addition = r'''

/* SG-Gateway 22.08 canonical tabs. Structural rail ownership remains in sg-ui-layout. */
.sg-ui-tabs {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.sg-ui-tab {
  display: inline-flex;
  min-height: var(--sg-ui-control-height-sm, 32px);
  align-items: center;
  justify-content: center;
  padding: 7px 13px;
  border: 1px solid var(--sg-ui-border-strong);
  border-radius: var(--sg-ui-control-radius, 9px);
  background: var(--sg-ui-surface-raised);
  color: var(--sg-ui-text-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.sg-ui-tab.active {
  border-color: color-mix(in srgb, var(--sg-ui-accent) 60%, var(--sg-ui-border-strong));
  background: var(--sg-ui-accent-soft);
  color: var(--sg-ui-accent);
}
'''
    path.write_text(text.rstrip() + addition + '\n', encoding='utf-8')


def write_routing_css() -> None:
    Path('app/web/static/sg-ui-routing-v22-08.css').write_text(r'''/* SG-Gateway 22.08 Routing. Shared layout owns horizontal page rails. */
.sg-ui-routing {
  color: var(--r096-text, var(--sg-ui-text));
}

.sg-ui-routing-head {
  min-height: 68px;
  padding-block: 4px 10px;
  border-bottom: 1px solid var(--r096-line, var(--sg-ui-border));
}

.sg-ui-routing-head > div:first-child {
  min-width: 0;
}

.sg-ui-routing-head h1 {
  font-size: 27px;
  line-height: 1.05;
}

.sg-ui-routing-tabs {
  padding-block: 0 10px;
  border-bottom: 1px solid var(--r096-line, var(--sg-ui-border));
}

.sg-ui-routing-panel {
  gap: 12px;
  padding-block: 0 4px;
}

.sg-ui-routing-panel[hidden] {
  display: none;
}

@media (max-width: 760px) {
  .sg-ui-routing-head {
    min-height: 0;
  }

  .sg-ui-routing-tabs .sg-ui-tab {
    flex: 1 1 140px;
  }
}
''', encoding='utf-8')


def migrate() -> None:
    migrate_template()
    migrate_base()
    migrate_legacy_css()
    extend_components()
    write_routing_css()


if __name__ == '__main__':
    write_tests()
    migrate()
