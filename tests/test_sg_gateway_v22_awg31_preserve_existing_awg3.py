from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.maintenance.awg31_stage3a import Stage3AInstaller

ROOT = Path(__file__).resolve().parents[1]


class RecordingOS:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, *command: str) -> None:
        self.commands.append(tuple(command))


def _seed_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(
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
            INSERT INTO clients(id, name) VALUES (1, 'alpha');
            INSERT INTO devices(id, client_id, name, is_primary)
            VALUES (11, 1, 'main', 1);
            """
        )
        config = {
            "endpoint": "awg31.internal:587",
            "i1": "<b 0x160301>",
            "i2": "<r 16><t>",
            "i3": "<rd 12>",
            "i4": "<rc 24>",
            "i5": "<b 0x01020304><r 8>",
            "jc": 2,
            "jmin": 10,
            "jmax": 20,
            "s1": 64,
            "s2": 96,
            "s3": 48,
            "s4": 12,
            "h1": "1-2",
            "h2": "3",
            "h3": "4",
            "h4": "5",
        }
        db.execute(
            "INSERT INTO connection_settings(engine, host, port, config_json) "
            "VALUES ('amneziawg31', 'awg31.internal', 587, ?)",
            (json.dumps(config, sort_keys=True),),
        )


def test_stage3a_preserves_an_existing_awg3_runtime_byte_for_byte(tmp_path: Path) -> None:
    root = tmp_path / "root"
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database)

    marker = root / "opt/sg-gateway/awg3/local-runtime.marker"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"installed-awg3-runtime-must-not-change\x00\xff")
    before = marker.read_bytes()

    awg3_unit = root / "etc/systemd/system/sg-gateway-awg3.service"
    awg3_unit.parent.mkdir(parents=True)
    awg3_unit.write_text("existing-awg3-unit\n", encoding="utf-8")

    os_boundary = RecordingOS()
    result = Stage3AInstaller(
        source_root=ROOT,
        root=root,
        os_boundary=os_boundary,
    ).migrate(database=database)

    assert marker.read_bytes() == before
    assert (root / "opt/sg-gateway/awg31/bin/awg").is_file()
    assert result.created_credentials == 1
    assert (
        "systemctl",
        "try-restart",
        "sg-gateway-awg3.service",
    ) not in os_boundary.commands
