from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
CSS = (ROOT / "app/web/static/sg-readable-typography-v3.css").read_text(encoding="utf-8")


def test_clients_row_double_override_is_removed() -> None:
    assert "Clients list row exact 2× typography" not in CSS
    for marker in (
        "font-size: 34px !important",
        "font-size: 30px !important",
        "min-height: 64px !important",
        "height: 136px",
    ):
        assert marker not in CSS


def test_release_marks_approved_scale_and_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert version.startswith("0.1.0-021.")
    assert manifest["version"] == version
    update = manifest["installer_update"]
    assert update["client_list_row_typography_v020"] == "reverted-to-approved-018-scale"
    assert update["permanent_log_secret_redaction"] is True


def test_only_password_is_interactive_and_sg_admin_is_automatic() -> None:
    assert "collect_automatic_parameters" in INSTALL
    assert INSTALL.count("  read_password\n") == 1
    assert 'read_yes_no "Создать первого клиента sg-admin' not in INSTALL
    assert 'CREATE_SG_ADMIN="1"' in INSTALL
    assert "installer_port_preflight" not in INSTALL
    assert "Первый VPN-клиент sg-admin будет создан автоматически" in INSTALL
    for forbidden in (
        'read_tty "Имя сервера и hostname SSH"',
        'read_tty "Публичный HTTP-порт панели"',
        'read_tty "Reality target"',
        'read_tty "Reality SNI"',
        'read_tty "Порт VLESS Reality TCP"',
    ):
        assert forbidden not in INSTALL


def test_installer_uses_sanitized_permanent_log() -> None:
    assert "sanitize_installer_stream()" in INSTALL
    assert 'sanitize_installer_stream < "$raw_output" >> "$INSTALL_LOG"' in INSTALL
    assert '} 2>&1 | sanitize_installer_stream >> "$INSTALL_LOG"' in INSTALL
    assert "[REDACTED PEM BLOCK]" in INSTALL
    assert "[REDACTED LONG CREDENTIAL]" in INSTALL


def test_sanitizer_redacts_pem_profiles_and_private_values() -> None:
    sample = "\n".join(
        (
            "-----BEGIN CERTIFICATE-----",
            "ABCDEF",
            "-----END CERTIFICATE-----",
            "vless://uuid@example.com:443?encryption=secret",
            "subscription-base64: dmxlc3M6Ly9zZWNyZXQ=",
            "SG_GATEWAY_XRAY_PRIVATE_KEY=secret",
            '{"password":"secret","ok":true}',
            "",
        )
    )
    command = (
        'set +eE; source "$1"; '
        'printf "%s" "$2" | sanitize_installer_stream'
    )
    result = subprocess.run(
        ["bash", "-c", command, "_", str(ROOT / "install.sh"), sample],
        text=True,
        capture_output=True,
        check=True,
    )
    output = result.stdout
    assert "BEGIN CERTIFICATE" not in output
    assert "uuid@example.com" not in output
    assert "dmxlc3M6" not in output
    assert "=secret" not in output
    assert '"password":"secret"' not in output
    assert "[REDACTED PEM BLOCK]" in output
    assert "vless://[REDACTED]" in output


def test_final_success_block_does_not_dump_credentials() -> None:
    final = INSTALL.rsplit("INSTALL_SUCCESS=1", 1)[1]
    assert "subscription-base64" not in final
    assert "vless://" not in final
    assert "hysteria2://" not in final
    assert "mieru://" not in final
    assert "BEGIN CERTIFICATE" not in final
    assert "BEGIN PRIVATE KEY" not in final
    assert "Пароль:       %s" not in final
    assert "print_sg_admin_status" in final
    assert "Профили sg-admin: Reality TCP, XHTTP Reality, AmneziaWG, Mieru" in INSTALL
