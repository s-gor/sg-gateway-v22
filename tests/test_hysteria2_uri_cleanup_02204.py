from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients import exports  # noqa: E402
from app.clients.repository import Client, ClientDeployment  # noqa: E402


def _link(monkeypatch, mode: str) -> tuple[str, dict]:
    client = Client(1, "URI cleanup", True, None, "missing", "applied")
    deployment = ClientDeployment(
        engine="xray",
        status="applied",
        engine_object_id="uuid-value",
        config_json=json.dumps(
            {
                "uuid": "uuid-value",
                "hysteria_auth": "auth-value",
                "profiles": ["hysteria2"],
            }
        ),
    )
    server_config = {
        "public_key": "public-key",
        "short_id": "0123456789abcdef",
        "server_name": "vpn.example.com",
        "hysteria2_obfs_mode": mode,
        "hysteria2_obfs_password": "G" * 32,
        "hysteria2_uri_scheme": "hysteria2",
    }
    monkeypatch.setattr(exports, "list_client_deployments", lambda client_id: [deployment])
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda engine: SimpleNamespace(host="203.0.113.9", port=443, config=server_config),
    )
    monkeypatch.setattr(
        exports,
        "xray_profiles_overview",
        lambda: {
            "profiles": [SimpleNamespace(id="hysteria2", title="Hysteria 2", port=8446)],
            "tls_domain": "vpn.example.com",
            "host": "203.0.113.9",
        },
    )
    return exports.build_xray_profile_link(client, "hysteria2").body, server_config


def test_hysteria2_gecko_uri_does_not_export_alpn(monkeypatch):
    link, server_config = _link(monkeypatch, "gecko")
    query = parse_qs(urlsplit(link).query)
    assert query["sni"] == ["vpn.example.com"]
    assert query["insecure"] == ["0"]
    assert query["obfs"] == ["gecko"]
    assert query["obfs-password"] == [server_config["hysteria2_obfs_password"]]
    assert "alpn" not in query


def test_hysteria2_salamander_uri_does_not_export_alpn(monkeypatch):
    link, server_config = _link(monkeypatch, "salamander")
    query = parse_qs(urlsplit(link).query)
    assert query["obfs"] == ["salamander"]
    assert query["obfs-password"] == [server_config["hysteria2_obfs_password"]]
    assert "alpn" not in query
