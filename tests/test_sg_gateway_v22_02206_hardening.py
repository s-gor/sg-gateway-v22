from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from app.clients.mieru_router import MieruRouterError, build_mieru_router_uri
from app.clients.mieru_router_http import register_mieru_router_http
from app.security import operation_jobs
from app.security.operation_jobs import _panel_update_result, _panel_update_runtime_attention


ROOT = Path(__file__).resolve().parents[1]


def test_stable_02206_identity_is_consistent() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    build_id = (ROOT / "BUILD-ID").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert version == "0.1.0-022.06"
    assert build_id == "MAIN-02206-STABLE"
    assert manifest["version"] == version
    assert manifest["build"] == build_id
    assert manifest["channel"] == "stable-02206"
    assert manifest["status"] == "STABLE"
    assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02206"
    assert manifest["next_development_line"] == "0.1.0-022.07"


def test_dev_deploy_identity_matches_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    token = version.rsplit("-", 1)[1].replace(".", "")
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    uninstaller = (ROOT / "deploy" / "full-uninstall-ubuntu.sh").read_text(encoding="utf-8")

    assert f'VERSION="{version}"' in installer
    assert f'INSTALLER_BUILD="{token}-full-clean-dual-stack"' in installer
    assert f'INSTALL_LOG="/var/log/sg-gateway-installer-{token}.log"' in installer
    assert f'RESUME_FILE="/root/sg-gateway-{token}-installer-resume.env"' in installer
    assert f'Запускаю полный мастер SG-Gateway {version}' in installer
    assert f'Мастер установки SG-Gateway {version} запущен' in installer
    assert installer.count(f'before-sg-gateway-{token}') == 2
    assert "SG-Gateway V22 vendor bundle:" in installer

    assert f'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-{token}.log"' in uninstaller
    assert f"SG-Gateway {version} · ПОЛНОЕ УДАЛЕНИЕ" in uninstaller


def test_awg3_repair_does_not_enable_service_without_generated_config() -> None:
    body = (ROOT / "deploy" / "repair-awg3-runtime.sh").read_text(encoding="utf-8")
    active = body.split("if (( ACTIVE_CLIENTS > 0 )); then", 1)[1].split("\nelse\n  systemctl stop", 1)[0]
    assert active.index('if [[ -s "$CONFIG" ]]') < active.index('systemctl enable "$SERVICE"')
    assert 'else\n    systemctl stop "$SERVICE" >/dev/null 2>&1 || true\n    systemctl disable "$SERVICE" >/dev/null 2>&1 || true\n    log "AWG3 runtime восстановлен.' in active


def test_mieru_router_uri_uses_compact_router_contract() -> None:
    source = (
        "mierus://demo:secret@example.com?profile=default&port=2099&protocol=TCP"
        "&multiplexing=MULTIPLEXING_LOW&handshake-mode=HANDSHAKE_STANDARD#Phone"
    )
    assert build_mieru_router_uri(source) == (
        "mieru://demo:secret@example.com:2099?transport=TCP#Phone"
    )


def test_mieru_router_uri_rejects_bad_port() -> None:
    with pytest.raises(MieruRouterError):
        build_mieru_router_uri("mierus://demo:secret@example.com?port=70000&protocol=TCP")


def test_panel_update_result_keeps_failure_stage_exit_and_rollback() -> None:
    log = """
[SG-Gateway Update] [3/6] Обновление исходников SG-Gateway + WSGI migration
[SG-Gateway Update] ERROR: synthetic deploy failure
[SG-Gateway Update] ROLLBACK: restoring the pre-update server state...
[SG-Gateway Update] ROLLBACK OK. Backup: /root/sg-gateway-update-safety/20260819-100000-before-update
[SG-Gateway] ОШИБКА: код 17
"""
    result = _panel_update_result("failed", log)
    assert result["stage_number"] == 3
    assert "Обновление исходников" in result["stage_label"]
    assert result["reason"] == "synthetic deploy failure"
    assert result["exit_code"] == 17
    assert result["rollback_ok"] is True
    assert "база и клиенты" in result["restored"]
    assert result["backup"].endswith("before-update")


