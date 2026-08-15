from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_global_typography_css_is_loaded_last():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    marker = "sg-typography-v1.css"
    assert marker in base
    assert base.index("{% block head %}{% endblock %}") < base.index(marker)


def test_global_typography_has_readable_floor():
    css = (ROOT / "app/web/static/sg-typography-v1.css").read_text(encoding="utf-8")
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


def test_global_typography_protects_maintenance_layout():
    css = (ROOT / "app/web/static/sg-typography-v1.css").read_text(encoding="utf-8")
    assert "overflow-wrap: anywhere" in css
    assert ".mtv1-backup-row" in css
    assert ".mtv1-backup-meta" in css
    assert "@media (max-width: 1500px)" in css


def test_global_typography_does_not_use_transform_scaling():
    css = (ROOT / "app/web/static/sg-typography-v1.css").read_text(encoding="utf-8")
    assert "transform: scale(" not in css
    assert "zoom:" not in css
