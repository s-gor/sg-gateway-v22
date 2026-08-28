from __future__ import annotations

from pathlib import Path

from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db
from app.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.js"
CSS_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.css"


def test_fingerprint_native_menu_uses_readable_theme_colors() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "data-fingerprint-panel" in script
    assert "colorScheme" in script
    assert "querySelectorAll('option, optgroup')" in script
    assert "getComputedStyle(fingerprint)" in script


def test_reality_panel_keeps_only_sni_editable_and_adds_copy_actions() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "configureCompactRealityPanel" in script
    assert "hostField.closest('label')?.remove()" in script
    assert "portField.closest('label')?.remove()" in script
    assert "field.readOnly = true" in script
    assert "field.removeAttribute('name')" in script
    assert "xray-reality-copy" in script
    assert "navigator.clipboard.writeText(field.value)" in script
    assert "Сохранить SNI" in script
    assert "bindRealityPortToApply" not in script
    assert "reality_tcp_port" not in script


def test_reality_panel_has_compact_two_row_layout() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".xray-reality-compact-grid" in css
    assert 'grid-template-areas:\n    "sni sni"\n    "public short"' in css
    assert ".xray-reality-value-row" in css
    assert ".xray-reality-copy" in css
    assert "@media (max-width: 760px)" in css


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
