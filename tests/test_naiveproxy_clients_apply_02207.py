from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "hostd/sg_hostd/naiveproxy_client_runtime_patch.py"
SPEC = importlib.util.spec_from_file_location(
    "naiveproxy_client_runtime_patch_test", MODULE_PATH
)
patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(patch)


class ClientRuntimeError(RuntimeError):
    pass


def _database(tmp_path, *, host="", credentials=0):
    path = tmp_path / "sg-gateway.sqlite"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE connection_settings (engine TEXT, host TEXT)"
    )
    connection.execute(
        "CREATE TABLE device_credentials (engine TEXT)"
    )
    connection.execute(
        "INSERT INTO connection_settings VALUES ('naiveproxy', ?)",
        (host,),
    )
    connection.executemany(
        "INSERT INTO device_credentials VALUES ('naiveproxy')",
        [()] * credentials,
    )
    connection.commit()
    connection.close()
    return path


def _modules(base, runtime):
    client_runtime = SimpleNamespace(
        apply_all_clients=base,
        ClientRuntimeError=ClientRuntimeError,
    )
    commands = SimpleNamespace(apply_all_clients=base)
    patch.install(client_runtime, commands, runtime)
    return client_runtime, commands


def test_common_apply_skips_naiveproxy_when_unused(tmp_path):
    calls = []
    runtime = SimpleNamespace(
        DB_PATH=_database(tmp_path),
        _load=lambda: ({"domain": "", "port": 8447}, [], []),
        sync=lambda: calls.append("sync") or {"ok": True},
        _redact=str,
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime, commands = _modules(base, runtime)

    result = client_runtime.apply_all_clients()

    assert result["ok"] is True
    assert result["engines"] == []
    assert calls == []
    assert commands.apply_all_clients is client_runtime.apply_all_clients


def test_base_runtime_failure_does_not_touch_naiveproxy(tmp_path):
    calls = []
    runtime = SimpleNamespace(
        DB_PATH=tmp_path / "not-used.sqlite",
        sync=lambda: calls.append("sync") or {"ok": True},
        _redact=str,
    )
    base = lambda: {"ok": False, "message": "base failed", "engines": []}
    client_runtime, _commands = _modules(base, runtime)

    result = client_runtime.apply_all_clients()

    assert result["ok"] is False
    assert result["message"] == "base failed"
    assert calls == []


def test_old_backup_without_naiveproxy_profile_is_accepted(tmp_path):
    database = tmp_path / "legacy.sqlite"
    sqlite3.connect(database).close()
    calls = []
    runtime = SimpleNamespace(
        DB_PATH=database,
        _load=lambda: (_ for _ in ()).throw(AssertionError("must not load")),
        sync=lambda: calls.append("sync") or {"ok": True},
        _redact=str,
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime, _commands = _modules(base, runtime)

    result = client_runtime.apply_all_clients()

    assert result["ok"] is True
    assert calls == []


def test_naiveproxy_failure_raises_inside_common_runtime_transaction(tmp_path):
    runtime = SimpleNamespace(
        DB_PATH=_database(tmp_path, host="vpn.example.test", credentials=1),
        _load=lambda: (
            {"domain": "vpn.example.test", "port": 8447},
            [{"username": "sg-1", "password": "not-returned"}],
            [41],
        ),
        sync=lambda: (_ for _ in ()).throw(
            RuntimeError("Caddy validation failed for basic_auth sg-1 secret-value")
        ),
        _redact=lambda value: value.replace("secret-value", "***"),
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime, _commands = _modules(base, runtime)

    with pytest.raises(ClientRuntimeError, match="Caddy validation failed") as error:
        client_runtime.apply_all_clients()

    assert "secret-value" not in str(error.value)


def test_successful_apply_returns_safe_critical_engine_result(tmp_path):
    runtime = SimpleNamespace(
        DB_PATH=_database(tmp_path, host="vpn.example.test", credentials=2),
        _load=lambda: (
            {"domain": "vpn.example.test", "port": 9447},
            [
                {"username": "sg-1", "password": "secret-one"},
                {"username": "sg-2", "password": "secret-two"},
            ],
            [41, 42],
        ),
        sync=lambda: {
            "ok": True,
            "service": "sg-gateway-naiveproxy.service",
            "port": 9447,
            "users": 2,
        },
        _redact=str,
    )
    base = lambda: {
        "ok": True,
        "message": "base applied",
        "warnings": [],
        "engines": [{"engine": "xray", "ok": True, "critical": True}],
    }
    client_runtime, _commands = _modules(base, runtime)

    result = client_runtime.apply_all_clients()
    naive = result["engines"][-1]
    rendered = repr(result).lower()

    assert result["ok"] is True
    assert naive == {
        "engine": "naiveproxy",
        "ok": True,
        "message": "NaiveProxy применён; клиентов: 2",
        "clients": 2,
        "critical": True,
        "service": "sg-gateway-naiveproxy.service",
        "port": 9447,
        "credentials": 2,
    }
    assert "secret-one" not in rendered
    assert "secret-two" not in rendered
    assert "password" not in rendered
