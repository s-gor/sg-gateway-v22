from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connections_uses_current_canonical_geometry_contract():
    css = (ROOT / "app/web/static/sg-ui-connections-v22-08.css").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    mihomo = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")

    assert "calc(" not in css
    assert "margin-inline" not in css
    assert '<div class="awgd-inner-rail sg-ui-rail">' in template
    assert '<div class="mhv2-inner-rail sg-ui-rail">' in mihomo


def test_connections_is_direct_template_not_wrapper():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    assert template.startswith('{% extends "base.html" %}')
    assert 'connections_legacy_8f7481cb.html' not in template
    assert 'class="cnv1-engine-pair sg-ui-grid"' in template
    assert 'class="awgd-card awgd-card-v2"' in template
    assert '{% include "_mihomo_panel.html" %}' in template
    assert 'name="fingerprint"' in template


def test_naiveproxy_precedes_final_connections_note():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    naive = template.index('{% include "_naiveproxy_panel.html" %}')
    note = template.index('class="cnv1-note-panel sg-ljd-card sg-ui-card"')
    content_end = template.index('{% endblock %}', note)

    assert naive < note < content_end
    assert template.count('_naiveproxy_panel.html') == 1
    assert 'sg-naiveproxy-bottom-v1.css' not in template
    assert 'cnv1-layout-grid' not in template
    assert 'cnv1-grid-cell' not in template


def test_restore_has_no_legacy_wrapper_artifacts():
    assert not (ROOT / "app/web/templates/connections_legacy_8f7481cb.html").exists()
    assert not (ROOT / "app/web/static/sg-naiveproxy-bottom-v1.css").exists()
