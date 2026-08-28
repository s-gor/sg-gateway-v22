from __future__ import annotations

from pathlib import Path

from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db
from app.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.js"


def test_fingerprint_native_menu_uses_readable_theme_colors() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "data-fingerprint-panel" in script
    assert "colorScheme" in script
    assert "querySelectorAll('option, optgroup')" in script
    assert "getComputedStyle(fingerprint)" in script


def test_reality_identity_fields_are_read_only_and_not_submitted() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'textarea[name="public_key"]' in script
    assert 'input[name="short_id"]' in script
    assert "field.readOnly = true" in script
    assert "field.removeAttribute('name')" in script
    assert "aria-readonly" in script


def test_public_xray_form_syncs_listener_port_and_preserves_identity(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    init_db()

    current = get_connection_settings("xray")
    trusted_config = dict(current.config)
    trusted_config.update(
        {
            "public_key": "TRUSTED_REALITY_PUBLIC_KEY",
            "short_id": "0123456789abcdef",
            "reality_tcp_port": 443,
        }
    )
    assert update_connection_settings(
        "xray", "203.0.113.10", 443, trusted_config
    ) is True

    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})
    response = client.post(
        "/connections/xray",
        data={
            "host": "203.0.113.10",
            "port": "9443",
            "server_name": "www.bing.com",
            "public_key": "ATTACKER_REPLACEMENT_KEY",
            "short_id": "deadbeefdeadbeef",
        },
    )

    saved = get_connection_settings("xray")
    assert response.status_code == 302
    assert saved.port == 9443
    assert saved.config["reality_tcp_port"] == 9443
    assert saved.config["public_key"] == "TRUSTED_REALITY_PUBLIC_KEY"
    assert saved.config["short_id"] == "0123456789abcdef"
