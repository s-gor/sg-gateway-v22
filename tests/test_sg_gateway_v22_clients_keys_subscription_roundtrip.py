from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from app.clients.repository import Client, Device
from app.clients import router_subscription_store as router_store
from app.clients import sg_subscription_store as sg_store
from app.db import SCHEMA
from sg_hostd import data_backup_runtime


SG_TOKEN = "sg1_" + ("A" * 40)
ROUTER_TOKEN = "sgr1_" + ("B" * 40)
SGCLIENT_TOKEN = "client-sub-" + ("C" * 40)


def _database(path: Path, *, server_host: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO clients(id, name, enabled, expires_at, created_at) "
            "VALUES (1, 'Alice', 1, NULL, '2026-08-20 10:00:00')"
        )
        connection.execute(
            "INSERT INTO devices(id, client_id, name, enabled, expires_at, is_primary, last_seen_at, created_at) "
            "VALUES (1, 1, 'Основной доступ', 1, NULL, 1, NULL, '2026-08-20 10:00:00')"
        )
        connection.execute(
            "INSERT INTO device_credentials(id, device_id, engine, status, engine_object_id, config_json, rotated_at, created_at) "
            "VALUES (1, 1, 'sgclient', 'applied', 'sgclient-1', ?, NULL, '2026-08-20 10:00:00')",
            (
                json.dumps(
                    {
                        "client_name": "Alice",
                        "format": "base64-links-v2",
                        "subscription_token": SGCLIENT_TOKEN,
                        "sources": ["xray", "mihomo", "anytls", "tuic"],
                    },
                    sort_keys=True,
                ),
            ),
        )
        connection.execute(
            "INSERT INTO connection_settings(engine, enabled, host, port, config_json, updated_at) "
            "VALUES ('amneziawg', 1, ?, 585, ?, '2026-08-20 10:00:00')",
            (
                server_host,
                json.dumps(
                    {
                        "dns": "9.9.9.9",
                        "server_public_key": f"SERVER-{server_host}",
                        "allowed_ips": "0.0.0.0/0, ::/0",
                        "persistent_keepalive": 25,
                    },
                    sort_keys=True,
                ),
            ),
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sg_subscription_tokens (
                client_id INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS router_subscription_tokens (
                device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            "INSERT INTO sg_subscription_tokens(client_id, token) VALUES (1, ?)",
            (SG_TOKEN,),
        )
        connection.execute(
            "INSERT INTO router_subscription_tokens(device_id, token) VALUES (1, ?)",
            (ROUTER_TOKEN,),
        )
        connection.commit()
    finally:
        connection.close()


def _client() -> Client:
    return Client(
        id=1,
        name="Alice",
        enabled=True,
        expires_at=None,
        awg_status="missing",
        xray_status="missing",
        sgclient_status="applied",
    )


def _device() -> Device:
    return Device(
        id=1,
        client_id=1,
        name="Основной доступ",
        enabled=True,
        expires_at=None,
        is_primary=True,
        created_at="2026-08-20 10:00:00",
    )


def test_clients_keys_preserves_real_subscription_tokens_and_rebinds_urls(
    tmp_path: Path, monkeypatch
) -> None:
    source_data = tmp_path / "source"
    destination_data = tmp_path / "destination"
    source_out = tmp_path / "source-out"
    data_store = tmp_path / "data-store"
    work = tmp_path / "work"
    full_store = tmp_path / "full-store"
    for path in (source_data, destination_data, source_out, data_store, work, full_store):
        path.mkdir()

    _database(source_data / "sg-gateway.sqlite", server_host="old.example")
    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=source_data,
        destination_dir=source_out,
    )
    _database(destination_data / "sg-gateway.sqlite", server_host="new.example")

    shutil.copy2(
        Path(created["path"]),
        data_store / data_backup_runtime.RESTORE_UPLOAD_NAME,
    )
    monkeypatch.setattr(data_backup_runtime, "_data_backup_dir", lambda: data_store)
    monkeypatch.setattr(data_backup_runtime, "_work_dir", lambda: work)
    monkeypatch.setattr(
        data_backup_runtime,
        "assert_runtime_contract",
        lambda **kwargs: {"ok": True},
    )
    monkeypatch.setattr(data_backup_runtime.full, "_data_dir", lambda: destination_data)
    monkeypatch.setattr(
        data_backup_runtime.full,
        "_destination_public_address",
        lambda: "new.example",
    )
    monkeypatch.setattr(data_backup_runtime.full, "_restored_tls_state", lambda: {})
    monkeypatch.setattr(data_backup_runtime.full, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(data_backup_runtime.full, "_backup_dir", lambda: full_store)

    result = data_backup_runtime.promote_uploaded_data_backup()
    promoted = Path(result["full_restore_upload"])
    extracted = tmp_path / "promoted"
    extracted.mkdir()
    data_backup_runtime.full._extract_archive(promoted, extracted)
    restored_data = extracted / "payload/var/lib/sg-gateway"
    database = restored_data / "sg-gateway.sqlite"

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT token FROM sg_subscription_tokens WHERE client_id = 1"
        ).fetchone()[0] == SG_TOKEN
        assert connection.execute(
            "SELECT token FROM router_subscription_tokens WHERE device_id = 1"
        ).fetchone()[0] == ROUTER_TOKEN
        assert connection.execute(
            "SELECT host FROM connection_settings WHERE engine = 'amneziawg'"
        ).fetchone()[0] == "new.example"
        sgclient = json.loads(
            connection.execute(
                "SELECT config_json FROM device_credentials WHERE device_id = 1 AND engine = 'sgclient'"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    assert sgclient["subscription_token"] == SGCLIENT_TOKEN
    assert b"old.example" not in database.read_bytes()

    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(restored_data))
    monkeypatch.setattr(sg_store, "subscription_base_url", lambda: "https://new.example")
    monkeypatch.setattr(router_store, "subscription_base_url", lambda: "https://new.example")

    assert sg_store.ensure_client_subscription_token(1) == SG_TOKEN
    assert router_store.ensure_router_subscription_token(1, 1) == ROUTER_TOKEN
    assert sg_store.build_sg_subscription_url(_client()) == (
        f"https://new.example/sg/sub/v1/{SG_TOKEN}"
    )
    assert router_store.build_router_subscription_url(_client(), _device()) == (
        f"https://new.example/sg/router/v1/{ROUTER_TOKEN}.json"
    )
    assert router_store.build_openwrt_subscription_url(_client(), _device()) == (
        f"https://new.example/sg/router/openwrt/v1/{ROUTER_TOKEN}.sub"
    )
    access = router_store.get_router_subscription_access(ROUTER_TOKEN)
    assert access is not None
    assert access[0].id == 1
    assert access[1].id == 1
