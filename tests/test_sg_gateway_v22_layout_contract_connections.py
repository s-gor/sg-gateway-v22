from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/web/templates/base.html"
TEMPLATE = ROOT / "app/web/templates/connections.html"
CONNECTIONS_CSS = ROOT / "app/web/static/sg-ui-connections-v22-08.css"
LAYOUT_CSS = ROOT / "app/web/static/sg-ui-layout-v22-08.css"


def test_canonical_layout_layers_load_before_page_specific_connections_css():
    base = BASE.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    foundation = "sg-ui-foundation-v22-08.css"
    layout = "sg-ui-layout-v22-08.css"
    components = "sg-ui-components-v22-08.css"
    assert base.index(foundation) < base.index(layout) < base.index(components)
    assert "{% block page_styles %}{% endblock %}" in base
    assert "sg-connections-unified-v1.css" not in base
    assert re.search(
        r"static_asset\(['\"]sg-ui-connections-v22-08\.css['\"]\)",
        template,
    )


def test_22_08_layout_defines_reusable_semantic_geometry_primitives():
    assert LAYOUT_CSS.exists()
    css = LAYOUT_CSS.read_text(encoding="utf-8")

    for selector in (
        ".sg-content",
        ".sg-ui-page",
        ".sg-ui-page-head",
        ".sg-ui-section",
        ".sg-ui-section-head",
        ".sg-ui-section-body",
        ".sg-ui-rail",
        ".sg-ui-grid",
        ".sg-ui-nested",
        ".sg-ui-form-row",
        ".sg-ui-field",
        ".sg-ui-actions",
    ):
        assert selector in css

    assert "padding-inline: var(--sg-ui-page-pad-x, 30px);" in css
    page_block = css.split(".sg-ui-page {", 1)[1].split("}", 1)[0]
    assert "padding-inline" not in page_block
    assert "margin-inline" not in page_block


def test_connections_consumes_canonical_rail_without_magic_spacing():
    css = CONNECTIONS_CSS.read_text(encoding="utf-8")

    assert "var(--sg-ui-rail-inset" in css
    assert "var(--sg-ui-grid-gap" in css
    assert "--sg-layout-" not in css
    assert "--sgui-" not in css
    assert "calc(" not in css

    for stale_geometry in (
        "margin: 0 17px;",
        "padding: 0 12px 12px;",
        "margin: 0 12px 12px;",
    ):
        assert stale_geometry not in css


def test_connections_keeps_protocol_specific_composition_under_semantic_owner():
    css = CONNECTIONS_CSS.read_text(encoding="utf-8")

    for selector in (
        "body.page-connections .cnv1-engine-xray",
        "body.page-connections .cnv1-engine-pair.sg-ui-grid",
        ".awgd-shell",
        ".mhv2-panel",
        ".xps2-naiveproxy-card",
    ):
        assert selector in css
