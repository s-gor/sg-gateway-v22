from pathlib import Path

from jinja2 import Environment


def test_global_light_theme_fix1():
    root = Path(__file__).resolve().parents[1]
    css = (
        root / "app/web/static/sg-light-latte-graphite-v1.css"
    ).read_text(encoding="utf-8")

    assert css.count("{") == css.count("}")
    assert 'html[data-theme="light"]' in css
    assert 'html[data-theme="dark"]' not in css

    required = (
        ".sg-nav-item.active",
        ".sv1-summary-card",
        ".cv2-summary-card",
        ".cnv1-summary-card",
        ".rtux2-rules-card",
        ".mtv2-panel",
        ".secv2-workflow",
        ".hlpv1-article-panel",
    )
    for selector in required:
        assert selector in css

    assert "--sg-bg: #d6dee3" in css
    assert "--sg-panel: #e9eef1" in css
    assert "--sg-text: #172531" in css
    assert "--sg-blue: #315d82" in css
