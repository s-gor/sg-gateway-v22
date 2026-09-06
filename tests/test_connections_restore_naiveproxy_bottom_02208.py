from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload).hexdigest()


def test_connections_legacy_layout_is_restored_exactly():
    assert _git_blob_sha(ROOT / "app/web/templates/connections.html") == "1276bcec589dcd3a94b7c34dc11b6dfa2a5abd04"
    assert _git_blob_sha(ROOT / "app/web/static/sg-ui-connections-v22-08.css") == "96b396e32560f4f986596eb9cdebcdd060767960"


def test_naiveproxy_is_appended_only_after_legacy_connections_page():
    wrapper = (ROOT / "app/web/templates/connections_02208.html").read_text(encoding="utf-8")
    legacy = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")

    assert '{% extends "connections.html" %}' in wrapper
    assert "{{ super() }}" in wrapper
    assert wrapper.index("{{ super() }}") < wrapper.index('_naiveproxy_panel.html')
    assert wrapper.count('_naiveproxy_panel.html') == 1
    assert "sg-naiveproxy-bottom-v1.css" in wrapper
    assert "naiveproxy" not in legacy.lower()
    assert 'render_template(\n            "connections_02208.html"' in main


def test_naiveproxy_bottom_block_has_isolated_full_width_contract():
    css = (ROOT / "app/web/static/sg-naiveproxy-bottom-v1.css").read_text(encoding="utf-8")
    assert ".sg-naiveproxy-bottom" in css
    assert "width: 100%;" in css
    assert ".cnv1-engine-pair" not in css
    assert ".mhv2-" not in css
    assert ".awgd-" not in css
