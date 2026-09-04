from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xmux_is_one_outer_surface_with_header_and_body_spacing():
    wrapper = block("body.page-connections #xray-xmux.xmux1-wrap")
    assert "padding: 0;" in wrapper
    assert "border: 0;" in wrapper
    assert "background: transparent;" in wrapper
    assert "box-shadow: none;" in wrapper

    card = block("body.page-connections #xray-xmux .xmux1-card")
    assert "padding: 0;" in card

    head = block("body.page-connections #xray-xmux .xmux1-head")
    assert "padding: var(--sgui-card-padding);" in head
    assert "margin: 0;" in head

    form = block("body.page-connections #xray-xmux #xray-xmux-form")
    assert "padding: 0 var(--sgui-card-padding) var(--sgui-card-padding);" in form


def test_mihomo_uses_same_header_body_footer_geometry_as_other_engines():
    panel = block("body.page-connections .mhv2-panel")
    assert "padding: 0;" in panel

    head = block("body.page-connections .mhv2-head")
    assert "padding: var(--sgui-card-padding);" in head
    assert "margin: 0;" in head

    body = block("body.page-connections #mihomo :is(")
    assert ".mhv2-compact-meta" in CSS[CSS.index("body.page-connections #mihomo :is(") : CSS.index("{", CSS.index("body.page-connections #mihomo :is("))]
    assert ".mhv2-form" in CSS[CSS.index("body.page-connections #mihomo :is(") : CSS.index("{", CSS.index("body.page-connections #mihomo :is("))]
    assert ".mhv2-runtime-note" in CSS[CSS.index("body.page-connections #mihomo :is(") : CSS.index("{", CSS.index("body.page-connections #mihomo :is("))]
    assert "margin-inline: var(--sgui-card-padding);" in body


def test_nested_surfaces_share_flat_visual_depth():
    marker = "body.page-connections :is(\n  .xps2-selection,"
    start = CSS.index(marker)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    shared = CSS[open_brace + 1 : close_brace]
    assert "box-shadow: none;" in shared


def test_xmux_and_mihomo_actions_follow_same_right_aligned_rhythm():
    actions = block("body.page-connections :is(\n  #xray-xmux .xmux1-actions,\n  .mhv2-actions")
    assert "justify-content: flex-end;" in actions
    assert "margin-top: var(--sgui-grid-gap);" in actions


def test_naiveproxy_wrapper_does_not_create_a_card_inside_a_card():
    wrapper = block("body.page-connections #sg-naiveproxy-settings")
    assert "padding: 0;" in wrapper
    assert "border: 0;" in wrapper
    assert "background: transparent;" in wrapper
    assert "box-shadow: none;" in wrapper
