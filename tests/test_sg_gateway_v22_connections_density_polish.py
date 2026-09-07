from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_CSS = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
CONNECTIONS = ROOT / "app/web/templates/connections.html"


def _css() -> str:
    return PAGE_CSS.read_text(encoding="utf-8")


def test_xmux_card_participates_in_canonical_surface_without_offset_contract():
    css = _css()
    assert "#xray-xmux .xmux1-card" in css
    assert "border-radius: var(--sg-ui-card-radius, 14px);" in css
    assert "margin-inline" not in css
    assert "--sg-layout-" not in css


def test_awg_shell_uses_canonical_card_surface_without_page_separator_override():
    css = _css()
    assert ".awgd-shell" in css
    assert "border-radius: var(--sg-ui-card-radius, 14px);" in css
    assert "border-bottom" not in css


def test_mihomo_internal_rhythm_uses_canonical_grid_gap():
    css = _css()
    for selector in (
        ".mhv2-listeners",
        ".mhv2-form",
        ".mhv2-form-compact",
        ".mhv2-basic-fields",
        ".mhv2-advanced-body",
        ".mhv2-listener",
        ".mhv2-client-actions",
        ".mhv2-actions",
    ):
        assert selector in css
    assert "gap: var(--sg-ui-grid-gap, 12px);" in css


def test_connections_bottom_incomplete_port_summary_is_removed():
    template = CONNECTIONS.read_text(encoding="utf-8")
    assert 'class="cnv1-page-footer"' not in template
    for stale_label in ("AWG2:", "AWG3:", "Xray Reality:", "Mihomo:"):
        assert stale_label not in template


def test_mobile_connections_rail_does_not_double_inset():
    css = _css()
    mobile = css[css.index("@media (max-width: 760px)") :]
    assert "padding-inline: var(--sg-ui-rail-inset, 14px);" in mobile
    assert "margin-inline" not in mobile
    assert "calc(" not in mobile
