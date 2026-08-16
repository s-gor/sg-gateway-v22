from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.clients import exports  # noqa: E402
from app.clients.repository import Client, ClientDeployment  # noqa: E402
from app.connections.settings import get_connection_settings, update_connection_settings  # noqa: E402
from app.db import init_db  # noqa: E402
from app.xray.salamander import (  # noqa: E402
    GECKO_MINIMUM_VERSION,
    GECKO_PACKET_SIZE,
    MANAGED_VARIANT_MARKER,
    SALAMANDER_MINIMUM_VERSION,
    generate_password,
    merge_finalmask,
    version_supported,
)
from app.xray.salamander_diagnostics import inspect  # noqa: E402
from app.xray.settings_transactions import begin, commit, pending, rollback  # noqa: E402
from sg_hostd import client_runtime  # noqa: E402


def test_password_is_24_random_bytes_base64url_shape():
    first = generate_password()
    second = generate_password()
    assert len(first) == 32
    assert len(second) == 32
    assert first != second
    assert "=" not in first
    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", first)


def test_minimum_version_contract():
    assert SALAMANDER_MINIMUM_VERSION == "26.3.27"
    assert GECKO_MINIMUM_VERSION == "26.6.27"
    assert GECKO_PACKET_SIZE == "512-1200"
    assert version_supported("26.3.27", SALAMANDER_MINIMUM_VERSION)
    assert not version_supported("26.3.26", SALAMANDER_MINIMUM_VERSION)
    assert version_supported("26.6.27", GECKO_MINIMUM_VERSION)
    assert version_supported("26.7.28", GECKO_MINIMUM_VERSION)
    assert not version_supported("26.6.26", GECKO_MINIMUM_VERSION)


def test_finalmask_renders_plain_salamander_gecko_and_off_without_leaking_marker():
    base = {
        "quicParams": {"maxIdleTimeout": 30},
        "tcp": [{"type": "padding", "settings": {"size": 9}}],
        "udp": [{"type": "padding", "settings": {"size": 7}}],
        MANAGED_VARIANT_MARKER: True,
    }
    salamander = merge_finalmask(base, "salamander", "A" * 32)
    gecko = merge_finalmask(base, "gecko", "A" * 32)
    disabled = merge_finalmask(base, "none", "")

    assert MANAGED_VARIANT_MARKER not in salamander
    assert MANAGED_VARIANT_MARKER not in gecko
    assert MANAGED_VARIANT_MARKER not in disabled
    assert salamander["udp"] == [
        {"type": "salamander", "settings": {"password": "A" * 32}}
    ]
    assert gecko["udp"] == [
        {
            "type": "salamander",
            "settings": {"password": "A" * 32, "packetSize": "512-1200"},
        }
    ]
    assert disabled == {
        "quicParams": {"maxIdleTimeout": 30},
        "tcp": [{"type": "padding", "settings": {"size": 9}}],
        "udp": [{"type": "padding", "settings": {"size": 7}}],
    }
    assert base["udp"] == [{"type": "padding", "settings": {"size": 7}}]


def test_database_migration_is_additive_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    settings = get_connection_settings("xray")
    assert settings.config["hysteria2_obfs_mode"] == "none"
    assert settings.config["hysteria2_obfs_password"] is None
    before = json.dumps(settings.config, ensure_ascii=False, sort_keys=True)
    init_db()
    after = json.dumps(get_connection_settings("xray").config, ensure_ascii=False, sort_keys=True)
    assert before == after


def test_settings_transaction_rolls_back_and_commits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    original = get_connection_settings("xray")
    candidate = dict(original.config)
    candidate["hysteria2_obfs_mode"] = "salamander"
    candidate["hysteria2_obfs_password"] = "B" * 32

    transaction = begin("xray", "203.0.113.40", 443, candidate)
    assert pending("xray").id == transaction.id
    assert get_connection_settings("xray").config["hysteria2_obfs_mode"] == "salamander"
    assert rollback(transaction.id)
    assert get_connection_settings("xray").config["hysteria2_obfs_mode"] == "none"

    transaction = begin("xray", "203.0.113.40", 443, candidate)
    assert commit(transaction.id)
    assert pending("xray") is None
    assert get_connection_settings("xray").config["hysteria2_obfs_mode"] == "salamander"


def _mock_gecko_export(monkeypatch):
    client = Client(1, "Test client", True, None, "missing", "applied")
    deployment = ClientDeployment(
        engine="xray",
        status="applied",
        engine_object_id="uuid-value",
        config_json=json.dumps(
            {
                "uuid": "uuid-value",
                "hysteria_auth": "auth:with space/@",
                "profiles": ["hysteria2"],
            }
        ),
    )
    server_config = {
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
        "server_name": "vpn.example.com",
        "hysteria2_obfs_mode": "gecko",
        "hysteria2_obfs_password": "pass /?&+=" + "X" * 20,
        "hysteria2_uri_scheme": "hysteria2",
    }
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda engine: SimpleNamespace(host="203.0.113.9", port=443, config=server_config),
    )
    profile = SimpleNamespace(id="hysteria2", title="Hysteria 2", port=8446)
    monkeypatch.setattr(
        exports,
        "xray_profiles_overview",
        lambda: {"profiles": [profile], "tls_domain": "vpn.example.com", "host": "203.0.113.9"},
    )
    return client, server_config


