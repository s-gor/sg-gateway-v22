from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xray_outer_shell_drops_legacy_padding_tail():
    card = block("body.page-connections .cnv1-engine-xray.sg-ui-card")
    assert "padding: 0;" in card


def test_xray_profile_panel_uses_section_gap_without_local_outer_margin():
    panel = block("body.page-connections .cnv1-engine-xray .xps2-panel.sg-ui-section")
    assert "gap: var(--sg-ui-section-gap, 16px);" in panel
    assert "margin" not in panel


def test_connections_shell_tail_has_no_22_07_compensation_tokens():
    assert "--sg-layout-" not in CSS
    assert "calc(" not in CSS
