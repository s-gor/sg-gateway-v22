from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "app/web/static/sg-awg-dual-v1.css"


def test_xray_empty_parameter_rows_are_hidden() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert '.xps2-parameter-row[data-profile-panel="reality_tcp"]' in css
    assert '.xps2-parameter-row[data-profile-panel="xhttp_reality"]' in css
    assert "display: none !important" in css


def test_xray_fingerprint_is_a_compact_responsive_row() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".xps2-parameter-row[data-fingerprint-panel]" in css
    assert "display: flex !important" in css
    assert "flex: 0 1 420px" in css
    assert ".xps2-parameter-row[data-fingerprint-panel] .xps2-parameter-title" in css
    assert "flex-direction: column" in css


def test_xray_apply_actions_use_the_same_compact_inset() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".page-connections .xps2-actions" in css
    assert "margin: 0 18px" in css
    assert "padding: 14px 16px" in css


def test_xray_reality_fields_have_explicit_symmetric_placement() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".page-connections .cnv1-engine-xray > .cnv1-advanced" in css
    assert "margin: 0 36px 18px" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".cnv1-form-grid > label:nth-child(1)" in css
    assert ".cnv1-form-grid > label:nth-child(4)" in css
    assert "grid-column: 1 / -1" in css


def test_xray_reality_public_key_is_a_single_line_control() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert 'textarea[name="public_key"]' in css
    assert "min-height: 42px" in css
    assert "resize: none" in css
