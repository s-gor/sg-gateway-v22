from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app/web/templates/_mihomo_panel.html"
STYLESHEET = ROOT / "app/web/static/sg-mihomo-v2.css"


def _css_block(source: str, selector: str) -> str:
    start = source.index(selector)
    end = source.index("}", start)
    return source[start : end + 1]


def test_mihomo_panel_keeps_compact_endpoint_and_approved_controls() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "mhv2-compact-endpoint" in source
    assert "mihomo.listener_active" in source
    assert "mihomo.listener_total" in source
    assert 'name="tuic_alpn"' not in source

    for control in (
        'name="mieru_multiplexing"',
        'name="mieru_handshake"',
        'name="mieru_user_hint_mandatory"',
        'name="anytls_padding_scheme"',
        'name="tuic_congestion_controller"',
        'name="tuic_udp_relay_mode"',
    ):
        assert control in source


def test_tuic_advanced_row_contains_congestion_then_udp_relay() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    start = source.index("<h3>TUIC v5</h3>")
    end = source.index("</article>", start)
    tuic = source[start:end]

    congestion = tuic.index('name="tuic_congestion_controller"')
    udp_relay = tuic.index('name="tuic_udp_relay_mode"')
    assert congestion < udp_relay


def test_mihomo_advanced_sections_have_no_top_divider() -> None:
    source = STYLESHEET.read_text(encoding="utf-8")
    advanced = _css_block(source, ".mhv2-advanced {")

    assert "border-top" not in advanced
    assert "padding-top: 11px" in advanced
