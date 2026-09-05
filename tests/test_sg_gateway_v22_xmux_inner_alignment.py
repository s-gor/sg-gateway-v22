from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xmux_outer_section_keeps_full_major_card_width():
    wrapper = block("body.page-connections #xray-xmux.xmux1-wrap")
    assert "margin-inline: 0;" in wrapper
    assert "border: 1px solid var(--sg-line);" in wrapper
    assert "border-radius: var(--sgui-radius-card);" in wrapper


def test_xmux_inner_card_aligns_with_xray_inner_action_boundaries():
    card = block("body.page-connections #xray-xmux .xmux1-card")
    assert "margin-inline: var(--sgui-card-padding);" in card

    xray = block("body.page-connections .cnv1-engine-xray :is(\n  .xps2-selection,\n  .xps2-parameters,\n  .xps2-actions\n)")
    assert "margin-inline: var(--sgui-card-padding);" in xray
