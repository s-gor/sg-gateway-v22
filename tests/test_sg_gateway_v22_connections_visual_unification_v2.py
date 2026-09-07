from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_connection_families_share_canonical_card_and_nested_radii():
    assert ".cnv1-engine-xray" in CSS
    assert ".awgd-shell" in CSS
    assert ".mhv2-panel" in CSS
    assert "#xray-xmux .xmux1-card" in CSS
    assert ".xps2-naiveproxy-card" in CSS
    assert "border-radius: var(--sg-ui-card-radius, 14px);" in CSS
    assert "border-radius: var(--sg-ui-nested-radius, 10px);" in CSS


def test_xray_uses_semantic_section_and_one_inner_rail():
    section = block("body.page-connections .cnv1-engine-xray.sg-ui-section")
    assert "gap: 0;" in section

    panel = block("body.page-connections .cnv1-engine-xray .xps2-panel.sg-ui-section")
    assert "gap: var(--sg-ui-section-gap, 16px);" in panel

    rail = block("body.page-connections .cnv1-engine-xray .sg-ui-rail")
    assert "padding-inline: var(--sg-ui-rail-inset, 18px);" in rail


def test_xmux_mihomo_and_form_actions_share_canonical_action_rhythm():
    marker = "body.page-connections :is(\n  #xray-xmux .xmux1-actions,\n  .mhv2-actions,\n  .cnv1-form-actions"
    actions = block(marker)
    assert "align-items: center;" in actions
    assert "justify-content: flex-end;" in actions
    assert "gap: var(--sg-ui-grid-gap, 12px);" in CSS


def test_controls_and_statuses_use_canonical_dimensions():
    assert "border-radius: var(--sg-ui-control-radius, 9px);" in CSS
    assert "min-height: var(--sg-ui-control-height, 42px);" in CSS
    assert "min-height: var(--sg-ui-badge-height, 28px);" in CSS


def test_visual_composition_has_no_legacy_offset_or_theme_fence():
    assert "--sg-layout-" not in CSS
    assert "--sgui-" not in CSS
    assert "calc(" not in CSS
    assert "!important" not in CSS
