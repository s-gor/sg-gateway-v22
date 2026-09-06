from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")


def test_connections_css_cache_key_tracks_the_deployed_asset_content():
    asset_name = "sg-connections-unified-v1.css"
    asset_path = ROOT / "app/web/static" / asset_name
    expected = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:16]

    stylesheet_line = next(
        line for line in BASE_TEMPLATE.splitlines() if asset_name in line
    )
    assert f"?v={expected}" in stylesheet_line
    assert "app_version" not in stylesheet_line
