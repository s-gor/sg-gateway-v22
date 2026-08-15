from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_product_constant_is_udp_585():
    source = (ROOT / "app/constants.py").read_text(encoding="utf-8")
    assert "AMNEZIAWG_UDP_PORT = 585" in source


def test_database_default_and_bundled_database_are_udp_585():
    source = (ROOT / "app/db.py").read_text(encoding="utf-8")
    assert '"port": AMNEZIAWG_UDP_PORT' in source
    with sqlite3.connect(ROOT / "data/sg-gateway.sqlite") as connection:
        port = connection.execute(
            "SELECT port FROM connection_settings WHERE engine='amneziawg'"
        ).fetchone()[0]
    assert port == 585


def test_seed_backend_ui_and_installer_enforce_udp_585():
    seed = (ROOT / "app/install_seed.py").read_text(encoding="utf-8")
    settings = (ROOT / "app/connections/settings.py").read_text(encoding="utf-8")
    ui = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "awg_port = AMNEZIAWG_UDP_PORT" in seed
    assert 'engine == "amneziawg"' in settings
    assert 'min="585" max="585"' in ui
    assert 'DEFAULT_AWG_PORT="585"' in installer
    assert 'AmneziaWG invariant: UDP {AMNEZIAWG_UDP_PORT}' in installer
    assert "AmneziaWG runtime does not listen on UDP 585" in installer


def test_no_standard_wireguard_51820_remains_in_managed_text_sources():
    managed = [
        ROOT / "app", ROOT / "hostd", ROOT / "deploy", ROOT / "install.sh",
        ROOT / "release-manifest.json", ROOT / "SG-GATEWAY-021-REQUIREMENTS.json",
    ]
    offenders = []
    for item in managed:
        paths = item.rglob("*") if item.is_dir() else [item]
        for path in paths:
            if not path.is_file() or path.suffix in {".svg", ".dat", ".sqlite"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "51820" in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_rejected_double_typography_is_not_declared():
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["clients_ui"]["list_row_typography"] == "approved-v018-scale-restored"
    css = (ROOT / "app/web/static/sg-readable-typography-v3.css").read_text(encoding="utf-8")
    assert "exact 2× typography" not in css
    assert "height: 136px" not in css
