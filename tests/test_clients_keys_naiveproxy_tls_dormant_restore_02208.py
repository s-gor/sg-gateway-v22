from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hostd"))

from sg_hostd import naiveproxy_client_runtime_patch as naive_patch


def _database(path: Path) -> None:
    db = sqlite3.connect(path)
    try:
        db.execute("CREATE TABLE connection_settings (engine TEXT, host TEXT)")
        db.execute("CREATE TABLE device_credentials (engine TEXT)")
        db.execute(
            "INSERT INTO connection_settings VALUES ('naiveproxy', 'vpn.example.test')"
        )
        db.execute("INSERT INTO device_credentials VALUES ('naiveproxy')")
        db.commit()
    finally:
        db.close()


def test_naiveproxy_tls_readiness_failure_from_sync_is_deferred_during_restore(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "sg-gateway.sqlite"
    _database(database_path)

    binary = tmp_path / "caddy"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    cert = tmp_path / "fullchain.pem"
    key = tmp_path / "privkey.pem"
    cert.write_text("certificate", encoding="utf-8")
    key.write_text("private-key", encoding="utf-8")

    sync_calls: list[str] = []
    runtime = SimpleNamespace(
        DB_PATH=database_path,
        BINARY=binary,
        _load=lambda: (
            {
                "domain": "vpn.example.test",
                "port": 8447,
                "certificate_path": str(cert),
                "private_key_path": str(key),
            },
            [{"username": "restored-user", "password": "restored-password"}],
            [41],
        ),
        sync=lambda: sync_calls.append("sync") or (_ for _ in ()).throw(
            RuntimeError("NaiveProxy TLS certificate is not ready")
        ),
        _redact=str,
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime = SimpleNamespace(
        apply_all_clients=base,
        ClientRuntimeError=RuntimeError,
    )
    commands = SimpleNamespace(apply_all_clients=base)
    naive_patch.install(client_runtime, commands, runtime)
    monkeypatch.setenv(naive_patch.RESTORE_CONTEXT_ENV, "1")

    result = client_runtime.apply_all_clients()

    assert sync_calls == ["sync"]
    assert result["ok"] is True
    naive = result["engines"][-1]
    assert naive["engine"] == "naiveproxy"
    assert naive["deferred"] is True
    assert naive["ok"] is False
    assert naive["credentials"] == 1
    assert "TLS certificate is not ready" in naive["message"]


def test_naiveproxy_tls_readiness_failure_from_sync_remains_fatal_outside_restore(
    tmp_path,
) -> None:
    database_path = tmp_path / "sg-gateway.sqlite"
    _database(database_path)

    binary = tmp_path / "caddy"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    cert = tmp_path / "fullchain.pem"
    key = tmp_path / "privkey.pem"
    cert.write_text("certificate", encoding="utf-8")
    key.write_text("private-key", encoding="utf-8")

    runtime = SimpleNamespace(
        DB_PATH=database_path,
        BINARY=binary,
        _load=lambda: (
            {
                "domain": "vpn.example.test",
                "port": 8447,
                "certificate_path": str(cert),
                "private_key_path": str(key),
            },
            [{"username": "user", "password": "password"}],
            [41],
        ),
        sync=lambda: (_ for _ in ()).throw(
            RuntimeError("NaiveProxy TLS certificate is not ready")
        ),
        _redact=str,
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime = SimpleNamespace(
        apply_all_clients=base,
        ClientRuntimeError=RuntimeError,
    )
    commands = SimpleNamespace(apply_all_clients=base)
    naive_patch.install(client_runtime, commands, runtime)

    try:
        client_runtime.apply_all_clients()
    except RuntimeError as exc:
        assert str(exc) == "NaiveProxy: NaiveProxy TLS certificate is not ready"
    else:
        raise AssertionError("ordinary NaiveProxy apply must stay strict")
