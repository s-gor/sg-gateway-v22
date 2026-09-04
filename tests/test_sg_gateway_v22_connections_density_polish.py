from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "app/web/static/sg-connections-unified-v1.css"
CONNECTIONS = ROOT / "app/web/templates/connections.html"


def _css() -> str:
    return UNIFIED.read_text(encoding="utf-8")


def test_xmux_outer_card_uses_single_surface_without_wrapper_inset():
    css = _css()
    assert "body.page-connections #xray-xmux.xmux1-wrap" in css
    assert "padding: 0;" in css
    assert "body.page-connections #xray-xmux #xray-xmux-form" in css
    assert "padding: 0 var(--sgui-card-padding) var(--sgui-card-padding);" in css


def test_awg_header_has_no_visual_separator_before_profile_cards():
    css = _css()
    assert "body.page-connections .awgd-shell > .cnv1-engine-head" in css
    assert "border-bottom: 0;" in css


def test_mihomo_internal_vertical_rhythm_is_compact_and_explicit():
    css = _css()
    assert "body.page-connections #mihomo {" in css
    assert "row-gap: 0;" in css
    assert "body.page-connections #mihomo .mhv2-compact-meta" in css
    assert "margin-bottom: var(--sgui-grid-gap);" in css
    assert "body.page-connections #mihomo .mhv2-runtime-note" in css


def test_connections_bottom_incomplete_port_summary_is_removed():
    template = CONNECTIONS.read_text(encoding="utf-8")
    assert 'class="cnv1-page-footer"' not in template
    for stale_label in ("AWG2:", "AWG3:", "Xray Reality:", "Mihomo:"):
        assert stale_label not in template


def test_mobile_xmux_gutter_does_not_double_inset_the_card():
    css = _css()
    assert "body.page-connections #xray-xmux.xmux1-wrap {\n    padding: 0;" in css
    assert "body.page-connections #xray-xmux #xray-xmux-form {\n    padding: 0 var(--sgui-nested-padding) var(--sgui-nested-padding);" in css
