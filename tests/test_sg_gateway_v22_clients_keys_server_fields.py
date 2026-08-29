from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import data_backup_runtime
from sg_hostd.clients_keys_backup_patch import SERVER_FIELDS


def test_clients_keys_contract_excludes_legacy_and_all_known_server_fields() -> None:
    assert "client_deployments" not in data_backup_runtime.CLIENT_TABLES
    assert "client_deployments" in data_backup_runtime.DELETE_ORDER
    assert "client_deployments" not in data_backup_runtime.INSERT_ORDER

    samples = {
        "amneziawg": {
            "private_key": "AWG-CLIENT-PRIVATE",
            "public_key": "AWG-CLIENT-PUBLIC",
            "address": "10.66.0.3/32",
        },
        "amneziawg3": {
            "private_key": "AWG3-CLIENT-PRIVATE",
            "public_key": "AWG3-CLIENT-PUBLIC",
            "address": "10.67.0.3/32",
            "generation": 3,
        },
        "xray": {
            "uuid": "11111111-1111-4111-8111-111111111111",
            "hysteria_auth": "HYSTERIA-CLIENT-SECRET",
            "profiles": ["reality_tcp", "xhttp_reality"],
        },
        "anytls": {
            "password": "ANYTLS-CLIENT-PASSWORD",
            "fingerprint": "firefox",
        },
        "tuic": {
            "uuid": "22222222-2222-4222-8222-222222222222",
            "password": "TUIC-CLIENT-PASSWORD",
        },
    }

    for engine, client_values in samples.items():
        source = dict(client_values)
        for key in SERVER_FIELDS[engine]:
            source[key] = f"OLD-SERVER-{key}"
        cleaned = json.loads(
            data_backup_runtime._sanitize_credential(
                engine, json.dumps(source, ensure_ascii=False)
            )
        )
        assert not (set(cleaned) & SERVER_FIELDS[engine]), engine
        for key, value in client_values.items():
            assert cleaned[key] == value, (engine, key)


def test_clients_keys_rebind_uses_destination_settings_for_every_server_field(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "destination.sqlite"
    db = sqlite3.connect(db_path)
    try:
        db.executescript(
            """
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY,
                engine TEXT NOT NULL,
                config_json TEXT
            );
            """
        )
        settings = {
            "amneziawg": (
                "new.example",
                585,
                {
                    "dns": "9.9.9.9",
                    "server_public_key": "NEW-AWG-SERVER",
                    "allowed_ips": "0.0.0.0/0, ::/0",
                    "persistent_keepalive": 31,
                },
            ),
            "amneziawg3": (
                "new.example",
                586,
                {
                    "dns": "8.8.8.8",
                    "server_public_key": "NEW-AWG3-SERVER",
                    "allowed_ips": "0.0.0.0/0, ::/0",
                    "persistent_keepalive": "29-35",
                },
            ),
            "xray": (
                "new.example",
                443,
                {
                    "security": "reality",
                    "type": "tcp",
                    "flow": "xtls-rprx-vision",
                    "fingerprint": "firefox",
                    "server_name": "new-sni.example",
                    "public_key": "NEW-REALITY-PUBLIC",
                    "short_id": "abcdef0123456789",
                    "vless_encryption": "NEW-VLESS-ENCRYPTION",
                },
            ),
            "mihomo": (
                "new.example",
                2099,
                {
                    "anytls_port": 8443,
                    "tuic_port": 10499,
                    "tuic_congestion_controller": "cubic",
                    "tuic_udp_relay_mode": "native",
                    "tuic_alpn": "h3",
                },
            ),
        }
        for engine, (host, port, config) in settings.items():
            db.execute(
                "INSERT INTO connection_settings VALUES (?, 1, ?, ?, ?, CURRENT_TIMESTAMP)",
                (engine, host, port, json.dumps(config)),
            )

        credentials = {
            "amneziawg": {
                "private_key": "AWG-CLIENT-PRIVATE",
                "public_key": "AWG-CLIENT-PUBLIC",
                "address": "10.66.0.3/32",
            },
            "amneziawg3": {
                "private_key": "AWG3-CLIENT-PRIVATE",
                "public_key": "AWG3-CLIENT-PUBLIC",
                "address": "10.67.0.3/32",
                "generation": 3,
            },
            "xray": {
                "uuid": "11111111-1111-4111-8111-111111111111",
                "hysteria_auth": "HYSTERIA-CLIENT-SECRET",
                "profiles": ["reality_tcp"],
            },
            "anytls": {
                "password": "ANYTLS-CLIENT-PASSWORD",
                "fingerprint": "firefox",
            },
            "tuic": {
                "uuid": "22222222-2222-4222-8222-222222222222",
                "password": "TUIC-CLIENT-PASSWORD",
            },
        }
        for index, (engine, payload) in enumerate(credentials.items(), start=1):
            db.execute(
                "INSERT INTO device_credentials VALUES (?, ?, ?)",
                (index, engine, json.dumps(payload)),
            )
        db.commit()

        monkeypatch.setattr(
            data_backup_runtime.full,
            "_destination_public_address",
            lambda: "new.example",
        )
        monkeypatch.setattr(
            data_backup_runtime.full,
            "_restored_tls_state",
            lambda: {"domain": "vpn.new.example"},
        )
        data_backup_runtime._rebind_client_credentials(db)
        db.commit()

        rebound = {
            engine: json.loads(raw)
            for engine, raw in db.execute(
                "SELECT engine, config_json FROM device_credentials"
            ).fetchall()
        }
    finally:
        db.close()

    assert rebound["amneziawg"]["private_key"] == "AWG-CLIENT-PRIVATE"
    assert rebound["amneziawg"]["server_public_key"] == "NEW-AWG-SERVER"
    assert rebound["amneziawg"]["endpoint"] == "new.example:585"
    assert rebound["amneziawg"]["dns"] == "9.9.9.9"

    assert rebound["amneziawg3"]["private_key"] == "AWG3-CLIENT-PRIVATE"
    assert rebound["amneziawg3"]["server_public_key"] == "NEW-AWG3-SERVER"
    assert rebound["amneziawg3"]["endpoint"] == "new.example:586"
    assert rebound["amneziawg3"]["port"] == 586

    assert rebound["xray"]["uuid"] == "11111111-1111-4111-8111-111111111111"
    assert rebound["xray"]["host"] == "new.example"
    assert rebound["xray"]["public_key"] == "NEW-REALITY-PUBLIC"
    assert rebound["xray"]["server_name"] == "new-sni.example"

    assert rebound["anytls"]["password"] == "ANYTLS-CLIENT-PASSWORD"
    assert rebound["anytls"]["host"] == "vpn.new.example"
    assert rebound["anytls"]["port"] == 8443
    assert rebound["anytls"]["server_name"] == "vpn.new.example"

    assert rebound["tuic"]["password"] == "TUIC-CLIENT-PASSWORD"
    assert rebound["tuic"]["host"] == "vpn.new.example"
    assert rebound["tuic"]["port"] == 10499
    assert rebound["tuic"]["congestion_control"] == "cubic"
    assert rebound["tuic"]["udp_relay_mode"] == "native"
    assert rebound["tuic"]["alpn"] == "h3"
