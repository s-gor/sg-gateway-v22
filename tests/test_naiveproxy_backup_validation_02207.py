from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "hostd"
    / "sg_hostd"
    / "naiveproxy_backup_patch.py"
)
SPEC = importlib.util.spec_from_file_location("naiveproxy_backup_patch_test", MODULE_PATH)
backup_patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(backup_patch)


def _install_fake_runtime(monkeypatch, runtime) -> None:
    package = ModuleType("sg_hostd")
    package.naiveproxy_runtime = runtime
    monkeypatch.setitem(sys.modules, "sg_hostd", package)
    monkeypatch.setitem(sys.modules, "sg_hostd.naiveproxy_runtime", runtime)


def test_old_backup_without_naiveproxy_profile_is_accepted(tmp_path, monkeypatch):
    database = tmp_path / "old.sqlite"
    sqlite3.connect(database).close()
    runtime = SimpleNamespace(DB_PATH=database)
    _install_fake_runtime(monkeypatch, runtime)

    assert backup_patch._profile_present() is False


def test_configured_naiveproxy_profile_is_detected(tmp_path, monkeypatch):
    database = tmp_path / "configured.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE connection_settings (engine TEXT, host TEXT, port INTEGER, config_json TEXT)"
    )
    connection.execute(
        "INSERT INTO connection_settings VALUES ('naiveproxy', 'vpn.example.com', 8447, '{}')"
    )
    connection.commit()
    connection.close()
    runtime = SimpleNamespace(DB_PATH=database)
    _install_fake_runtime(monkeypatch, runtime)

    assert backup_patch._profile_present() is True


def test_corrupt_configured_profile_fails_restore_sync(tmp_path, monkeypatch):
    database = tmp_path / "corrupt.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE connection_settings (engine TEXT, host TEXT, port INTEGER, config_json TEXT)"
    )
    connection.execute(
        "INSERT INTO connection_settings VALUES ('naiveproxy', 'vpn.example.com', 8447, '{}')"
    )
    connection.commit()
    connection.close()

    def broken_load():
        raise RuntimeError("NaiveProxy credential 7 is invalid")

    runtime = SimpleNamespace(DB_PATH=database, _load=broken_load)
    _install_fake_runtime(monkeypatch, runtime)

    with pytest.raises(RuntimeError, match="credential 7 is invalid"):
        backup_patch._sync_if_configured()


def test_blank_seeded_profile_does_not_start_runtime(tmp_path, monkeypatch):
    database = tmp_path / "blank.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE connection_settings (engine TEXT, host TEXT, port INTEGER, config_json TEXT)"
    )
    connection.execute(
        "INSERT INTO connection_settings VALUES ('naiveproxy', '', 8447, '{}')"
    )
    connection.commit()
    connection.close()
    calls: list[str] = []
    runtime = SimpleNamespace(
        DB_PATH=database,
        _load=lambda: ({"domain": ""}, [], []),
        sync=lambda: calls.append("sync"),
    )
    _install_fake_runtime(monkeypatch, runtime)

    backup_patch._sync_if_configured()

    assert calls == []
