from __future__ import annotations

import sqlite3
from pathlib import Path

from sg_hostd import clients_keys_portable_restore_patch as portable


def _db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE device_credentials ("
            "id INTEGER PRIMARY KEY, engine TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL)"
        )
        con.execute(
            "INSERT INTO device_credentials(id, engine, status, config_json) VALUES(1, 'naiveproxy', 'applied', '{\"token\":\"keep-me\"}')"
        )
        con.execute(
            "INSERT INTO device_credentials(id, engine, status, config_json) VALUES(2, 'amneziawg', 'applied', '{\"token\":\"ready\"}')"
        )
        con.commit()
    finally:
        con.close()


def test_destination_runtime_policy_keeps_deferred_applied_credential_dormant(monkeypatch, tmp_path: Path) -> None:
    database_path = tmp_path / "sg-gateway.sqlite"
    _db(database_path)

    from sg_hostd import runtime_contracts

    monkeypatch.setattr(
        runtime_contracts,
        "inspect_runtime_contract",
        lambda **_kwargs: {
            "ok": False,
            "failures": [{"engine": "naiveproxy", "error": "TLS certificate is not ready"}],
        },
    )

    with portable._destination_runtime_policy(database_path) as policy:
        assert policy["deferred_engines"] == ["naiveproxy"]
        con = sqlite3.connect(database_path)
        try:
            assert con.execute(
                "SELECT status FROM device_credentials WHERE id = 1"
            ).fetchone()[0] == "disabled"
            assert con.execute(
                "SELECT status FROM device_credentials WHERE id = 2"
            ).fetchone()[0] == "applied"
        finally:
            con.close()

    con = sqlite3.connect(database_path)
    try:
        row = con.execute(
            "SELECT status, config_json FROM device_credentials WHERE id = 1"
        ).fetchone()
        assert row == ("disabled", '{"token":"keep-me"}')
        assert con.execute(
            "SELECT status FROM device_credentials WHERE id = 2"
        ).fetchone()[0] == "applied"
    finally:
        con.close()
