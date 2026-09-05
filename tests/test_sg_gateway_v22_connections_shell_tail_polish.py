from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/sg-connections-unified-v1.css").read_text(encoding="utf-8")


def block(selector: str) -> str:
    start = CSS.index(selector)
    open_brace = CSS.index("{", start)
    close_brace = CSS.index("}", open_brace)
    return CSS[open_brace + 1 : close_brace]


def test_xmux_outer_shell_uses_same_panel_surface_as_inner_card():
    wrapper = block("body.page-connections #xray-xmux.xmux1-wrap")
    assert "background: var(--sg-panel);" in wrapper
    assert "background: transparent;" not in wrapper


def test_xray_profile_panel_drops_legacy_bottom_tail():
    panel = block("body.page-connections .cnv1-engine-xray .xps2-panel")
    assert "margin-bottom: 0;" in panel
