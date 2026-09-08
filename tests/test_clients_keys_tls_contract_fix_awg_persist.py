from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from sg_hostd import clients_keys_tls_contract_fix as contract_fix


def _database(path: Path) -> None:
    db = sqlite3.connect(path)
    try:
        db.executescript(
            """
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                host TEXT NOT NULL DEFAULT '',
                port INTEGER NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY,
                device_id INTEGER NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL,
                config_json TEXT
            );
            """
        )
        db.execute(
            "INSERT INTO connection_settings(engine, enabled, config_json) VALUES('amneziawg', 1, '{}')"
        )
        db.execute(
            "INSERT INTO connection_settings(engine, enabled, config_json) VALUES('amneziawg3', 1, '{}')"
        )
        db.execute(
            "INSERT INTO device_credentials(id, device_id, engine, status, config_json) VALUES(1, 1, 'amneziawg', 'pending', ?)",
            (json.dumps({'private_key': 'awg2-key'}),),
        )
        db.execute(
            "INSERT INTO device_credentials(id, device_id, engine, status, config_json) VALUES(2, 1, 'amneziawg3', 'pending', ?)",
            (json.dumps({'private_key': 'awg3-key'}),),
        )
        db.commit()
    finally:
        db.close()


def test_destination_policy_keeps_successful_awg_runtime_repair(tmp_path: Path) -> None:
    database = tmp_path / 'sg-gateway.sqlite'
    _database(database)
    tls = SimpleNamespace(XRAY_PROFILE_FLAGS={})

    with contract_fix._destination_protocol_policy(tls, database):
        db = sqlite3.connect(database)
        try:
            awg2 = {'private_key': 'awg2-key', 'jc': 4, 'jmin': 10, 'jmax': 50, 's1': 64, 's2': 96,
                    'h1': '1', 'h2': '2', 'h3': '3', 'h4': '4'}
            awg3 = {'private_key': 'awg3-key', 'jc': 4, 'jmin': 10, 'jmax': 50, 's1': 64, 's2': 96,
                    's3': 48, 's4': 12, 'h1': '1', 'h2': '2', 'h3': '3', 'h4': '4',
                    'header_protection_key': 'hp'}
            db.execute(
                "UPDATE device_credentials SET status='applied', config_json=? WHERE id=1",
                (json.dumps(awg2, sort_keys=True),),
            )
            db.execute(
                "UPDATE device_credentials SET status='applied', config_json=? WHERE id=2",
                (json.dumps(awg3, sort_keys=True),),
            )
            db.commit()
        finally:
            db.close()

    db = sqlite3.connect(database)
    try:
        rows = db.execute(
            "SELECT id, status, config_json FROM device_credentials ORDER BY id"
        ).fetchall()
    finally:
        db.close()

    assert rows[0][1] == 'applied'
    assert json.loads(rows[0][2])['jc'] == 4
    assert rows[1][1] == 'applied'
    assert json.loads(rows[1][2])['header_protection_key'] == 'hp'
