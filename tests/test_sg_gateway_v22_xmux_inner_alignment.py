from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIFIED_CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")
XRAY_CSS = (ROOT / "app/web/static/sg-xray-profiles-v2.css").read_text(encoding="utf-8")
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


def test_xray_action_rail_is_two_card_insets_from_the_major_card_edge():
    global_root = block(GLOBAL_CSS, ":root")
    assert "--sgui-card-padding: 18px;" in global_root

    xray_panel = block(XRAY_CSS, ".xps2-panel")
    assert "margin: 18px;" in xray_panel

    xray_children = block(
        UNIFIED_CSS,
        "body.page-connections .cnv1-engine-xray :is(\n  .xps2-selection,\n  .xps2-parameters,\n  .xps2-actions\n)",
    )
    assert "margin-inline: var(--sg-layout-card-inset);" in xray_children

    layout_root = block(LAYOUT_CSS, ":root")
    assert "--sg-layout-card-inset: var(--sgui-card-padding);" in layout_root
    assert "--sg-layout-deep-inset: calc(var(--sg-layout-card-inset) * 2);" in layout_root


def test_xmux_inner_card_uses_the_same_cumulative_rail_as_xray_actions():
    card = block(UNIFIED_CSS, "body.page-connections #xray-xmux .xmux1-card")
    assert "margin-inline: var(--sg-layout-deep-inset);" in card


def test_mobile_xmux_removes_the_desktop_inner_rail():
    mobile_start = UNIFIED_CSS.index("@media (max-width: 650px)")
    mobile = UNIFIED_CSS[mobile_start:]
    assert "body.page-connections #xray-xmux .xmux1-card" in mobile
    assert "margin-inline: 0;" in mobile
