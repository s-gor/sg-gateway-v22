from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGE_CSS = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
LEGACY_CSS = ROOT / "app/web/static/sg-connections-unified-v1.css"


def _page_css() -> str:
    assert PAGE_CSS.is_file(), "22.08 Connections stylesheet is missing"
    return PAGE_CSS.read_text(encoding="utf-8")


def test_connections_uses_22_08_page_stylesheet_and_not_legacy_unified_asset():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    assert "sg-connections-unified-v1.css" not in base
    assert template.count("sg-ui-connections-v22-08.css") == 1
    assert re.search(
        r"static_asset\(['\"]sg-ui-connections-v22-08\.css['\"]\)",
        template,
    )


def test_connections_22_08_css_uses_only_canonical_geometry_tokens():
    css = _page_css()
    for token in (
        "--sg-ui-page-gap",
        "--sg-ui-section-gap",
        "--sg-ui-grid-gap",
        "--sg-ui-card-radius",
        "--sg-ui-nested-radius",
        "--sg-ui-control-radius",
        "--sg-ui-control-height",
        "--sg-ui-badge-height",
        "--sg-ui-rail-inset",
    ):
        assert f"var({token}" in css

    assert "--sg-layout-" not in css
    assert "--sgui-" not in css
    assert "calc(" not in css


def test_connections_22_08_css_does_not_own_global_shell_or_outer_page_rail():
    css = _page_css()
    assert ".sg-content" not in css
    assert ".sg-shell" not in css
    assert not re.search(
        r"\.cnv1-page\.sg-ui-page\s*\{[^}]*(?:padding-inline|margin-inline|border)\s*:",
        css,
        flags=re.S,
    )


def test_connections_22_08_css_has_no_theme_palette_or_important_fence():
    css = _page_css()
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", css) is None
    assert "rgb(" not in css.lower()
    assert "rgba(" not in css.lower()
    assert "!important" not in css
    assert "html[data-theme=" not in css


def test_connections_22_08_css_covers_all_connection_families():
    css = _page_css()
    for selector in (
        ".cnv1-engine-xray",
        "#xray-xmux .xmux1-card",
        ".awgd-shell",
        ".awgd-card",
        ".mhv2-panel",
        ".mhv2-listener",
        ".xps2-naiveproxy-card",
    ):
        assert selector in css


def test_connections_22_08_css_pins_controls_badges_and_nested_surfaces_to_canonical_tokens():
    css = _page_css()
    assert "border-radius: var(--sg-ui-card-radius" in css
    assert "border-radius: var(--sg-ui-nested-radius" in css
    assert "border-radius: var(--sg-ui-control-radius" in css
    assert "min-height: var(--sg-ui-control-height" in css
    assert "min-height: var(--sg-ui-badge-height" in css
    assert '.xps2-parameter-row input:not([type="checkbox"]):not([type="radio"])' in css
    assert ".awgd-shared-dns-form input" in css
    assert ".mhv2-basic-fields select" in css


def test_legacy_connections_unified_stylesheet_is_removed_after_migration():
    assert not LEGACY_CSS.exists()
