from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
AWG31 = (ROOT / "app/web/templates/_awg31_panel.html").read_text(encoding="utf-8")
NAIVE = (ROOT / "app/web/templates/_naiveproxy_panel.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")


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