def test_hysteria2_uri_has_exact_encoded_gecko_parameters_and_no_alpn(monkeypatch):
    client, server_config = _mock_gecko_export(monkeypatch)
    link = exports.build_xray_profile_link(client, "hysteria2").body
    parsed = urlsplit(link)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "hysteria2"
    assert parsed.username == "auth%3Awith%20space%2F%40"
    assert parsed.port == 8446
    assert query["obfs"] == ["gecko"]
    assert query["obfs-password"] == [server_config["hysteria2_obfs_password"]]
    assert query["sni"] == ["vpn.example.com"]
    assert query["insecure"] == ["0"]
    assert "alpn" not in query


def test_runtime_candidate_merges_gecko_and_quic_params(monkeypatch):
    monkeypatch.setattr(
        client_runtime,
        "_read_env",
        lambda path: {
            "SG_GATEWAY_XRAY_PRIVATE_KEY": "private-key",
            "SG_GATEWAY_XRAY_SHORT_ID": "0123456789abcdef",
            "SG_GATEWAY_REALITY_SNI": "www.bing.com",
            "SG_GATEWAY_REALITY_TARGET": "www.bing.com:443",
        },
    )
    config = {
        "server_name": "www.bing.com",
        "target": "www.bing.com:443",
        "hysteria2_finalmask": {
            "quicParams": {"maxIdleTimeout": 45},
            MANAGED_VARIANT_MARKER: True,
        },
        "hysteria2_obfs_mode": "gecko",
        "hysteria2_obfs_password": "C" * 32,
    }
    monkeypatch.setattr(
        client_runtime,
        "get_connection_settings",
        lambda engine: SimpleNamespace(config=config, host="203.0.113.10", port=443),
    )
    profile = SimpleNamespace(
        id="hysteria2", title="Hysteria 2", enabled=True, ready=True,
        tls_required=True, port=8446, path="", mode="", flow="",
    )
    monkeypatch.setattr(
        client_runtime,
        "xray_profiles_overview",
        lambda: {
            "profiles": [profile],
            "tls_ready": True,
            "tls_domain": "vpn.example.com",
        },
    )
    monkeypatch.setattr(
        client_runtime,
        "_sync_xray_tls_material",
        lambda domain: (
            "/usr/local/etc/xray/tls/fullchain.pem",
            "/usr/local/etc/xray/tls/privkey.pem",
        ),
    )
    payload = json.loads(client_runtime._render_xray_config([]))
    inbound = payload["inbounds"][0]
    assert inbound["tag"] == "sg-hysteria2"
    finalmask = inbound["streamSettings"]["finalmask"]
    assert finalmask["quicParams"] == {"maxIdleTimeout": 45}
    assert finalmask["udp"] == [
        {
            "type": "salamander",
            "settings": {"password": "C" * 32, "packetSize": "512-1200"},
        }
    ]
    assert MANAGED_VARIANT_MARKER not in finalmask


