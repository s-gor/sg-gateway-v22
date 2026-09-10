from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
AWG31 = (ROOT / "app/web/templates/_awg31_panel.html").read_text(encoding="utf-8")
NAIVE = (ROOT / "app/web/templates/_naiveproxy_panel.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")
XMUX = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")
MIHOMO = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")


def test_awg31_and_naiveproxy_share_one_compact_protocol_block() -> None:
    assert 'class="cnv1-compact-protocols' in TEMPLATE
    block = TEMPLATE.split('class="cnv1-compact-protocols', 1)[1].split('</section>', 1)[0]
    assert '{% include "_awg31_panel.html" %}' in block
    assert '{% include "_naiveproxy_panel.html" %}' in block
    assert 'cnv1-engine-awg awgd-shell' not in TEMPLATE


def test_awg31_panel_is_compact_and_keeps_dns_endpoint_contract() -> None:
    assert 'awg31-compact-card' in AWG31
    assert '{{ awg31_public_host }}:587' in AWG31
    assert "url_for('update_awg_dns')" in AWG31
    assert 'name="dns"' in AWG31
    assert 'Независимый userspace runtime' not in AWG31


def test_naiveproxy_uses_same_compact_card_family() -> None:
    assert 'naiveproxy-compact-card' in NAIVE
    assert 'data-naive-submit' in NAIVE
    assert 'data-naive-state' in NAIVE
    assert '.cnv1-compact-protocol-grid' in CSS
    assert 'grid-template-columns: repeat(2, minmax(0, 1fr));' in CSS


def test_compact_protocol_polish_removes_noise() -> None:
    assert 'cnv1-compact-protocol-grid sg-ui-rail' in TEMPLATE
    assert 'UDP VPN + HTTPS PROXY' not in TEMPLATE
    assert '<h2>AmneziaWG 3.1 · NaiveProxy</h2>' in TEMPLATE
    assert 'Два независимых подключения в одном компактном блоке.' not in TEMPLATE
    assert 'country_name(awg31_country)' not in AWG31
    assert 'HTTPS proxy · TLS · порт' in NAIVE
    assert 'data-naive-summary-port' in NAIVE


def test_connections_uses_one_pagewide_inner_rail() -> None:
    rail = 'var(--sg-ui-rail-inset, 18px)'
    assert f'body.page-connections .cnv1-engine-xray .sg-ui-rail {{\n  padding-inline: {rail};' in CSS
    assert f'body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {{\n  margin-inline: {rail};' in CSS
    assert f'body.page-connections .cnv1-compact-protocols .sg-ui-rail {{\n  padding-inline: {rail};' in CSS


def test_xmux_does_not_add_a_second_inner_rail() -> None:
    assert '#xray-xmux .xmux1-card > form {' not in XMUX


def test_xray_actions_use_panel_width_and_advanced_uses_single_rail() -> None:
    rail = 'var(--sg-ui-rail-inset, 18px)'
    assert 'body.page-connections .cnv1-engine-xray :is(.xps2-top-actions, .xps2-actions) {\n  margin-inline: 0;' in CSS
    assert f'body.page-connections .cnv1-engine-xray > .cnv1-advanced {{\n  margin-inline: {rail};' in CSS


def test_mihomo_and_compact_protocol_cards_match_xray_outline() -> None:
    assert '/* Unified protocol-card shell: one visual language in light and dark themes */' in CSS
    assert '.mhv2-listener,' in CSS
    assert '.cnv1-compact-protocol-card' in CSS
    assert 'border: 2px solid color-mix(' in CSS
    assert 'border-radius: var(--sg-ui-nested-radius, 10px);' in CSS
    assert 'box-shadow:' in CSS


def test_mihomo_does_not_add_a_second_inner_rail() -> None:
    assert 'class="mhv2-inner-rail">' in MIHOMO
    assert 'class="mhv2-inner-rail sg-ui-rail">' not in MIHOMO
    assert 'body.page-connections .mhv2-inner-rail {\n  padding: 0 0 var(--sg-ui-card-pad, 18px);' in CSS


def test_protocol_cards_share_one_visual_shell_and_naive_has_no_duplicate_port() -> None:
    assert 'border-radius: var(--sg-ui-nested-radius, 10px);' in CSS
    assert 'background-clip: padding-box;' in CSS
    assert 'cnv1-compact-protocol-port' not in CSS
    assert 'data-naive-port' not in NAIVE
    assert 'data-naive-endpoint' not in NAIVE
    assert "`${domain}:${activePort}`" in NAIVE


def test_mieru_user_hint_uses_compact_switch_not_native_checkbox_row() -> None:
    assert 'class="mhv2-user-hint-switch"' in MIHOMO
    assert 'class="sg-runtime-switch mhv2-user-hint-control"' in MIHOMO
    assert 'name="mieru_user_hint_mandatory"' in MIHOMO
    assert 'class="mhv2-check"' not in MIHOMO
    assert '.mhv2-user-hint-switch {' in CSS


def test_lower_engine_shells_match_xray_outer_card_language() -> None:
    assert 'mhv2-head cnv1-engine-head cnv1-peer-engine-head' in MIHOMO
    assert 'cnv1-engine-logo mihomo' in MIHOMO
    assert 'cnv1-compact-protocols cnv1-engine-card sg-ljd-card sg-ui-card sg-ui-section' in TEMPLATE
    assert '<h2>AmneziaWG 3.1 · NaiveProxy</h2>' in TEMPLATE
    assert '2 протокола' in TEMPLATE
    assert '/* Unified engine shells: Xray, Mihomo and AWG31/NaiveProxy share one outer-card language. */' in CSS
