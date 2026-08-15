from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mihomo_meta_is_one_compact_row():
    panel = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert 'class="mhv2-compact-meta"' in panel
    assert ".mhv2-compact-meta" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)" in css


def test_three_mihomo_listeners_share_desktop_row():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "grid-column: 1 / -1;" in css
    assert "Mieru spans the row" not in css


def test_engine_pair_stretches_without_forced_hundred_percent_height():
    css = (ROOT / "app/web/static/sg-preview28-final.css").read_text(encoding="utf-8")
    assert ".cnv1-engine-pair { align-items: stretch; }" in css
    assert "height: auto; align-self: stretch;" in css
    assert "height: 100%; align-self: stretch;" not in css


def test_preview28_css_is_loaded_after_luxury_jade():
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    assert base.index("sg-preview28-final.css") > base.index("sg-luxury-jade-depth-v2.css")
