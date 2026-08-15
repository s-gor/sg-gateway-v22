from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_global_typography_v2_is_loaded_after_v1():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    v1 = "sg-typography-v1.css"
    v2 = "sg-typography-v2.css"
    assert v1 in base
    assert v2 in base
    assert base.index(v1) < base.index(v2)


def test_global_typography_v2_raises_service_text():
    css = (ROOT / "app/web/static/sg-typography-v2.css").read_text(encoding="utf-8")
    for marker in (
        ".sg-nav-copy small",
        ".mtv1-backup-copy strong",
        ".mtv1-health-row small",
        ".cv2-table th",
        ".cnv1-engine-status",
        ".rtv1-value-card small",
        ".secv1-auth-row small",
        ".hlpv1-topic-copy small",
    ):
        assert marker in css


def test_global_typography_v2_keeps_responsive_protection():
    css = (ROOT / "app/web/static/sg-typography-v2.css").read_text(encoding="utf-8")
    assert "@media (max-width: 1640px)" in css
    assert "@media (max-width: 1480px)" in css
    assert ".mtv1-backup-meta" in css


def test_global_typography_v2_does_not_use_scaling():
    css = (ROOT / "app/web/static/sg-typography-v2.css").read_text(encoding="utf-8")
    assert "transform: scale(" not in css
    assert "zoom:" not in css
