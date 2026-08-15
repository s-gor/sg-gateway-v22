from __future__ import annotations

import os
from pathlib import Path

from app.config import load_config

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
OUTBOUNDS = (ROOT / "app/web/templates/outbounds.html").read_text(encoding="utf-8")
ROUTING = (ROOT / "app/web/templates/routing.html").read_text(encoding="utf-8")


def test_single_visible_spinner_and_quiet_technical_output():
    assert "run_quiet()" in INSTALLER
    assert 'local frames=(\'|\' \'/\' \'-\' "\\\\")' in INSTALLER
    assert "tee -a" not in INSTALLER
    assert "spinner_loop" not in INSTALLER
    assert "--quiet --disable-pip-version-check --no-input" in INSTALLER
    assert "Полный технический журнал" in INSTALLER
    assert "-- No entries --" not in INSTALLER


def test_same_ec2_retry_identity_ip_country_and_password_only_prompt():
    for token in (
        "detect_public_ip()",
        "checkip.amazonaws.com",
        "latest/meta-data/public-ipv4",
        "detect_country_code()",
        "collect_automatic_parameters",
        "read_password",
        "hostnamectl set-hostname",
        "SG_GATEWAY_CREATE_SG_ADMIN",
        "SG_GATEWAY_SERVER_NAME",
        "SG_GATEWAY_COUNTRY_CODE",
        "Повторный запуск выполняется на этом же EC2",
    ):
        assert token in INSTALLER
    assert "installer_port_preflight" not in INSTALLER
    assert 'read_yes_no "Создать первого клиента sg-admin' not in INSTALLER
    assert 'CREATE_SG_ADMIN="1"' in INSTALLER


def test_domain_is_optional_and_panel_uses_public_ip():
    assert "Домен не обязателен" in INSTALLER
    assert "Панель:       http://%s:%s" in INSTALLER
    assert "certbot" in INSTALLER
    assert "domain" not in " ".join(
        line for line in INSTALLER.splitlines() if "collect_automatic_parameters" in line
    ).lower()


def test_client_identity_guard_and_backup_rollback_exist():
    assert "fingerprint_clients()" in INSTALLER
    assert "client-identities-before.sha256" in INSTALLER
    assert "verify_client_identities_after_update" in INSTALLER
    assert "restore_backup()" in INSTALLER
    assert "service-state.tsv" in INSTALLER


def test_server_identity_is_visible_in_app(monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_SERVER_NAME", "sg-gateway-fr")
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")
    cfg = load_config()
    assert cfg.server_name == "sg-gateway-fr"
    assert cfg.public_address == "203.0.113.10"
    assert cfg.country_code == "fr"
    assert "server_identity.name" in BASE
    assert "country_flag_url(server_identity.country_code)" in BASE


def test_warp_is_managed_in_outbounds_without_old_create_modal():
    assert "WARP Outbound" in OUTBOUNDS
    create_form = OUTBOUNDS.split("outbounds_warp_create", 1)[1].split("</form>", 1)[0]
    assert "data-sg-confirm" not in create_form
    assert 'data-r096-tab="warp"' not in ROUTING
    assert 'data-r096-panel="warp"' not in ROUTING
    assert "url_for('outbounds')" in ROUTING
    assert "Через SG-Gateway" in ROUTING
    assert "Через WARP" in ROUTING
    assert "Заблокировать" in ROUTING


def test_warp_backend_contract_is_native_and_fail_closed():
    warp = (ROOT / "app/routing/warp.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/routing/runtime.py").read_text(encoding="utf-8")
    assert '"protocol": "wireguard"' in warp
    assert '"noKernelTun": True' in warp
    assert '"mtu": profile.mtu' in warp
    assert "routing_uses_warp" in warp
    assert "ensure_routing_supported" in warp
    assert "WARP" in runtime
