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
    assert "grid-template-columns: minmax(0, 1fr) minmax(280px, 420px)" in css
    assert ".xps2-parameter-row[data-fingerprint-panel] .xps2-field-mode > span" in css
    assert "@media (max-width: 900px)" in css
