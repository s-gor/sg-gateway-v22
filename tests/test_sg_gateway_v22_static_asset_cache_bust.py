from __future__ import annotations

import hashlib
from pathlib import Path

import app.version as version_module


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "app/main.py").read_text(encoding="utf-8")


def test_connections_css_cache_key_tracks_the_deployed_asset_content():
    asset_name = "sg-connections-unified-v1.css"
    asset_path = ROOT / "app/web/static" / asset_name
    expected = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:16]

    cache_key = getattr(version_module, "get_static_asset_version", None)
    assert callable(cache_key), "static asset cache key helper is missing"
    assert cache_key(asset_name) == expected

    assert '"static_asset_version": get_static_asset_version' in MAIN_SOURCE
    assert (
        "url_for('static', filename='sg-connections-unified-v1.css', "
        "v=static_asset_version('sg-connections-unified-v1.css'))"
    ) in BASE_TEMPLATE
    assert (
        "sg-connections-unified-v1.css') }}?v={{ app_version }}-connections-unified-v1"
        not in BASE_TEMPLATE
    )
