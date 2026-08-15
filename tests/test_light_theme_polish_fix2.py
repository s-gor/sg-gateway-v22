from pathlib import Path


def test_light_theme_polish_fix2_css():
    root = Path(__file__).resolve().parents[1]
    css = (
        root / "app/web/static/sg-light-theme-polish-fix2.css"
    ).read_text(encoding="utf-8")

    assert css.count("{") == css.count("}")
    assert 'html[data-theme="dark"]' not in css

    assert ".sg-theme-moon" in css
    assert ".sg-theme-sun" in css
    assert 'html[data-theme="light"] .sg-theme-moon' in css
    assert 'html[data-theme="light"] .sg-theme-sun' in css

    assert 'html[data-theme="light"] .secv2-progress' in css
    assert 'html[data-theme="light"] .secv2-checks > div' in css
    assert 'html[data-theme="light"] .secv2-list > div' in css
    assert 'background: #e4eaed' in css
