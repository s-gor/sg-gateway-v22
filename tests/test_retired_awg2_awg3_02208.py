from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hostd"))


def test_client_repository_no_longer_supports_awg2_or_awg3() -> None:
    from app.clients import repository

    assert "amneziawg" not in repository.SUPPORTED_ENGINES
    assert "amneziawg3" not in repository.SUPPORTED_ENGINES
    assert "amneziawg31" in repository.SUPPORTED_ENGINES
    assert "amneziawg" not in repository.RUNTIME_ENGINES
    assert "amneziawg3" not in repository.RUNTIME_ENGINES

    engines, _, _ = repository._parse_access(
        "amneziawg,amneziawg3,amneziawg31,xray"
    )
    assert engines == ["amneziawg31", "xray"]


def test_legacy_awg_credentials_stay_durable_but_are_hidden_from_active_reads(
    tmp_path,
    monkeypatch,
) -> None:
    from app.clients import repository

    database_path = tmp_path / "sg-gateway.sqlite"
    database = sqlite3.connect(database_path)
    try:
        database.execute(
            "CREATE TABLE device_credentials ("
            "id INTEGER PRIMARY KEY, device_id INTEGER, engine TEXT, status TEXT, "
            "engine_object_id TEXT, config_json TEXT)"
        )
        database.executemany(
            "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json) "
            "VALUES (7, ?, 'applied', ?, '{}')",
            [
                ("amneziawg", "legacy-awg2"),
                ("amneziawg3", "legacy-awg3"),
                ("amneziawg31", "current-awg31"),
                ("xray", "current-xray"),
            ],
        )
        database.commit()
    finally:
        database.close()

    class _Connection:
        def __enter__(self):
            self.db = sqlite3.connect(database_path)
            self.db.row_factory = sqlite3.Row
            return self.db

        def __exit__(self, exc_type, exc, tb):
            self.db.close()

    monkeypatch.setattr(repository, "init_db", lambda: None)
    monkeypatch.setattr(repository, "connect", lambda: _Connection())

    visible = repository.list_device_credentials(7)
    assert [item.engine for item in visible] == ["amneziawg31", "xray"]

    database = sqlite3.connect(database_path)
    try:
        durable = dict(
            database.execute(
                "SELECT engine, engine_object_id FROM device_credentials ORDER BY engine"
            )
        )
    finally:
        database.close()
    assert durable["amneziawg"] == "legacy-awg2"
    assert durable["amneziawg3"] == "legacy-awg3"
    assert durable["amneziawg31"] == "current-awg31"


def test_runtime_policy_removes_awg2_awg3_from_critical_contract() -> None:
    from sg_hostd import retired_awg_runtime_patch as patch

    class _Result:
        def __init__(self, engine, ok, message, clients):
            self.engine = engine
            self.ok = ok
            self.message = message
            self.clients = clients

    client_runtime = SimpleNamespace(
        EngineResult=_Result,
        _apply_awg=lambda: (_ for _ in ()).throw(AssertionError("AWG2 executed")),
    )
    awg3_runtime = SimpleNamespace(
        apply_awg3=lambda: (_ for _ in ()).throw(AssertionError("AWG3 executed")),
    )
    runtime_contracts = SimpleNamespace(
        DEFAULT_SPECS={
            "amneziawg": object(),
            "amneziawg3": object(),
            "amneziawg31": object(),
            "xray": object(),
        }
    )

    patch.install(client_runtime, awg3_runtime, runtime_contracts)

    assert set(runtime_contracts.DEFAULT_SPECS) == {"amneziawg31", "xray"}
    assert client_runtime._apply_awg().ok is True
    assert client_runtime._apply_awg().clients == 0
    assert awg3_runtime.apply_awg3().ok is True
    assert awg3_runtime.apply_awg3().clients == 0
