from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
AWG31 = (ROOT / "app/web/templates/_awg31_panel.html").read_text(encoding="utf-8")
NAIVE = (ROOT / "app/web/templates/_naiveproxy_panel.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")
XMUX = (ROOT / "app/web/templates/_xray_xmux_settings.html").read_text(encoding="utf-8")


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
    assert 'padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));' in CSS


def test_compact_protocol_polish_matches_mihomo_rail_and_removes_noise() -> None:
    assert 'cnv1-compact-protocol-grid sg-ui-rail' in TEMPLATE
    assert 'UDP VPN + HTTPS PROXY' not in TEMPLATE
    assert 'AmneziaWG 3.1 · NaiveProxy' not in TEMPLATE
    assert 'Два независимых подключения в одном компактном блоке.' not in TEMPLATE
    assert 'country_name(awg31_country)' not in AWG31
    assert 'HTTPS proxy · TLS · порт' in NAIVE
    assert 'data-naive-summary-port' in NAIVE
    assert 'padding-inline: calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px));' in CSS

def test_upper_connection_inner_rails_match_compact_protocol_inset() -> None:
    desktop_inset = 'calc(var(--sg-ui-card-pad, 18px) + var(--sg-ui-rail-inset, 18px))'
    assert f'body.page-connections .cnv1-engine-xray .sg-ui-rail {{\n  padding-inline: {desktop_inset};' in CSS
    assert f'body.page-connections .cnv1-engine-xray > .cnv1-endpoint-card {{\n  margin-inline: {desktop_inset};' in CSS
    assert f'body.page-connections .cnv1-compact-protocols .sg-ui-rail {{\n  padding-inline: {desktop_inset};' in CSS

def test_xmux_inner_controls_follow_the_same_desktop_rail() -> None:
    assert '#xray-xmux .xmux1-card > form {' in XMUX
    assert 'padding-inline: var(--sg-ui-rail-inset, 18px);' in XMUX
    assert '@media (max-width: 760px)' in XMUX
    assert 'padding-inline: 0;' in XMUX