def test_diagnostics_reports_gecko_state_without_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    secret = "D" * 32
    config.update(
        {
            "hysteria2_obfs_mode": "gecko",
            "hysteria2_obfs_password": secret,
            "hysteria2_finalmask": {MANAGED_VARIANT_MARKER: True},
        }
    )
    assert update_connection_settings("xray", "203.0.113.10", 443, config)
    live = tmp_path / "xray.json"
    live.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "sg-hysteria2",
                        "streamSettings": {
                            "finalmask": {
                                "udp": [
                                    {
                                        "type": "salamander",
                                        "settings": {
                                            "password": secret,
                                            "packetSize": "512-1200",
                                        },
                                    }
                                ]
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = inspect(live)
    assert result["consistent"] is True
    assert result["finalmask_udp_active"] is True
    assert result["live_mode"] == "gecko"
    assert result["gecko_packet_size_ready"] is True
    assert result["client_uri_parameters_present"] is True
    assert secret not in json.dumps(result, ensure_ascii=False)
    assert result["safe_lines"] == [
        "Hysteria2 obfuscation: Gecko",
        "Hysteria2 obfs password: configured",
        "Gecko packetSize: 512-1200",
        "FinalMask UDP layer: active",
        "Client URI parameters: present",
    ]


def test_ui_has_off_salamander_gecko_and_internal_confirmation():
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    section = template[template.index('data-salamander-panel'):]
    assert 'name="hysteria2_obfs_mode" value="none"' in section
    assert 'name="hysteria2_obfs_mode" value="salamander"' in section
    assert 'name="hysteria2_obfs_mode" value="gecko"' in section
    assert "Gecko · рекомендуется" in section
    assert "Сгенерировать новый" in section
    assert "dataset.sgConfirm" in section
    assert "window.alert" not in section
    assert "window.confirm" not in section
    assert "window.prompt" not in section


def test_runtime_legacy_discovery_still_removes_plain_salamander_layer(tmp_path, monkeypatch):
    secret = "OLD" * 11
    live = tmp_path / "config.json"
    live.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "sg-hysteria2",
                        "streamSettings": {
                            "finalmask": {
                                "quicParams": {"maxIdleTimeout": 22},
                                "udp": [
                                    {"type": "padding", "settings": {"size": 5}},
                                    {"type": "salamander", "settings": {"password": secret}},
                                ],
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_runtime, "XRAY_CONFIG", live)
    base = client_runtime._live_hysteria_finalmask_base(
        {
            "hysteria2_obfs_mode": "salamander",
            "hysteria2_obfs_password": secret,
        }
    )
    assert base == {
        "quicParams": {"maxIdleTimeout": 22},
        "udp": [{"type": "padding", "settings": {"size": 5}}],
    }


def test_rotation_uses_password_shown_to_admin(monkeypatch):
    from app.xray import profiles

    old = "F" * 32
    shown = "G" * 32
    settings = SimpleNamespace(
        host="203.0.113.8",
        port=443,
        config={
            "reality_tcp_enabled": True,
            "reality_tcp_port": 443,
            "xhttp_reality_enabled": True,
            "xhttp_reality_port": 8444,
            "xhttp_reality_path": "/sg-xhttp-reality",
            "xhttp_reality_mode": "stream-one",
            "xhttp_tls_enabled": False,
            "xhttp_tls_port": 8445,
            "xhttp_tls_path": "/sg-xhttp-tls",
            "xhttp_tls_mode": "auto",
            "hysteria2_enabled": True,
            "hysteria2_port": 8446,
            "hysteria2_obfs_mode": "salamander",
            "hysteria2_obfs_password": old,
            "hysteria2_finalmask": {MANAGED_VARIANT_MARKER: True},
            "hysteria2_uri_scheme": "hysteria2",
            "vless_encryption": "ready",
        },
    )
    monkeypatch.setattr(profiles, "_config", lambda: (settings, dict(settings.config), {"https_ready": True}))
    monkeypatch.setattr(profiles, "_installed_xray_version", lambda: "26.6.27")
    monkeypatch.setattr(profiles, "_vless_encryption_ready", lambda value: True)
    monkeypatch.setattr(profiles, "generate_password", lambda: (_ for _ in ()).throw(AssertionError("unexpected regeneration")))
    prepared = profiles._prepare(
        {
            "host": settings.host,
            "reality_tcp_enabled": "on",
            "reality_tcp_port": "443",
            "xhttp_reality_enabled": "on",
            "xhttp_reality_port": "8444",
            "xhttp_reality_path": "/sg-xhttp-reality",
            "xhttp_reality_mode": "stream-one",
            "xhttp_tls_port": "8445",
            "xhttp_tls_path": "/sg-xhttp-tls",
            "xhttp_tls_mode": "auto",
            "hysteria2_enabled": "on",
            "hysteria2_port": "8446",
            "hysteria2_obfs_mode": "salamander",
            "hysteria2_obfs_password": shown,
            "hysteria2_obfs_rotate": "1",
        }
    )
    assert prepared.config["hysteria2_obfs_password"] == shown
    assert prepared.config["hysteria2_finalmask"][MANAGED_VARIANT_MARKER] is True
    assert prepared.salamander_rotated is True


def test_pending_candidate_does_not_leak_into_client_uri(monkeypatch):
    client = Client(2, "Pending test", True, None, "missing", "applied")
    deployment = ClientDeployment(
        engine="xray",
        status="applied",
        engine_object_id="uuid-value",
        config_json=json.dumps({"uuid": "uuid-value", "hysteria_auth": "old-auth", "profiles": ["hysteria2"]}),
    )
    applied_config = {
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
        "hysteria2_enabled": True,
        "hysteria2_port": 8446,
        "hysteria2_obfs_mode": "none",
        "hysteria2_obfs_password": None,
    }
    candidate_config = dict(applied_config)
    candidate_config.update({"hysteria2_obfs_mode": "gecko", "hysteria2_obfs_password": "H" * 32})
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda engine: SimpleNamespace(host="203.0.113.9", port=443, config=candidate_config),
    )
    monkeypatch.setattr(
        exports,
        "pending_settings_transaction",
        lambda engine: SimpleNamespace(previous_config=applied_config, previous_host="203.0.113.9", previous_port=443),
    )
    monkeypatch.setattr(
        exports,
        "xray_profiles_overview",
        lambda: {"profiles": [SimpleNamespace(id="hysteria2", title="Hysteria 2", port=8446, path="", mode="")], "tls_domain": "vpn.example.com", "host": "203.0.113.9"},
    )
    link = exports.build_xray_profile_link(client, "hysteria2").body
    assert "obfs=gecko" not in link
    assert "obfs-password=" not in link
