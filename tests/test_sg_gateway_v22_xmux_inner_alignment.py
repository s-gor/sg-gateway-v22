from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIFIED_CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")
CONNECTIONS_VISUAL_CSS = (ROOT / "app/web/static/sg-connections-visual-v1.css").read_text(encoding="utf-8")
LAYOUT_CSS = (ROOT / "app/web/static/sg-layout-contract-v1.css").read_text(encoding="utf-8")
GLOBAL_CSS = (ROOT / "app/web/static/sg-global-ui-system-v1.css").read_text(encoding="utf-8")


def block(css: str, selector: str) -> str:
    start = css.index(selector)
    open_brace = css.index("{", start)
    close_brace = css.index("}", open_brace)
    return css[open_brace + 1 : close_brace]


def test_xmux_outer_section_keeps_full_major_card_width():
    wrapper = block(UNIFIED_CSS, "body.page-connections #xray-xmux.xmux1-wrap")
    assert "margin-inline: 0;" in wrapper
    assert "border: 1px solid var(--sg-line);" in wrapper
    assert "border-radius: var(--sgui-radius-card);" in wrapper


def test_upper_xray_inner_surface_uses_one_card_inset():
    global_root = block(GLOBAL_CSS, ":root")
    assert "--sgui-card-padding: 18px;" in global_root

    endpoint = block(CONNECTIONS_VISUAL_CSS, ".cnv1-endpoint-card")
    assert "margin: 0 18px;" in endpoint

    layout_root = block(LAYOUT_CSS, ":root")
    assert "--sg-layout-card-inset: var(--sgui-card-padding);" in layout_root


def test_xmux_inner_card_matches_the_upper_xray_inner_surface_width():
    card = block(UNIFIED_CSS, "body.page-connections #xray-xmux .xmux1-card")
    assert "margin-inline: var(--sg-layout-card-inset);" in card
    assert "var(--sg-layout-deep-inset)" not in card


def test_mobile_xmux_removes_the_desktop_inner_rail():
    mobile_start = UNIFIED_CSS.index("@media (max-width: 650px)")
    mobile = UNIFIED_CSS[mobile_start:]
    assert "body.page-connections #xray-xmux .xmux1-card" in mobile
    assert "margin-inline: 0;" in mobile
