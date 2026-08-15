from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.clients import exports
from app.clients.repository import Client
from app.xray.sg_panel_vless import REALITY_TCP_FLOW
from sg_hostd import client_runtime

UUID = "11111111-1111-1111-1111-111111111111"
ENCRYPTION = (
    "mlkem768x25519plus.native.0rtt.100-111-1111.75-0-111.50-0-3333."
    "Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0ND"
    "Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0ND"
    "Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M"
)
DECRYPTION = (
    "mlkem768x25519plus.native.600s.100-111-1111.75-0-111.50-0-3333."
    "U1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NTU1NT"
    "U1NTU1NTU1NTU1NTU1NTU1NTUw"
)


def _profiles():
    return {
        "profiles": [
            SimpleNamespace(
                id="reality_tcp", title="VLESS Reality TCP", enabled=True,
                ready=True, tls_required=False, port=443, path="", mode="",
            ),
            SimpleNamespace(
                id="xhttp_reality", title="VLESS XHTTP Reality", enabled=True,
                ready=True, tls_required=False, port=8444,
                path="/sg-xhttp-reality", mode="stream-one",
            ),
            SimpleNamespace(
                id="xhttp_tls", title="VLESS XHTTP TLS", enabled=False,
                ready=False, tls_required=True, port=8445,
                path="/sg-xhttp-tls", mode="auto",
            ),
            SimpleNamespace(
                id="hysteria2", title="Hysteria 2", enabled=False,
                ready=False, tls_required=True, port=8446, path="", mode="",
            ),
        ],
        "tls_ready": False,
        "tls_domain": "",
        "host": "203.0.113.10",
    }


def test_runtime_matches_sg_panel_reality_contract(monkeypatch):
    monkeypatch.setattr(client_runtime, "_read_env", lambda path: {
        "SG_GATEWAY_XRAY_PRIVATE_KEY": "private-key",
        "SG_GATEWAY_XRAY_SHORT_ID": "0123456789abcdef",
        "SG_GATEWAY_VLESS_ENCRYPTION": ENCRYPTION,
        "SG_GATEWAY_VLESS_DECRYPTION": DECRYPTION,
        "SG_GATEWAY_REALITY_SNI": "www.bing.com",
        "SG_GATEWAY_REALITY_TARGET": "www.bing.com:443",
    })
    monkeypatch.setattr(
        client_runtime,
        "get_connection_settings",
        lambda engine: SimpleNamespace(
            config={"server_name": "www.bing.com", "target": "www.bing.com:443"},
            host="203.0.113.10",
            port=443,
        ),
    )
    monkeypatch.setattr(client_runtime, "xray_profiles_overview", _profiles)
    row = {
        "client_id": 1,
        "client_name": "SG-Panel parity",
        "engine_object_id": UUID,
        "config_json": json.dumps({
            "uuid": UUID,
            "profiles": ["reality_tcp", "xhttp_reality"],
        }),
    }

    config = json.loads(client_runtime._render_xray_config([row]))
    tcp = next(item for item in config["inbounds"] if item["tag"] == "sg-vless-reality-tcp")
    xhttp = next(item for item in config["inbounds"] if item["tag"] == "sg-vless-xhttp-reality")

    assert tcp["streamSettings"]["network"] == "tcp"
    assert tcp["streamSettings"]["realitySettings"] == {
        "show": False,
        "dest": "www.bing.com:443",
        "xver": 0,
        "serverNames": ["www.bing.com"],
        "privateKey": "private-key",
        "shortIds": ["0123456789abcdef"],
    }
    assert "target" not in tcp["streamSettings"]["realitySettings"]
    assert tcp["settings"]["decryption"] == "none"
    assert tcp["settings"]["clients"][0]["flow"] == REALITY_TCP_FLOW

    assert xhttp["settings"]["decryption"] == DECRYPTION
    assert xhttp["settings"]["clients"][0]["flow"] == REALITY_TCP_FLOW
    assert xhttp["streamSettings"]["network"] == "xhttp"
    assert xhttp["streamSettings"]["xhttpSettings"] == {
        "path": "/sg-xhttp-reality",
        "mode": "auto",
    }
    assert xhttp["streamSettings"]["realitySettings"] == tcp["streamSettings"]["realitySettings"]


