from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xmux_visible_card_uses_xray_inner_working_width():
    wrapper = block("body.page-connections #xray-xmux.xmux1-wrap")
    assert "margin-inline: 0;" in wrapper

    card = block("body.page-connections #xray-xmux .xmux1-card")
    assert "margin-inline: var(--sgui-card-padding);" in card


def test_mihomo_https_warning_matches_listener_row_width():
    warning_wrap = block("body.page-connections #mihomo .mhv2-compact-meta")
    assert "margin-inline: calc(var(--sgui-card-padding) * 2);" in warning_wrap

    form = block("body.page-connections #mihomo .mhv2-form")
    assert "margin-inline: var(--sgui-card-padding);" in form


def test_naiveproxy_card_has_standard_header_height_and_vertical_rhythm():
    card = block("body.page-connections .xps2-naiveproxy-card")
    assert "min-height: 104px;" in card
    assert "padding-block: var(--sgui-card-padding);" in card
    assert "align-items: center;" in card

    copy = block("body.page-connections .xps2-naiveproxy-copy")
    assert "display: grid;" in copy
    assert "align-content: center;" in copy


def test_mobile_final_grid_does_not_keep_desktop_double_inset():
    mobile = CSS[CSS.index("@media (max-width: 650px)") :]
    assert "body.page-connections #xray-xmux.xmux1-wrap {\n    margin-inline: 0;" in mobile
    assert "body.page-connections #xray-xmux .xmux1-card {\n    margin-inline: 0;" in mobile
    assert "body.page-connections #mihomo .mhv2-compact-meta {\n    margin-inline: var(--sgui-nested-padding);" in mobile
