from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")
LAYOUT_CSS = (ROOT / "app/web/static/sg-ui-layout-v22-08.css").read_text(encoding="utf-8")


def block(css: str, selector: str) -> str:
    start = css.index(selector)
    open_brace = css.index("{", start)
    close_brace = css.index("}", open_brace)
    return css[open_brace + 1 : close_brace]


def test_xmux_and_xray_share_the_canonical_single_rail_contract():
    rail = block(PAGE_CSS, "body.page-connections .cnv1-engine-xray .sg-ui-rail")
    assert "padding-inline: var(--sg-ui-rail-inset" in rail

    canonical = block(LAYOUT_CSS, ".sg-ui-rail")
    assert "padding-inline: var(--sg-ui-rail-inset" in canonical

    assert "--sg-layout-card-inset" not in PAGE_CSS
    assert "--sg-layout-nested-inset" not in PAGE_CSS


def test_xmux_alignment_has_no_local_margin_compensation():
    assert "calc(" not in PAGE_CSS
    assert "margin-inline: var(--sg-layout" not in PAGE_CSS
    assert "#xray-xmux.xmux1-wrap" not in PAGE_CSS

    actions = block(
        PAGE_CSS,
        "body.page-connections :is(\n  #xray-xmux .xmux1-actions,\n  .mhv2-actions,\n  .cnv1-form-actions\n)",
    )
    assert "justify-content: flex-end;" in actions
