from pathlib import Path


def test_global_ui_unification_fix1():
    root = Path(__file__).resolve().parents[1]
    css = (
        root / "app/web/static/sg-global-ui-system-v1.css"
    ).read_text(encoding="utf-8")

    assert css.count("{") == css.count("}")

    for token in (
        "--sgui-topbar-height",
        "--sgui-page-gap",
        "--sgui-radius-card",
        "--sgui-button-height",
        "--sgui-badge-height",
        "--sgui-page-title",
    ):
        assert token in css

    for page in (
        ".sv1-page",
        ".cv2-page",
        ".cnv1-page",
        ".rtux2-page",
        ".mtv2-page",
        ".secv2-page",
        ".hlpv1-page",
    ):
        assert page in css

    assert ".sg-body .button" in css
    assert ".sv1-state-pill" in css
    assert ".secv2-list > div" in css
    assert ".mtv2-panel" in css
    assert ".secv2-workflow" in css