def test_export_links_match_sg_panel_parameters(monkeypatch):
    client = Client(
        id=1, name="Сергей", enabled=True, expires_at=None,
        awg_status="missing", xray_status="applied",
    )
    deployment = SimpleNamespace(
        engine="xray",
        status="applied",
        config_json=json.dumps({
            "host": "203.0.113.10",
            "uuid": UUID,
            "fingerprint": "Firefox",
            "server_name": "www.bing.com",
            "public_key": "public-key",
            "short_id": "0123456789abcdef",
            "vless_encryption": ENCRYPTION,
            "profiles": ["reality_tcp", "xhttp_reality"],
        }),
    )
    monkeypatch.setattr(exports, "list_client_deployments", lambda _id: [deployment])
    monkeypatch.setattr(exports, "xray_profiles_overview", _profiles)

    tcp_link = exports.build_xray_profile_link(client, "reality_tcp").body
    tcp_query = parse_qs(urlparse(tcp_link).query)
    assert tcp_query == {
        "encryption": ["none"],
        "type": ["tcp"],
        "security": ["reality"],
        "pbk": ["public-key"],
        "fp": ["firefox"],
        "sni": ["www.bing.com"],
        "sid": ["0123456789abcdef"],
        "flow": [REALITY_TCP_FLOW],
        "spx": ["/"],
    }

    xhttp_link = exports.build_xray_profile_link(client, "xhttp_reality").body
    xhttp_query = parse_qs(urlparse(xhttp_link).query)
    assert xhttp_query["encryption"] == [ENCRYPTION]
    assert xhttp_query["flow"] == [REALITY_TCP_FLOW]
    assert xhttp_query["type"] == ["xhttp"]
    assert xhttp_query["security"] == ["reality"]
    assert xhttp_query["pbk"] == ["public-key"]
    assert xhttp_query["fp"] == ["firefox"]
    assert xhttp_query["sni"] == ["www.bing.com"]
    assert xhttp_query["sid"] == ["0123456789abcdef"]
    assert xhttp_query["path"] == ["/sg-xhttp-reality"]
    assert xhttp_query["mode"] == ["stream-one"]
    assert xhttp_query["spx"] == ["/"]


def test_port_is_isolated_from_clients_storage():
    module = (ROOT / "app/xray/sg_panel_vless.py").read_text(encoding="utf-8")
    assert "app.clients" not in module
    assert "connect(" not in module
    assert '"dest"' in module
    assert '"network": "tcp"' in module
    assert "spx=%2F" in module


def test_exports_ignore_stale_server_values_in_access(monkeypatch):
    client = Client(
        id=1, name="Сергей", enabled=True, expires_at=None,
        awg_status="missing", xray_status="applied",
    )
    deployment = SimpleNamespace(
        engine="xray", status="applied",
        config_json=json.dumps({
            "uuid": UUID,
            "host": "192.0.2.99",
            "fingerprint": "chrome",
            "server_name": "stale.example",
            "public_key": "stale-key",
            "short_id": "aaaaaaaaaaaaaaaa",
            "vless_encryption": "stale-encryption",
            "profiles": ["reality_tcp", "xhttp_reality"],
        }),
    )
    current = SimpleNamespace(
        host="203.0.113.10", port=443,
        config={
            "fingerprint": "firefox",
            "server_name": "www.bing.com",
            "public_key": "current-key",
            "short_id": "0123456789abcdef",
            "vless_encryption": ENCRYPTION,
        },
    )
    monkeypatch.setattr(exports, "list_client_deployments", lambda _id: [deployment])
    monkeypatch.setattr(exports, "get_connection_settings", lambda engine: current)
    monkeypatch.setattr(exports, "xray_profiles_overview", _profiles)

    link = exports.build_xray_profile_link(client, "xhttp_reality").body
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "203.0.113.10"
    assert query["pbk"] == ["current-key"]
    assert query["sid"] == ["0123456789abcdef"]
    assert query["sni"] == ["www.bing.com"]
    assert query["fp"] == ["firefox"]
    assert query["encryption"] == [ENCRYPTION]
    assert "stale" not in link


def test_install_migration_synchronizes_server_values_without_rotating_uuid(tmp_path, monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path))
    from app.clients.repository import create_client, list_client_deployments
    from app.db import connect, init_db
    from app.install_seed import _synchronize_xray_credentials

    init_db()
    client_id = create_client("Existing", "xray")
    before = next(item for item in list_client_deployments(client_id) if item.engine == "xray")
    original_uuid = before.engine_object_id
    with connect() as connection:
        stale = json.loads(before.config_json)
        stale.update({
            "host": "192.0.2.99",
            "port": 9443,
            "fingerprint": "chrome",
            "server_name": "stale.example",
            "public_key": "stale-key",
            "short_id": "aaaaaaaaaaaaaaaa",
            "vless_encryption": "stale-encryption",
        })
        credential_id = connection.execute(
            "SELECT id FROM device_credentials WHERE engine='xray' AND engine_object_id=?",
            (original_uuid,),
        ).fetchone()["id"]
        connection.execute(
            "UPDATE device_credentials SET config_json=? WHERE id=?",
            (json.dumps(stale), int(credential_id)),
        )

    changed = _synchronize_xray_credentials(
        host="203.0.113.10",
        port=443,
        fingerprint="firefox",
        server_name="www.bing.com",
        public_key="current-key",
        short_id="0123456789abcdef",
        vless_encryption=ENCRYPTION,
    )
    assert changed == 1
    after = next(item for item in list_client_deployments(client_id) if item.engine == "xray")
    assert after.engine_object_id == original_uuid
    config = json.loads(after.config_json)
    assert config["uuid"] == original_uuid
    assert config["profiles"] == ["reality_tcp", "xhttp_reality"]
    assert config["host"] == "203.0.113.10"
    assert config["port"] == 443
    assert config["fingerprint"] == "firefox"
    assert config["server_name"] == "www.bing.com"
    assert config["public_key"] == "current-key"
    assert config["short_id"] == "0123456789abcdef"
    assert config["vless_encryption"] == ENCRYPTION
