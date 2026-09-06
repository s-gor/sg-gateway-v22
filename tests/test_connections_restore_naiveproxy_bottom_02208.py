from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload).hexdigest()


def test_connections_legacy_geometry_css_is_restored_exactly():
    assert _git_blob_sha(ROOT / "app/web/static/sg-ui-connections-v22-08.css") == "96b396e32560f4f986596eb9cdebcdd060767960"


def test_connections_is_direct_template_not_wrapper():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    assert template.startswith('{% extends "base.html" %}')
    assert 'connections_legacy_8f7481cb.html' not in template
    assert 'class="cnv1-engine-pair sg-ui-grid"' in template
    assert 'class="awgd-card awgd-card-v2"' in template
    assert '{% include "_mihomo_panel.html" %}' in template
    assert 'name="fingerprint"' in template


def test_naiveproxy_is_the_last_connections_block():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")

    note = template.index('class="cnv1-note-panel sg-ljd-card sg-ui-card"')
    naive = template.index('{% include "_naiveproxy_panel.html" %}')
    content_end = template.index('{% endblock %}', naive)

    assert note < naive < content_end
    assert template.count('_naiveproxy_panel.html') == 1
    assert 'sg-naiveproxy-bottom-v1.css' not in template
    assert 'cnv1-layout-grid' not in template
    assert 'cnv1-grid-cell' not in template


def test_restore_has_no_legacy_wrapper_artifacts():
    assert not (ROOT / "app/web/templates/connections_legacy_8f7481cb.html").exists()
    assert not (ROOT / "app/web/static/sg-naiveproxy-bottom-v1.css").exists()
