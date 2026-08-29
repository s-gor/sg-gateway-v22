from __future__ import annotations

import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from sg_hostd import full_backup_runtime as full


def _seed_database(path: Path, *, awg31: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as database:
        database.executescript(
            """
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY, enabled INTEGER, host TEXT, port INTEGER,
                config_json TEXT, updated_at TEXT
            );
            CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE devices (id INTEGER PRIMARY KEY, client_id INTEGER, name TEXT);
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY, device_id INTEGER, engine TEXT, status TEXT,
                engine_object_id TEXT, config_json TEXT,
                UNIQUE(device_id, engine)
            );
            CREATE TABLE runtime_settings_transactions (
                id INTEGER PRIMARY KEY, status TEXT, finished_at TEXT
            );
            INSERT INTO clients VALUES (1, 'device owner');
            INSERT INTO devices VALUES (11, 1, 'phone');
            """
        )
        for row_id, engine, raw in (
            (1, "amneziawg", '{"private_key":"awg2-private","spacing":"awg2"}'),
            (2, "amneziawg3", '{ "private_key" : "awg3-private", "spacing" : "awg3" }'),
        ):
            database.execute(
                "INSERT INTO device_credentials VALUES (?,11,?,'applied',?,?)",
                (row_id, engine, f"{engine}-public", raw),
            )
        database.execute(
            "INSERT INTO connection_settings VALUES "
            "('amneziawg',1,'192.0.2.1',585,'{}','awg2-time'),"
            "('amneziawg3',1,'192.0.2.1',586,'{}','awg3-time')"
        )
        if awg31:
            raw = '{  "private_key" : "awg31-private", "public_key" : "awg31-public", "opaque" : [3, 1]  }'
            database.execute(
                "INSERT INTO device_credentials VALUES "
                "(31,11,'amneziawg31','applied','awg31-public',?)",
                (raw,),
            )
            database.execute(
                "INSERT INTO connection_settings VALUES "
                "('amneziawg31',1,'awg31.internal',587,?, 'awg31-time')",
                ('{ "server_public_key" : "server-public", "profile" : "awg31" }',),
            )


def _database_bytes(path: Path) -> dict[str, tuple]:
    with sqlite3.connect(path) as database:
        return {
            "settings": tuple(
                database.execute(
                    "SELECT engine,enabled,host,port,config_json,updated_at "
                    "FROM connection_settings ORDER BY engine"
                )
            ),
            "credentials": tuple(
                database.execute(
                    "SELECT id,device_id,engine,status,engine_object_id,config_json "
                    "FROM device_credentials ORDER BY id"
                )
            ),
        }


@pytest.fixture()
def isolated_full_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    live = tmp_path / "live"
    data = live / "var/lib/sg-gateway"
    config = live / "etc/sg-gateway"
    awg_root = live / "etc/amnezia/amneziawg"
    awg31_config = awg_root / "awg31"
    awg31_state = data / "awg31"
    awg31_runtime = live / "opt/sg-gateway/awg31"
    awg31_unit = live / "etc/systemd/system/sg-gateway-awg31.service"

    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(data))
    monkeypatch.setattr(full, "CONFIG_DIR", config)
    monkeypatch.setattr(full, "ROOT_COMPONENTS", (config, awg_root))
    monkeypatch.setattr(full, "PORTABLE_STATE_ROOTS", (config,))
    monkeypatch.setattr(
        full,
        "AWG31_PROFILE_COMPONENTS",
        (awg31_config, awg31_state, awg31_runtime, awg31_unit),
    )
    monkeypatch.setattr(full, "DATA_COMPONENTS", ())
    monkeypatch.setattr(full, "_panel_ids", lambda: (os.getuid(), os.getgid()))
    monkeypatch.setattr(full, "_version", lambda: "test-awg31-stage3b")
    monkeypatch.setattr(
        full,
        "_awg31_service_state",
        lambda: {"enabled": True, "active": False},
    )
    monkeypatch.setattr(full, "_destination_public_address", lambda: "192.0.2.1")

    return {
        "live": live,
        "data": data,
        "config": config,
        "awg_root": awg_root,
        "awg31_config": awg31_config,
        "awg31_state": awg31_state,
        "awg31_runtime": awg31_runtime,
        "awg31_unit": awg31_unit,
    }


def _write_profile(paths: dict[str, Path]) -> None:
    files = {
        paths["awg31_config"] / "awg31.conf": b"server-config\x00exact\n",
        paths["awg31_config"] / "peers/device-11.conf": b"peer-config\xffexact\n",
        paths["awg31_state"] / "server-private.key": b"server-private-exact\n",
        paths["awg31_state"] / "server-public.key": b"server-public-exact\n",
        paths["awg31_runtime"] / "bin/awg": b"runtime-awg-exact",
        paths["awg31_runtime"] / "bin/awg-quick": b"runtime-quick-exact",
        paths["awg31_runtime"] / "bin/amneziawg-go": b"runtime-go-exact",
        paths["awg31_unit"]: b"[Unit]\nDescription=AWG31 exact\n",
    }
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


