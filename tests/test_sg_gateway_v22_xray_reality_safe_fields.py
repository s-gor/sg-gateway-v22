from __future__ import annotations

from pathlib import Path

from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db
from app.main import create_app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "app/web/templates/connections.html"
SCRIPT_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.js"
CSS_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.css"


def test_fingerprint_native_menu_uses_readable_theme_colors() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "data-fingerprint-panel" in script
    assert "colorScheme" in script
    assert "querySelectorAll('option, optgroup')" in script
    assert "getComputedStyle(fingerprint)" in script


def test_xray_client_settings_are_two_open_rows() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'id="xray-reality-form"' in template
    assert 'class="xps2-parameter-row is-visible xray-settings-primary"' in template
    assert 'class="xps2-parameter-row is-visible xray-settings-identity"' in template
    assert 'form="xray-reality-form"' in template
    assert 'name="server_name"' in template
    assert 'data-copy-target="xray-reality-public-key"' in template
    assert 'data-copy-target="xray-reality-short-id"' in template
    assert 'id="xray-reality-public-key"' in template
    assert 'id="xray-reality-short-id"' in template
    assert "Reality-ключи и общий адрес" not in template
    assert "configureCompactRealityPanel" not in script
    assert "bindRealityCopyActions" in script
    assert "navigator.clipboard.writeText(field.value)" in script


def test_xray_client_settings_have_compact_responsive_grid() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".xray-settings-primary" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto" in css
    assert ".xray-settings-identity" in css
    assert "grid-template-columns: minmax(0, 1.45fr) minmax(260px, .55fr)" in css
    assert ".xray-copy-icon" in css
    assert "@media (max-width: 900px)" in css


def test_public_xray_form_changes_only_sni(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    init_db()

    current = get_connection_settings("xray")
    trusted_config = dict(current.config)
    trusted_config.update(
        {
            "server_name": "old.example.com",
            "public_key": "TRUSTED_REALITY_PUBLIC_KEY",
            "short_id": "0123456789abcdef",
            "reality_tcp_port": 443,
            "trusted_marker": "must-survive",
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
            "host": "attacker.example.net",
            "port": "9443",
            "server_name": "new.example.com",
            "public_key": "ATTACKER_REPLACEMENT_KEY",
            "short_id": "deadbeefdeadbeef",
            "trusted_marker": "attacker-value",
        },
    )

    saved = get_connection_settings("xray")
    assert response.status_code == 302
    assert saved.host == "203.0.113.10"
    assert saved.port == 443
    assert saved.config["reality_tcp_port"] == 443
    assert saved.config["server_name"] == "new.example.com"
    assert saved.config["public_key"] == "TRUSTED_REALITY_PUBLIC_KEY"
    assert saved.config["short_id"] == "0123456789abcdef"
    assert saved.config["trusted_marker"] == "must-survive"
