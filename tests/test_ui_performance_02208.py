from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "app/web/static/sg-ui-components-v22-08.css"
LUXURY = ROOT / "app/web/static/sg-luxury-jade-depth-v2.css"


def test_light_theme_does_not_use_fixed_full_page_background():
    luxury = LUXURY.read_text(encoding="utf-8")
    components = COMPONENTS.read_text(encoding="utf-8")

    assert "radial-gradient" in luxury
    assert "background-attachment: scroll !important" in components


def test_large_panel_surfaces_are_paint_contained():
    components = COMPONENTS.read_text(encoding="utf-8")

    assert "contain: paint" in components
    assert ".sg-content" in components
    assert ".sg-main" in components


def test_sidebar_and_topbar_do_not_animate_layout_properties():
    components = COMPONENTS.read_text(encoding="utf-8")

    assert ".sg-sidebar" in components
    assert ".sg-global-topbar" in components
    assert "transition-property: none !important" in components
