from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "web" / "static"
TEMPLATES = ROOT / "app" / "web" / "templates"
BASE = TEMPLATES / "base.html"

CANONICAL = (
    "sg-ui-foundation-v22-08.css",
    "sg-ui-layout-v22-08.css",
    "sg-ui-components-v22-08.css",
)

LEGACY_PAGE_NAMESPACE_MARKERS = (
    ".sv1-",
    ".cv2-",
    ".cv10-",
    ".cv15-",
    ".cnv1-",
    ".xps2-",
    ".xmux1-",
    ".r096-",
    ".secv2-",
    ".ts2-",
    ".mtv2-",
    ".mtv31-",
    ".mtv32-",
    ".ob49-",
    ".hlpv1-",
    ".dv16-",
    ".cd10-",
)

REQUIRED_PRIMITIVES = (
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
    ".sg-ui-card",
    ".sg-ui-badge",
    ".sg-ui-button",
)


def _canonical_sources() -> dict[str, str]:
    missing = [name for name in CANONICAL if not (STATIC / name).is_file()]
    assert not missing, f"missing canonical 22.08 CSS layers: {missing}"
    return {name: (STATIC / name).read_text(encoding="utf-8") for name in CANONICAL}


def test_02208_has_exact_three_canonical_shared_css_layers():
    sources = _canonical_sources()
    assert tuple(sources) == CANONICAL


def test_02208_common_css_owns_semantic_primitives_not_legacy_page_namespaces():
    sources = _canonical_sources()
    combined = "\n".join(sources.values())

    for primitive in REQUIRED_PRIMITIVES:
        assert primitive in combined, f"missing canonical UI primitive: {primitive}"

    for marker in LEGACY_PAGE_NAMESPACE_MARKERS:
        assert marker not in combined, f"legacy page namespace leaked into common CSS: {marker}"


def test_02208_layout_has_one_outer_page_padding_owner():
    sources = _canonical_sources()
    layout = sources["sg-ui-layout-v22-08.css"]

    content_blocks = re.findall(r"\.sg-content\s*\{([^}]+)\}", layout, flags=re.S)
    assert len(content_blocks) == 1, "sg-content must have exactly one canonical layout block"
    assert re.search(r"padding-inline\s*:\s*(?:var\([^)]*30px[^)]*\)|30px)", content_blocks[0])

    page_blocks = re.findall(r"\.sg-ui-page\s*\{([^}]+)\}", layout, flags=re.S)
    assert page_blocks, "sg-ui-page layout primitive is missing"
    assert all("padding-inline" not in block for block in page_blocks)
    assert all("margin-inline" not in block for block in page_blocks)


def test_02208_base_loads_canonical_layers_once_via_asset_helper():
    base = BASE.read_text(encoding="utf-8")

    for name in CANONICAL:
        assert base.count(name) == 1, f"{name} must be loaded exactly once by base.html"

    assert "static_asset(" in base, "base.html must use the shared deterministic asset helper"
    for name in CANONICAL:
        assert re.search(rf"static_asset\(['\"]{re.escape(name)}['\"]\)", base)


def test_02208_canonical_layers_keep_geometry_theme_independent():
    sources = _canonical_sources()
    layout = sources["sg-ui-layout-v22-08.css"]

    theme_selector = re.compile(
        r"(?:\[data-theme[^]]*\]|\.theme-(?:dark|light))[^\{]*\{",
        flags=re.I,
    )
    assert not theme_selector.search(layout), (
        "canonical layout must contain no dark/light selectors; theme changes belong to tokens/components"
    )


def test_02208_new_page_css_cannot_take_back_outer_shell_geometry():
    for path in sorted(STATIC.glob("sg-ui-*-v22-08.css")):
        if path.name in CANONICAL:
            continue
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"\.sg-content\s*\{", source), f"{path.name} must not own .sg-content"
        assert not re.search(r"\.sg-shell\s*\{", source), f"{path.name} must not own .sg-shell"
        assert not re.search(r"\.sg-ui-page\s*\{[^}]*(?:padding-inline|margin-inline)\s*:", source, re.S), (
            f"{path.name} must not introduce page outer horizontal compensation"
        )
