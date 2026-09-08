from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "app/web/static/sg-controls-final-v1.css"
LUXURY = ROOT / "app/web/static/sg-luxury-jade-depth-v2.css"


def test_light_theme_does_not_use_fixed_full_page_background():
    luxury = LUXURY.read_text(encoding="utf-8")
    controls = CONTROLS.read_text(encoding="utf-8")

    assert "radial-gradient" in luxury
    assert "background-attachment: scroll !important" in controls


def test_large_panel_surfaces_are_paint_contained():
    controls = CONTROLS.read_text(encoding="utf-8")

    assert "contain: paint" in controls
    assert ".sg-content" in controls
    assert ".sg-main" in controls


def test_sidebar_and_topbar_do_not_animate_layout_properties():
    controls = CONTROLS.read_text(encoding="utf-8")

    assert ".sg-sidebar" in controls
    assert ".sg-global-topbar" in controls
    assert "transition-property: none !important" in controls
