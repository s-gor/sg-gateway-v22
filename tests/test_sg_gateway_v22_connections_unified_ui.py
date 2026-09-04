from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "app/web/static/sg-connections-unified-v1.css"


def _unified_css() -> str:
    assert UNIFIED.is_file(), "Connections canonical geometry stylesheet is missing"
    return UNIFIED.read_text(encoding="utf-8")


def test_connections_unified_stylesheet_exists():
    assert UNIFIED.is_file()


def test_connections_unified_stylesheet_is_loaded_once_between_controls_and_dark_theme():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    marker = "sg-connections-unified-v1.css"
    assert base.count(marker) == 1
    assert "active_page|default('') == 'connections'" in base
    assert base.index("sg-controls-final-v1.css") < base.index(marker)
    assert base.index(marker) < base.index("sg-connections-dark-classic-v1.css")


def test_connections_unified_css_uses_global_geometry_tokens():
    css = _unified_css()
    for token in (
        "--sgui-page-gap",
        "--sgui-section-gap",
        "--sgui-grid-gap",
        "--sgui-radius-card",
        "--sgui-radius-nested",
        "--sgui-radius-control",
        "--sgui-radius-badge",
        "--sgui-card-padding",
        "--sgui-nested-padding",
        "--sgui-button-height",
        "--sgui-button-height-small",
        "--sgui-badge-height",
        "--sgui-card-shadow",
    ):
        assert f"var({token})" in css


def test_connections_unified_css_has_no_theme_palette_and_only_one_legacy_specificity_fence():
    css = _unified_css()
    assert re.search(r"#[0-9a-fA-F]{3,8}\b", css) is None
    assert "rgb(" not in css.lower()
    assert "rgba(" not in css.lower()

    important_lines = [line.strip() for line in css.splitlines() if "!important" in line]
    assert important_lines == [
        "border-color: var(--sg-line-soft) !important;",
        "border-radius: var(--sgui-radius-nested) !important;",
        "background: var(--sg-panel-soft) !important;",
    ]
    assert 'html[data-theme="light"] body.page-connections .mhv2-listener.sg-ljd-nested' in css
    assert "legacy light material class" in css.lower()


def test_connections_unified_css_covers_all_connection_families():
    css = _unified_css()
    for selector in (
        ".cnv1-engine-xray",
        "#xray-xmux .xmux1-card",
        ".awgd-shell",
        ".awgd-card",
        ".mhv2-panel",
        ".mhv2-listener",
        "#sg-naiveproxy-settings",
        ".xps2-naiveproxy-card",
    ):
        assert selector in css


def test_connections_unified_css_defines_shared_outer_nested_control_and_status_contracts():
    css = _unified_css()
    assert "background: var(--sg-panel);" in css
    assert "background: var(--sg-panel-soft);" in css
    assert "border-radius: var(--sgui-radius-card);" in css
    assert "border-radius: var(--sgui-radius-nested);" in css
    assert "border-radius: var(--sgui-radius-control);" in css
    assert "border-radius: var(--sgui-radius-badge);" in css
    assert "min-height: var(--sgui-button-height);" in css
    assert "height: var(--sgui-button-height);" in css
    assert "min-height: var(--sgui-badge-height);" in css


def test_connections_unified_css_pins_real_controls_to_canonical_height():
    css = _unified_css()
    assert "body.page-connections .button {\n  height: var(--sgui-button-height);" in css
    assert ".xps2-parameter-row input:not([type=\"checkbox\"]):not([type=\"radio\"])" in css
    assert ".awgd-shared-dns-form input" in css
    assert ".mhv2-basic-fields select" in css


def test_naiveproxy_late_stylesheet_uses_same_geometry_tokens():
    css = (ROOT / "app/web/static/sg-compact-protocol-cards-v1.css").read_text(encoding="utf-8")
    naive = css.split(".xps2-naiveproxy-card", 1)[1]
    assert "var(--sgui-radius-card)" in naive
    assert "var(--sgui-radius-nested)" in naive
    assert "var(--sgui-button-height)" in naive
