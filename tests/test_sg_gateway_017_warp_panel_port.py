from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routing import warp, warp_helper


SAMPLE_WARP = {
    "protocol": "wireguard",
    "settings": {
        "secretKey": "private-secret",
        "address": ["172.16.0.2/32", "2606:4700:110::2/128"],
        "peers": [
            {
                "publicKey": "peer-public",
                "endpoint": "engage.cloudflareclient.com:2408",
                "allowedIPs": ["0.0.0.0/0", "::/0"],
            }
        ],
        "reserved": [1, 2, 3],
        "mtu": 1280,
    },
    "tag": "wireguard",
}


def _warp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "warp"
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_DIR", str(root))
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_PATH", str(tmp_path / "warp-state.json"))
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_MANAGED_PATH", str(tmp_path / "routing.json"))
    return root


def test_archive_network_json_is_normalised_like_sg_panel(monkeypatch, tmp_path):
    root = _warp_env(monkeypatch, tmp_path)
    root.mkdir()
    warp.xray_json_path().write_text(json.dumps(SAMPLE_WARP), encoding="utf-8")
    warp.save_state(enabled=True, profile_ready=True, profile={})

    outbound = warp.outbound()
    assert outbound["tag"] == "warp"
    assert outbound["protocol"] == "wireguard"
    assert outbound["settings"]["noKernelTun"] is True
    assert outbound["settings"]["peers"][0]["endpoint"] == "162.159.192.1:2408"
    assert outbound["settings"]["reserved"] == [1, 2, 3]
    assert warp.overview()["status_label"] == "Активен"


def test_one_click_install_is_idempotent_when_already_active(monkeypatch, tmp_path):
    root = _warp_env(monkeypatch, tmp_path)
    root.mkdir()
    warp.xray_json_path().write_text(json.dumps(SAMPLE_WARP), encoding="utf-8")
    warp.save_state(enabled=True, profile_ready=True, profile=warp.scrubbed_profile())

    monkeypatch.setattr(warp_helper, "_install_wgcf", lambda: (_ for _ in ()).throw(AssertionError("must not download")))
    result = warp_helper.install()
    assert result["ok"] is True
    assert "активен" in result["message"]


def test_helper_uses_verified_sg_panel_registration_contract():
    source = Path("app/routing/warp_helper.py").read_text(encoding="utf-8")
    deploy = Path("deploy/install-wgcf-cli.sh").read_text(encoding="utf-8")
    assert "ArchiveNetwork/wgcf-cli" in source
    assert 'WGCF_VERSION = "v0.3.6"' in Path("app/routing/warp.py").read_text(encoding="utf-8")
    assert '[str(WGCF_BIN), "register"]' in source
    assert '[str(WGCF_BIN), "generate", "--xray"]' in source
    assert "SHA2-256=" in source
    assert 'VERSION="v0.3.6"' in deploy
    assert "tar --use-compress-program=unzstd" in deploy


def test_installer_keeps_warp_manual_and_hides_links():
    source = Path("install.sh").read_text(encoding="utf-8")
    assert "stage9_ensure_warp" in source
    assert "/commands/warp.install" in source
    assert "Создание и активация WARP" not in source
    assert "helper установлен; создаётся при необходимости в Outbounds" in source
    assert "существующий профиль сохранён" in source
    assert "Первый клиент sg-admin: создан" in source
    assert "Первый VPN-клиент sg-admin будет создан автоматически" in source
    final = source.rsplit("INSTALL_SUCCESS=1", 1)[1]
    assert "subscription-base64" not in final
    assert "Ссылки первого клиента" not in source

def test_amneziawg_has_fixed_udp_585_contract():
    source = Path("install.sh").read_text(encoding="utf-8")
    assert 'DEFAULT_AWG_PORT="585"' in source
    assert 'read_tty "UDP-порт AmneziaWG"' not in source
    assert 'AWG_PORT="$DEFAULT_AWG_PORT"' in source


def test_clients_small_text_fix_is_page_scoped_and_bottom_button_removed():
    clients = Path("app/web/templates/clients.html").read_text(encoding="utf-8")
    detail = Path("app/web/templates/client_detail.html").read_text(encoding="utf-8")
    css = Path("app/web/static/sg-clients-readable-small-v1.css").read_text(encoding="utf-8")
    assert "sg-clients-readable-small-v1.css" in clients
    assert ".cv15-clarity-page" in css
    assert "body {" not in css
    assert "dv16-add-bottom" not in detail
    assert detail.count("+ Добавить устройство") == 1


def test_outbounds_ui_matches_sg_panel_visible_actions():
    source = Path("app/web/templates/outbounds.html").read_text(encoding="utf-8")
    for text in ("WARP JSON", "Проверить WARP", "Отключить", "Пересоздать", "Удалить"):
        assert text in source
    assert "protocol: {{ warp.protocol_label }}" in source
    assert "Дополнительные действия" not in source
    assert "создаст" not in source.lower() or "активирует" in source.lower()


def test_hostd_exposes_warp_json_action():
    from hostd.sg_hostd import commands, privileged_runtime

    assert "warp.export_json" in commands._COMMANDS
    assert "warp.export_json" in privileged_runtime._ACTIONS


def test_panel_reads_public_warp_state_without_secret_file_access(monkeypatch, tmp_path):
    _warp_env(monkeypatch, tmp_path)
    warp.save_state(enabled=True, profile_ready=True, profile={"endpoint": "162.159.192.1:2408"})
    monkeypatch.setattr(warp.os, "geteuid", lambda: 1001)
    payload = warp.overview()
    assert payload["installed"] is True
    assert payload["enabled"] is True
    assert payload["status_label"] == "Активен"


def test_enabling_legacy_profile_keeps_existing_warp_rules_valid(monkeypatch, tmp_path):
    root = _warp_env(monkeypatch, tmp_path)
    root.mkdir()
    warp.xray_json_path().write_text(json.dumps(SAMPLE_WARP), encoding="utf-8")
    warp.save_state(enabled=False, profile_ready=True, profile=warp.scrubbed_profile())
    Path(tmp_path / "routing.json").write_text(
        json.dumps({"routing": {"domainStrategy": "AsIs", "rules": [
            {"type": "field", "domain": ["domain:example.com"], "outboundTag": "warp"}
        ]}}), encoding="utf-8"
    )
    monkeypatch.setattr(warp_helper, "xray_test_config", lambda config: ("ok", "accepted"))
    monkeypatch.setattr(warp_helper, "apply_full_config", lambda config, restart_if_active=True: ("ok", "applied"))
    monkeypatch.setattr(warp_helper, "service_is_active", lambda: False)
    result = warp_helper.enable()
    assert result["ok"] is True
    assert warp.enabled() is True