def test_panel_update_result_success_has_version_commit_and_three_checks() -> None:
    log = """
[SG-Gateway Update] [6/6] Проверка HTTPS, Clients, Nginx и runtime
[SG-Gateway Update] [OK] Проверка HTTPS, Clients, Nginx и runtime
Panel Update baseline: abcdef1234567890abcdef1234567890abcdef12 (dev-02206)
[SG-Gateway Update] VERSION: 0.1.0-022.06
"""
    result = _panel_update_result("success", log)
    assert result["exit_code"] == 0
    assert result["version"] == "0.1.0-022.06"
    assert result["commit"].startswith("abcdef123456")
    assert result["checks"] == {"panel": "ok", "clients": "ok", "https": "ok"}


def test_panel_update_success_guides_explicit_missing_awg3_to_maintenance(monkeypatch) -> None:
    monkeypatch.setattr(
        operation_jobs,
        "runtime_engine_state",
        lambda engine: {"known": True, "ready": False, "missing": ["awg"]},
    )
    attention = _panel_update_runtime_attention()
    assert attention["needs_repair"] is True
    assert attention["kind"] == "awg3_runtime_repair"
    assert attention["target_url"] == "/maintenance?tab=updates"
    assert attention["target_label"] == "Открыть AWG3 Runtime"

    monkeypatch.setattr(
        operation_jobs,
        "runtime_engine_state",
        lambda engine: {"known": True, "ready": True, "missing": []},
    )
    assert _panel_update_runtime_attention() == {}

    monkeypatch.setattr(
        operation_jobs,
        "runtime_engine_state",
        lambda engine: {"known": False, "ready": True, "missing": []},
    )
    assert _panel_update_runtime_attention() == {}


def test_mieru_router_qr_is_registered_only_in_production_entrypoint() -> None:
    production = (ROOT / "app" / "production.py").read_text(encoding="utf-8")
    http = (ROOT / "app" / "clients" / "mieru_router_http.py").read_text(encoding="utf-8")
    assert "register_mieru_router_http(app)" in production
    assert '"/clients/<int:client_id>/mieru-router/qr"' in http
    assert '"/clients/<int:client_id>/devices/<int:device_id>/mieru-router/qr"' in http
    assert "build_qr_svg(payload)" in http


def test_mieru_router_http_registration_is_idempotent() -> None:
    app = Flask("mieru-router-idempotency")
    register_mieru_router_http(app)
    register_mieru_router_http(app)
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.count("mieru_router_qr") == 1
    assert endpoints.count("device_mieru_router_qr") == 1


def test_mieru_ui_keeps_all_actions_visible_and_smart_qr_metadata() -> None:
    script = (ROOT / "app" / "web" / "static" / "sg-device-collapse-v1.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "web" / "static" / "sg-client-qr-modal-v1.css").read_text(encoding="utf-8")
    assert "QR · Mieru" in script
    assert "Router / ZB" in script
    assert "QR · Router / ZB" in script
    assert "JSON · iPhone" in script
    assert "QR · iPhone" in script
    assert "Другие форматы" not in script
    assert "...advancedItems" in script
    assert "iPhone JSON" in script
    assert "Сканируйте в приложении" in script
    assert ".sg-smart-qr-meta" in css


def test_client_exporter_error_is_visible_without_breaking_page() -> None:
    access = (ROOT / "app" / "clients" / "access.py").read_text(encoding="utf-8")
    script = (ROOT / "app" / "web" / "static" / "sg-device-collapse-v1.js").read_text(encoding="utf-8")
    assert "def _error_card(" in access
    assert 'status="error"' in access
    assert "Ошибка генерации" in access
    assert "Ошибка генерации" in script
    assert "Остальные профили устройства доступны" in script


def test_panel_update_terminal_has_structured_success_failure_and_runtime_guidance() -> None:
    template = (ROOT / "app" / "web" / "templates" / "operation_job.html").read_text(encoding="utf-8")
    assert "Обновление завершено" in template
    assert "Вернуться в SG-Gateway" in template
    assert "attention.target_url" in template
    assert "result.runtime_attention" in template
    assert "attention.target_label" in template
    assert "attention.message" in template
    assert "Панель:" in template
    assert "Clients:" in template
    assert "HTTPS:" in template
    assert "Этап ${result.stage_number}/6" in template
    assert "result.exit_code" in template
