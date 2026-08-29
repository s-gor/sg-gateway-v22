from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.connections.awg31 import (
    Awg31ValidationError,
    DEFAULT_PARAMETERS,
    REAL31_DEFAULT_PARAMETERS,
    normalize_legacy_parameters,
    validate_parameters,
)
from app.db import DEFAULT_CONNECTIONS
from app.maintenance.awg31_stage3a import Stage3AInstaller

ROOT = Path(__file__).resolve().parents[1]
SAFE_HEADERS = {name: str(REAL31_DEFAULT_PARAMETERS[name]) for name in ("H1", "H2", "H3", "H4")}


class FakeOS:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, *command: str) -> None:
        self.commands.append(tuple(command))


def _seed_legacy_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_parameters = {
        **{f"i{index}": "" for index in range(1, 6)},
        "jc": 0,
        "jmin": 0,
        "jmax": 0,
        **{f"s{index}": 0 for index in range(1, 5)},
        **{f"h{index}": "0" for index in range(1, 5)},
        "endpoint": "awg31.internal:587",
        "server_public_key": "legacy-server-public",
    }
    credential = {
        "profile": "awg31",
        "engine": "amneziawg31",
        "client_name": "Legacy",
        "private_key": "preserved-private",
        "public_key": "preserved-public",
        "address": "10.131.0.2/32",
        "dns": "1.1.1.1",
        "endpoint": "awg31.internal:587",
        "transport": "udp",
        "interface": "awg31",
        "network": "10.131.0.0/24",
        "allowed_ips": "0.0.0.0/0, ::/0",
        "persistent_keepalive": 25,
        "generation": 31,
        **{f"i{index}": "" for index in range(1, 6)},
        "jc": 0,
        "jmin": 0,
        "jmax": 0,
        **{f"s{index}": 0 for index in range(1, 5)},
        **{f"h{index}": "0" for index in range(1, 5)},
    }
    with sqlite3.connect(path) as database:
        database.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                last_seen_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                engine TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                engine_object_id TEXT,
                config_json TEXT,
                rotated_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id, engine)
            );
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                host TEXT NOT NULL DEFAULT '',
                port INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO clients(id, name) VALUES (1, 'Legacy');
            INSERT INTO devices(id, client_id, name, is_primary)
            VALUES (1, 1, 'primary', 1);
            """
        )
        database.execute(
            "INSERT INTO connection_settings(engine, enabled, host, port, config_json) "
            "VALUES ('amneziawg31', 1, 'awg31.internal', 587, ?)",
            (json.dumps(legacy_parameters, sort_keys=True),),
        )
        database.execute(
            "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json) "
            "VALUES (1, 'amneziawg31', 'applied', 'preserved-public', ?)",
            (json.dumps(credential, sort_keys=True),),
        )


def _read_payloads(path: Path) -> tuple[dict, dict, str]:
    with sqlite3.connect(path) as database:
        settings = json.loads(
            database.execute(
                "SELECT config_json FROM connection_settings WHERE engine = 'amneziawg31'"
            ).fetchone()[0]
        )
        row = database.execute(
            "SELECT config_json, status FROM device_credentials "
            "WHERE device_id = 1 AND engine = 'amneziawg31'"
        ).fetchone()
    return settings, json.loads(row[0]), str(row[1])


def test_awg31_default_header_values_are_pairwise_non_overlapping() -> None:
    assert {name: DEFAULT_PARAMETERS[name] for name in SAFE_HEADERS} == SAFE_HEADERS
    assert validate_parameters(DEFAULT_PARAMETERS) == DEFAULT_PARAMETERS


def test_awg31_database_seed_uses_safe_header_values() -> None:
    seed = json.loads(DEFAULT_CONNECTIONS["amneziawg31"]["config_json"])
    assert {name: seed[name.lower()] for name in SAFE_HEADERS} == SAFE_HEADERS


@pytest.mark.parametrize(
    "headers",
    [
        {"H1": "10", "H2": "10", "H3": "30", "H4": "40"},
        {"H1": "10-20", "H2": "20-30", "H3": "40", "H4": "50"},
        {"H1": "10-30", "H2": "15", "H3": "40", "H4": "50"},
    ],
)
def test_awg31_validation_rejects_overlapping_header_ranges(headers: dict[str, str]) -> None:
    payload = dict(DEFAULT_PARAMETERS)
    payload.update(headers)
    with pytest.raises(Awg31ValidationError, match="must not overlap"):
        validate_parameters(payload)


def test_only_legacy_all_zero_headers_are_normalized() -> None:
    legacy = dict(
        DEFAULT_PARAMETERS,
        Jc=0,
        Jmin=0,
        Jmax=0,
        S1=0,
        S2=0,
        S3=0,
        S4=0,
        H1="0",
        H2="0",
        H3="0",
        H4="0",
    )
    normalized = normalize_legacy_parameters(legacy)
    assert {name: normalized[name] for name in SAFE_HEADERS} == SAFE_HEADERS
    assert validate_parameters(legacy) == validate_parameters(DEFAULT_PARAMETERS)

    arbitrary_overlap = dict(DEFAULT_PARAMETERS, H1="9", H2="9", H3="30", H4="40")
    assert normalize_legacy_parameters(arbitrary_overlap) == arbitrary_overlap
    with pytest.raises(Awg31ValidationError, match="must not overlap"):
        validate_parameters(arbitrary_overlap)


def test_stage3a_repairs_legacy_headers_and_preserves_existing_keys(tmp_path: Path) -> None:
    root = tmp_path / "root"
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_legacy_database(database)
    fake_os = FakeOS()
    installer = Stage3AInstaller(source_root=ROOT, root=root, os_boundary=fake_os)

    first = installer.migrate(database=database)
    settings, credential, status = _read_payloads(database)

    assert first.created_credentials == 0
    assert first.peer_configs == 1
    assert credential["private_key"] == "preserved-private"
    assert credential["public_key"] == "preserved-public"
    assert credential["address"] == "10.131.0.2/32"
    assert {name: settings[name.lower()] for name in SAFE_HEADERS} == SAFE_HEADERS
    assert {name: credential[name.lower()] for name in SAFE_HEADERS} == SAFE_HEADERS
    assert status == "pending"

    server = (root / "etc/amnezia/amneziawg/awg31/awg31.conf").read_text(
        encoding="utf-8"
    )
    peer = (root / "etc/amnezia/amneziawg/awg31/peers/device-1.conf").read_text(
        encoding="utf-8"
    )
    for name, value in SAFE_HEADERS.items():
        assert f"{name} = {value}" in server
        assert f"{name} = {value}" in peer

    before_second = _read_payloads(database)
    second = installer.migrate(database=database)
    assert second.created_credentials == 0
    assert _read_payloads(database) == before_second
