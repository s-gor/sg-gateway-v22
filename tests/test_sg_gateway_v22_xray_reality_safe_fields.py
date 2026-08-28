from __future__ import annotations

from pathlib import Path

from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db
from app.main import create_app


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "app/web/static/sg-xmux-settings-v1.js"


def test_fingerprint_uses_sg_dropdown_instead_of_native_popup() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "data-fingerprint-panel" in script
    assert "xray-fingerprint-picker" in script
    assert "xray-fingerprint-trigger" in script
    assert "xray-fingerprint-menu" in script
    assert "role', 'listbox'" in script
    assert "fingerprint.hidden = true" in script
    assert "fingerprint.value = optionButton.dataset.value" in script
    assert "fingerprint.dispatchEvent(new Event('change', { bubbles: true }))" in script
    assert "fingerprint.style.colorScheme = 'light'" not in script
    assert "item.style.backgroundColor = '#ffffff'" not in script


def test_xray_client_settings_are_two_open_rows() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "configureTwoRowXraySettings" in script
    assert "form.id = 'xray-reality-form'" in script
    assert "fingerprintRow.classList.add('xray-settings-primary')" in script
    assert "identityRow.className = 'xps2-parameter-row is-visible xray-settings-identity'" in script
    assert "details.before(form)" in script
    assert "details.remove()" in script
    assert "serverName.setAttribute('form', form.id)" in script
    assert "submitButton.setAttribute('form', form.id)" in script
    assert "bindRealityCopyActions" in script
    assert "navigator.clipboard.writeText(field.value)" in script
    assert "configureCompactRealityPanel" not in script


def test_xray_client_settings_use_equal_halves() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert ".xray-settings-primary" in script
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in script
    assert ".xray-reality-sni-group" in script
    assert "sniGroup.append(serverNameLabel, submitButton)" in script
    assert "fingerprintRow.append(sniGroup)" in script
    assert ".xray-settings-identity" in script
    assert script.count("grid-template-columns: repeat(2, minmax(0, 1fr))") >= 2
    assert ".xray-copy-icon" in script
    assert "@media (max-width: 900px)" in script


def test_xray_primary_row_resets_legacy_grid_placement() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert (
        ".xray-settings-primary > .xps2-field-mode {\n"
        "        grid-area: fingerprint !important;\n"
        "        width: 100%;\n"
        "        max-width: none !important;"
    ) in script
    assert (
        ".xray-reality-sni-group > .xray-reality-sni,\n"
        "      .cnv1-engine-xray .xray-reality-sni-group > .xray-reality-save {\n"
        "        grid-area: auto !important;\n"
        "        grid-column: auto !important;\n"
        "        grid-row: auto !important;"
    ) in script
    assert (
        ".xray-reality-sni-group > .xray-reality-sni {\n"
        "        grid-column: 1 !important;\n"
        "        grid-row: 1 !important;"
    ) in script
    assert (
        ".xray-reality-sni-group > .xray-reality-save {\n"
        "        grid-column: 2 !important;\n"
        "        grid-row: 1 !important;"
    ) in script


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
