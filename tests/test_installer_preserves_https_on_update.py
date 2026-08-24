from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return INSTALLER.split(start, 1)[1].split(end, 1)[0]


def test_update_preserves_complete_https_state() -> None:
    helper = _section(
        "saved_https_access() {",
        "\nstage_systemd_units() {",
    )

    assert 'state.get("https_ready")' in helper
    assert 'state.get("domain")' in helper
    assert 'state.get("certificate_path")' in helper
    assert 'state.get("key_path")' in helper
    assert "public_port != panel_port" in helper
    assert "ssl_certificate" in helper
    assert "ssl_certificate_key" in helper
    assert "server_name" in helper
    assert "listen_pattern" in helper


def test_update_does_not_replace_working_https_with_http() -> None:
    stage = _section(
        "stage_systemd_units() {",
        "\nstage_firewall_and_network() {",
    )

    assert 'https_domain="$(saved_https_access)"' in stage
    assert 'if [[ -n "$https_domain" ]]; then' in stage
    assert "Сохраняю рабочий HTTPS" in stage
    assert stage.index('if [[ -n "$https_domain" ]]; then') < stage.index(
        "cat > /etc/nginx/sites-available/sg-gateway"
    )


def test_final_update_check_uses_real_https_domain() -> None:
    check = _section(
        "stage9_verify_nginx() {",
        "\nrun_final_stage() {",
    )
    helper = _section(
        "http_wait_resolved_https_json() {",
        "\nhttp_wait_file_match() {",
    )

    assert (
        'http_wait_resolved_https_json "$https_domain" "$PANEL_PORT" '
        '"sg-gateway-panel" 15'
    ) in check
    assert 'local url="https://${domain}:${port}/health"' in helper
    assert '--resolve "${domain}:${port}:127.0.0.1"' in helper
    assert "domain, certificate and Nginx config preserved" in check


def test_real_renewal_hook_is_in_transactional_backup() -> None:
    assert (
        "etc/letsencrypt/renewal-hooks/deploy/"
        "reload-sg-gateway-nginx.sh"
    ) in INSTALLER


def test_final_output_keeps_https_address() -> None:
    assert "final_https_domain" in INSTALLER
    assert "https://%s:%s" in INSTALLER
