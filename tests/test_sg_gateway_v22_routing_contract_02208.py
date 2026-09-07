from __future__ import annotations

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
    for name in ('preset', 'russia_scope'):
        assert f'name="{name}"' in ROUTING
    assert 'name="{{ name }}"' in ROUTING
    for name in ('local_action', 'russia_action', 'blocked_action', 'ads_action', 'default_action'):
        assert f"action_group('{name}'" in ROUTING
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
