from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xray_inner_working_width_uses_one_canonical_rail():
    rail = block("body.page-connections .cnv1-engine-xray .sg-ui-rail")
    assert "padding-inline: var(--sg-ui-rail-inset, 18px);" in rail
    assert "margin-inline:" not in rail


def test_awg_mihomo_pair_uses_canonical_grid_without_compensation_offsets():
    pair = block("body.page-connections .cnv1-engine-pair.sg-ui-grid")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in pair
    assert "gap: var(--sg-ui-grid-gap, 12px);" in pair
    assert "margin" not in pair
    assert "padding" not in pair


def test_connections_css_contains_no_22_07_offset_contract():
    assert "--sg-layout-" not in CSS
    assert "--sgui-" not in CSS
    assert "calc(" not in CSS
    for stale in (
        "margin-inline: var(--sg-layout-card-inset)",
        "margin-inline: var(--sg-layout-deep-inset)",
        "var(--sg-layout-mobile-inset)",
    ):
        assert stale not in CSS


def test_mobile_grid_collapses_without_reintroducing_double_inset():
    mobile = CSS[CSS.index("@media (max-width: 760px)") :]
    assert "padding-inline: var(--sg-ui-rail-inset, 14px);" in mobile
    assert "margin-inline" not in mobile

    responsive = CSS[CSS.index("@media (max-width: 900px)") :]
    assert "grid-template-columns: minmax(0, 1fr);" in responsive
