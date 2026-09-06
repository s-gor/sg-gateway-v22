from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_decorative_map_is_removed():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert "cnv1-map-panel" not in template
    assert "СХЕМА ПОДКЛЮЧЕНИЙ" not in template
    assert "Интернет → SG-Gateway → клиентский профиль" not in template


def test_connections_keeps_restored_order_and_appends_naiveproxy_last():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    xray = template.index("cnv1-engine-xray")
    xmux = template.index('_xray_xmux_settings.html', xray)
    awg = template.index("cnv1-engine-awg", xmux)
    mihomo = template.index('_mihomo_panel.html', awg)
    note = template.index("cnv1-note-panel", mihomo)
    naive = template.index('_naiveproxy_panel.html', note)
    assert xray < xmux < awg < mihomo < note < naive

    assert 'class="cnv1-engine-pair sg-ui-grid"' in template
    assert 'class="cnv1-engines cnv1-xray-row"' in template
    assert "cnv1-engine-grid" not in template
    assert "cnv1-grid-cell" not in template


def test_connections_has_native_naiveproxy_panel_without_html_injection():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    panel = (ROOT / "app/web/templates/_naiveproxy_panel.html").read_text(encoding="utf-8")
    http = (ROOT / "app/naiveproxy/http.py").read_text(encoding="utf-8")

    assert template.count('{% include "_naiveproxy_panel.html" %}') == 1
    assert 'id="sg-naiveproxy-settings"' in panel
    assert 'data-naiveproxy-panel' in panel
    assert "/api/naiveproxy/status" in panel
    assert "/api/naiveproxy/settings" in panel
    assert "_SETTINGS_PANEL" not in http
    assert 'request.endpoint == "connections"' not in http


def test_awg_is_compact_but_keeps_required_post_fields():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    awg_start = template.index("cnv1-engine-awg")
    awg_end = template.index("</article>", awg_start)
    awg = template[awg_start:awg_end]
    for field in ('name="host"', 'name="country_code"', 'name="port"', 'name="dns"', 'name="server_public_key"'):
        assert field in awg
    for removed in ("КЛИЕНТЫ", "PUBLIC KEY", "Публичный адрес или домен", "Страна по IP"):
        assert removed not in awg


def test_mihomo_is_compact_and_keeps_three_protocols():
    panel = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")
    assert "cnv1-engine-mihomo" in panel
    for protocol in ("Mieru", "AnyTLS", "TUIC v5"):
        assert protocol in panel
    for field in (
        'name="mieru_enabled"', 'name="mieru_transport"',
        'name="anytls_enabled"', 'name="tuic_enabled"',
    ):
        assert field in panel
    for field in ("mieru_port", "anytls_port", "tuic_port"):
        assert f'name="{field}"' not in panel
    for value in (
        "{{ mihomo.settings.mieru_port }}",
        "{{ mihomo.settings.anytls_port }}",
        "{{ mihomo.settings.tuic_port }}",
    ):
        assert value not in panel
    assert "Системный порт SG-Gateway" not in panel
    assert "mhv2-compact-endpoint" not in panel
    assert "mhv2-summary" not in panel
    assert "mhv2-sgclient" not in panel


def test_green_cyan_button_outline_is_removed():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert "border-color: transparent !important" in css
    assert ".sg-nav-item.active" in css
    assert ".mhv2-switch input:checked + span" in css
    assert "sg-preview28-final.css" in (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")


def test_connections_summary_cards_are_removed():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert 'class="cnv1-summary sg-ljd-strip"' not in template
    assert "cnv1-summary-card" not in template


def test_awg_and_mihomo_keep_equal_height_contract():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert "height: auto; align-self: stretch;" in css
    assert ".cnv1-engine-awg .cnv1-engine-form-compact { flex: 1 1 auto; }" in css
    assert ".cnv1-engine-awg .cnv1-form-actions { margin-top: auto; }" in css
