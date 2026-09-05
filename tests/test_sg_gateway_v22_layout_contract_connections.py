from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/web/templates/base.html"
CONNECTIONS_CSS = ROOT / "app/web/static/sg-connections-unified-v1.css"
LAYOUT_CSS = ROOT / "app/web/static/sg-layout-contract-v1.css"


def test_shared_layout_contract_is_loaded_before_page_specific_connections_css():
    base = BASE.read_text(encoding="utf-8")

    assert "sg-layout-contract-v1.css" in base
    assert base.index("sg-global-ui-system-v1.css") < base.index("sg-layout-contract-v1.css")
    assert base.index("sg-layout-contract-v1.css") < base.index("sg-connections-unified-v1.css")


def test_shared_layout_contract_defines_reusable_geometry_primitives():
    assert LAYOUT_CSS.exists()
    css = LAYOUT_CSS.read_text(encoding="utf-8")

    for token in (
        "--sg-layout-card-inset:",
        "--sg-layout-nested-inset:",
        "--sg-layout-mobile-inset:",
    ):
        assert token in css

    for selector in (
        ".sg-layout-page",
        ".sg-layout-card",
        ".sg-layout-card-head",
        ".sg-layout-card-body",
        ".sg-layout-nested",
        ".sg-layout-grid",
        ".sg-layout-actions",
    ):
        assert selector in css


def test_connections_consumes_shared_layout_rails_instead_of_local_magic_spacing():
    css = CONNECTIONS_CSS.read_text(encoding="utf-8")

    assert "var(--sg-layout-card-inset)" in css
    assert "var(--sg-layout-nested-inset)" in css
    assert "var(--sg-layout-mobile-inset)" in css

    for stale_geometry in (
        "margin: 0 17px;",
        "calc(var(--sgui-card-padding) * 2)",
        "padding: 0 12px 12px;",
        "margin: 0 12px 12px;",
    ):
        assert stale_geometry not in css


def test_connections_keeps_protocol_specific_css_while_shared_contract_owns_rails():
    css = CONNECTIONS_CSS.read_text(encoding="utf-8")

    for selector in (
        "body.page-connections .cnv1-engine-xray",
        "body.page-connections #xray-xmux",
        "body.page-connections .awgd-shell",
        "body.page-connections #mihomo",
        "body.page-connections .xps2-naiveproxy-card",
    ):
        assert selector in css