def _profile_bytes(paths: dict[str, Path]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for root_name in ("awg31_config", "awg31_state", "awg31_runtime"):
        root = paths[root_name]
        if root.is_dir():
            for item in sorted(root.rglob("*")):
                if item.is_file():
                    result[f"{root_name}/{item.relative_to(root)}"] = item.read_bytes()
    if paths["awg31_unit"].is_file():
        result["awg31_unit"] = paths["awg31_unit"].read_bytes()
    return result


def _extract(archive: Path, target: Path) -> tuple[dict, Path]:
    manifest = full._extract_archive(archive, target)
    return manifest, target / "payload"


def test_new_backup_restores_awg31_exactly_on_clean_system_and_is_idempotent(
    isolated_full_backup: dict[str, Path], tmp_path: Path,
) -> None:
    paths = isolated_full_backup
    _seed_database(paths["data"] / "sg-gateway.sqlite", awg31=True)
    _write_profile(paths)
    expected_db = _database_bytes(paths["data"] / "sg-gateway.sqlite")
    expected_profile = _profile_bytes(paths)

    created = full.create_full_backup_archive(prefix="AWG31-NEW")
    archive = Path(created["path"])
    extracted = tmp_path / "new-extracted"
    manifest, payload = _extract(archive, extracted)
    assert manifest["awg31_profile"]["format_version"] == 1
    assert manifest["awg31_profile"]["service"] == {"enabled": True, "active": False}

    for root in full.AWG31_PROFILE_COMPONENTS:
        full._remove_destination(root)
    (paths["data"] / "sg-gateway.sqlite").unlink()
    full._restore_payload(payload, preserve_machine_env=True)
    assert _database_bytes(paths["data"] / "sg-gateway.sqlite") == expected_db
    assert _profile_bytes(paths) == expected_profile

    full._restore_payload(payload, preserve_machine_env=True)
    assert _database_bytes(paths["data"] / "sg-gateway.sqlite") == expected_db
    assert _profile_bytes(paths) == expected_profile
    assert len(expected_db["credentials"]) == len(
        _database_bytes(paths["data"] / "sg-gateway.sqlite")["credentials"]
    )


def test_legacy_backup_without_awg31_restores_without_creating_profile(
    isolated_full_backup: dict[str, Path], tmp_path: Path,
) -> None:
    paths = isolated_full_backup
    _seed_database(paths["data"] / "sg-gateway.sqlite", awg31=False)
    legacy_db = _database_bytes(paths["data"] / "sg-gateway.sqlite")
    created = full.create_full_backup_archive(prefix="LEGACY")
    archive = Path(created["path"])
    extracted = tmp_path / "legacy-extracted"
    manifest, payload = _extract(archive, extracted)
    assert "awg31_profile" not in manifest

    full._restore_payload(payload, preserve_machine_env=True)
    assert _database_bytes(paths["data"] / "sg-gateway.sqlite") == legacy_db
    assert _profile_bytes(paths) == {}
    assert full._AWG31_RESTORE_MODE == "legacy"


def test_failed_restore_safety_rollback_removes_partial_awg31_and_preserves_awg2_awg3(
    isolated_full_backup: dict[str, Path], tmp_path: Path,
) -> None:
    paths = isolated_full_backup
    database = paths["data"] / "sg-gateway.sqlite"
    _seed_database(database, awg31=False)
    pre_database = _database_bytes(database)
    safety = full.create_full_backup_archive(prefix="SAFETY")
    _, safety_payload = _extract(Path(safety["path"]), tmp_path / "safety")

    database.unlink()
    _seed_database(database, awg31=True)
    _write_profile(paths)
    failed = full.create_full_backup_archive(prefix="FAILED-TARGET")
    _, failed_payload = _extract(Path(failed["path"]), tmp_path / "failed")

    full._restore_payload(failed_payload, preserve_machine_env=True)
    assert _profile_bytes(paths)
    with pytest.raises(RuntimeError, match="injected post-restore failure"):
        try:
            raise RuntimeError("injected post-restore failure")
        except Exception:
            full._restore_payload(safety_payload, preserve_machine_env=False)
            raise

    assert _database_bytes(database) == pre_database
    assert _profile_bytes(paths) == {}
    assert all(row[2] != "amneziawg31" for row in pre_database["credentials"])


def test_new_awg31_manifest_rejects_missing_profile_payload(
    isolated_full_backup: dict[str, Path], tmp_path: Path,
) -> None:
    paths = isolated_full_backup
    _seed_database(paths["data"] / "sg-gateway.sqlite", awg31=True)
    _write_profile(paths)
    created = full.create_full_backup_archive(prefix="AWG31-CORRUPT")
    archive = Path(created["path"])

    unpacked = tmp_path / "unpacked"
    with tarfile.open(archive, "r:gz") as source:
        source.extractall(unpacked)
    (unpacked / "payload" / paths["awg31_state"].relative_to("/") / "server-private.key").unlink()
    corrupted = tmp_path / "corrupted.sgbackup"
    with tarfile.open(corrupted, "w:gz") as target:
        target.add(unpacked / "manifest.json", arcname="manifest.json")
        for child in (unpacked / "payload").iterdir():
            target.add(child, arcname=f"payload/{child.name}")

    with pytest.raises(RuntimeError, match="AWG31 backup payload is incomplete"):
        full._extract_archive(corrupted, tmp_path / "verify-corrupt")
