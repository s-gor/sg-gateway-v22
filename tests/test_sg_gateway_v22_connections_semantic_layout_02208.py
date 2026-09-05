from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "web" / "templates" / "connections.html"
STATIC = ROOT / "app" / "web" / "static"
PAGE_CSS = STATIC / "sg-ui-connections-v22-08.css"


def test_02208_connections_loads_one_page_css_via_shared_asset_helper():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert template.count("sg-ui-connections-v22-08.css") == 1
    assert re.search(
        r"static_asset\(['\"]sg-ui-connections-v22-08\.css['\"]\)",
        template,
    )


def test_02208_connections_all_page_assets_use_late_shared_asset_slot():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "{% block head %}" not in template
    page_styles = template.split("{% block page_styles %}", 1)[1].split("{% endblock %}", 1)[0]
    for asset in (
        "sg-connections-visual-v1.css",
        "sg-xray-profiles-v2.css",
        "sg-xmux-settings-v1.css",
        "sg-awg-dual-v1.css",
        "sg-ui-connections-v22-08.css",
    ):
        assert page_styles.count(asset) == 1
        assert re.search(rf"static_asset\(['\"]{re.escape(asset)}['\"]\)", page_styles)
    assert "?v={{ app_version }}" not in page_styles


def test_02208_connections_outer_dom_uses_canonical_semantic_layout():
    template = TEMPLATE.read_text(encoding="utf-8")

    required_pairs = (
        ("cnv1-page", "sg-ui-page"),
        ("cnv1-heading", "sg-ui-page-head"),
        ("cnv1-heading-actions", "sg-ui-actions"),
        ("cnv1-engine-xray", "sg-ui-card"),
        ("cnv1-endpoint-card", "sg-ui-nested"),
        ("cnv1-engine-pair", "sg-ui-grid"),
        ("cnv1-note-panel", "sg-ui-card"),
    )
    for legacy, semantic in required_pairs:
        assert re.search(
            rf'class="[^"]*\b{re.escape(legacy)}\b[^"]*\b{re.escape(semantic)}\b[^"]*"',
            template,
        ), f"Connections must pair {legacy} with {semantic} during strangler migration"


def test_02208_connections_page_css_cannot_own_global_shell_or_outer_page_padding():
    assert PAGE_CSS.is_file(), "Connections must have a dedicated 22.08 component CSS"
    source = PAGE_CSS.read_text(encoding="utf-8")

    assert ".sg-content" not in source
    assert ".sg-shell" not in source
    assert not re.search(
        r"\.sg-ui-page\s*\{[^}]*(?:padding-inline|margin-inline)\s*:",
        source,
        flags=re.S,
    )
    assert "--sg-layout-" not in source, "22.07 compensation tokens must not leak into 22.08 Connections CSS"
    assert "calc(" not in source, "Connections must not rebuild cumulative rail offsets with calc()"


def test_02208_connections_page_css_uses_canonical_rail_and_component_tokens():
    source = PAGE_CSS.read_text(encoding="utf-8")

    assert ".sg-ui-rail" in source
    assert "var(--sg-ui-rail-inset" in source
    assert "var(--sg-ui-grid-gap" in source
    assert "var(--sg-ui-card-radius" in source


def test_02208_connections_preserves_partial_boundaries_and_functional_ids():
    template = TEMPLATE.read_text(encoding="utf-8")

    for include in (
        '_xray_xmux_settings.html',
        '_awg31_panel.html',
        '_mihomo_panel.html',
    ):
        assert f'{{% include "{include}" %}}' in template

    partials = (
        (ROOT / "app" / "web" / "templates" / "_xray_xmux_settings.html").read_text(encoding="utf-8")
        + (ROOT / "app" / "web" / "templates" / "_mihomo_panel.html").read_text(encoding="utf-8")
    )
    for required in (
        'id="xray-profiles"',
        'id="xps2-form"',
        'id="xray-xmux"',
        'id="awg-dns"',
        'id="mihomo"',
    ):
        assert required in template or required in partials


def test_02208_connections_is_detached_from_legacy_routing_page_frame():
    legacy = (STATIC / "sg-page-frame-routing-v1.css").read_text(encoding="utf-8")
    assert ".cnv1-page" not in legacy
    assert ".cnv1-heading" not in legacy
