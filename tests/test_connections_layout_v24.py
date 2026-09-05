from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _class_tag_index(template: str, tag: str, class_name: str, start: int = 0) -> int:
    match = re.search(
        rf'<{tag}\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>',
        template[start:],
    )
    if match is None:
        raise ValueError(f"{tag} with class token {class_name!r} not found")
    return start + match.start()


def test_decorative_map_is_removed():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert "cnv1-map-panel" not in template
    assert "СХЕМА ПОДКЛЮЧЕНИЙ" not in template
    assert "Интернет → SG-Gateway → клиентский профиль" not in template


def test_xray_is_full_width_before_equal_awg_mihomo_pair():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    xray = template.index('class="cnv1-engines cnv1-xray-row"')
    xray_card = template.index("cnv1-engine-xray", xray)
    pair = _class_tag_index(template, "section", "cnv1-engine-pair", xray_card)
    awg = template.index("cnv1-engine-awg", pair)
    mihomo = template.index('_mihomo_panel.html', awg)
    pair_end = template.index("</section>", mihomo)
    assert xray < xray_card < pair < awg < mihomo < pair_end

    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)" in css
    assert ".cnv1-xray-row" in css


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
        'name="anytls_enabled"',
        'name="tuic_enabled"',
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


def test_awg_and_mihomo_are_equal_height_on_desktop():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert ".cnv1-engine-pair { align-items: stretch; }" in css
    assert "height: auto; align-self: stretch;" in css
    assert ".cnv1-engine-awg .cnv1-engine-form-compact { flex: 1 1 auto; }" in css
    assert ".cnv1-engine-awg .cnv1-form-actions { margin-top: auto; }" in css


def test_preview28_connections_order_is_xray_then_awg_mihomo():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    assert template.index('class="cnv1-engines cnv1-xray-row"') < _class_tag_index(
        template, "section", "cnv1-engine-pair"
    )
