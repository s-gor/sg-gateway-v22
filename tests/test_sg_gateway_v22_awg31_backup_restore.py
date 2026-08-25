from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

from sg_hostd import full_backup_runtime as full


def _seed_database(path: Path, *, awg31: bool, legacy_marker: str = "live") -> None:
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
            (
                1,
                "amneziawg",
                f'{{"private_key":"awg2-private-{legacy_marker}","spacing":"awg2"}}',
            ),
            (
                2,
                "amneziawg3",
                f'{{ "private_key" : "awg3-private-{legacy_marker}", "spacing" : "awg3" }}',
            ),
        ):
            database.execute(
                "INSERT INTO device_credentials VALUES (?,11,?,'applied',?,?)",
                (row_id, engine, f"{engine}-public-{legacy_marker}", raw),
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
    awg2_config = awg_root / "awg0.conf"
    awg3_config = awg_root / "awg3.conf"
    awg2_runtime = live / "opt/sg-gateway/awg2"
    awg3_runtime = live / "opt/sg-gateway/awg3"

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
    monkeypatch.setattr(
        full,
        "GENERATED_RUNTIME_PATHS",
        (
            awg2_config,
            live / "etc/mihomo/config.yaml",
            live / "etc/sing-box/config.json",
            live / "usr/local/etc/xray/config.json",
            live / "usr/local/etc/xray/tls",
        ),
    )
    monkeypatch.setattr(full, "_panel_ids", lambda: (os.getuid(), os.getgid()))
    monkeypatch.setattr(full, "_version", lambda: "test-awg31-stage3b")
    monkeypatch.setattr(
        full,
        "_awg31_service_state",
        lambda: {"enabled": True, "active": False},
    )
    monkeypatch.setattr(full, "_destination_public_address", lambda: "192.0.2.1")
    monkeypatch.setattr(full, "_letsencrypt_certificate_domains", lambda: [])

    return {
        "live": live,
        "data": data,
        "config": config,
        "awg_root": awg_root,
        "awg31_config": awg31_config,
        "awg31_state": awg31_state,
        "awg31_runtime": awg31_runtime,
        "awg31_unit": awg31_unit,
        "awg2_config": awg2_config,
        "awg3_config": awg3_config,
        "awg2_runtime": awg2_runtime,
        "awg3_runtime": awg3_runtime,
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


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        item.relative_to(root).as_posix(): item.read_bytes()
        for item in sorted(root.rglob("*"))
        if item.is_file()
    }


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


def test_restore_entrypoint_automatically_rolls_back_post_apply_failure(
    isolated_full_backup: dict[str, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = isolated_full_backup
    database = paths["data"] / "sg-gateway.sqlite"
    paths["config"].mkdir(parents=True, exist_ok=True)
    (paths["config"] / "sg-gateway.env").write_text(
        "SG_GATEWAY_PUBLIC_ADDRESS=192.0.2.1\n", encoding="utf-8"
    )
    (paths["config"] / "runtime.env").write_text(
        "SG_GATEWAY_PUBLIC_ADDRESS=192.0.2.1\n", encoding="utf-8"
    )

    _seed_database(database, awg31=True, legacy_marker="target")
    paths["awg2_config"].parent.mkdir(parents=True, exist_ok=True)
    paths["awg2_config"].write_bytes(b"target-awg2-config")
    paths["awg3_config"].write_bytes(b"target-awg3-config")
    _write_profile(paths)
    target = full.create_full_backup_archive(prefix="AWG31-TARGET")

    database.unlink()
    _seed_database(database, awg31=False, legacy_marker="pre-restore")
    for component in full.AWG31_PROFILE_COMPONENTS:
        full._remove_destination(component)
    paths["awg2_config"].write_bytes(b"pre-awg2-config\x00exact")
    paths["awg3_config"].write_bytes(b"pre-awg3-config\xffexact")
    for runtime, files in (
        (paths["awg2_runtime"], {"bin/awg2": b"pre-awg2-runtime"}),
        (
            paths["awg3_runtime"],
            {
                "bin/awg": b"pre-awg3-tools",
                "bin/amneziawg-go": b"pre-awg3-go",
            },
        ),
    ):
        for relative, content in files.items():
            output = runtime / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)

    pre_database = _database_bytes(database)
    pre_awg2_config = paths["awg2_config"].read_bytes()
    pre_awg3_config = paths["awg3_config"].read_bytes()
    pre_awg2_runtime = _tree_bytes(paths["awg2_runtime"])
    pre_awg3_runtime = _tree_bytes(paths["awg3_runtime"])
    services = {
        "xray.service": {"active": True, "enabled": True},
        "sg-gateway-awg.service": {"active": True, "enabled": True},
        "sg-gateway-awg3.service": {"active": True, "enabled": True},
        "sg-gateway-awg31.service": {"active": False, "enabled": False},
        "mihomo.service": {"active": False, "enabled": False},
        "sg-gateway-singbox.service": {"active": True, "enabled": True},
        "nginx.service": {"active": True, "enabled": True},
        "sg-hostd.service": {"active": True, "enabled": True},
        "sg-gateway.service": {"active": True, "enabled": True},
    }
    pre_services = json.loads(json.dumps(services))

    upload = full._backup_dir() / full.RESTORE_UPLOAD_NAME
    shutil.copy2(Path(target["path"]), upload)

    import sg_hostd.runtime_contracts as runtime_contracts
    import sg_hostd.restore_hardening_patch as restore_hardening

    monkeypatch.setattr(runtime_contracts, "assert_runtime_contract", lambda **_: None)
    monkeypatch.setattr(full, "_normalize_xray_full_access", lambda: None)
    monkeypatch.setattr(full, "_validate_database_as_panel_user", lambda: None)
    monkeypatch.setattr(full, "_apply_client_runtime_required", lambda: None)
    monkeypatch.setattr(restore_hardening, "_local_panel_health", lambda _: None)
    monkeypatch.setattr(
        restore_hardening, "_panel_service_generation", lambda _: "test-generation"
    )
    monkeypatch.setattr(
        restore_hardening, "_schedule_panel_restart_required", lambda _: None
    )
    monkeypatch.setattr(
        restore_hardening,
        "_wait_for_panel_after_scheduled_restart",
        lambda *_: None,
    )
    progress: list[str] = []
    monkeypatch.setattr(full, "_restore_progress", progress.append)

    service_commands: list[tuple[str, ...]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        command = tuple(str(part) for part in command)
        service_commands.append(command)
        if command and command[0] == "systemctl" and len(command) >= 3:
            action = command[1]
            for service in command[2:]:
                if service.startswith("-"):
                    continue
                state = services.setdefault(
                    service, {"active": False, "enabled": False}
                )
                if action == "restart":
                    state["active"] = True
                elif action == "start":
                    state["active"] = True
                elif action == "stop":
                    state["active"] = False
                elif action == "enable":
                    state["enabled"] = True
                elif action == "disable":
                    state["enabled"] = False
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(full.subprocess, "run", fake_run)

    def restart_xray_boundary() -> None:
        services["xray.service"]["active"] = True
        service_commands.append(("systemctl", "restart", "xray.service"))

    monkeypatch.setattr(full, "_restart_xray_required", restart_xray_boundary)

    class InjectedPostApplyFailure(RuntimeError):
        pass

    injected = InjectedPostApplyFailure("injected post-apply validation failure")
    target_was_applied: dict[str, object] = {}
    validation_calls = 0

    def fail_post_apply_validation() -> None:
        nonlocal validation_calls
        validation_calls += 1
        if validation_calls > 1:
            assert _database_bytes(database) == pre_database
            assert _profile_bytes(paths) == {}
            return
        target_was_applied["database"] = _database_bytes(database)
        target_was_applied["profile"] = _profile_bytes(paths)
        assert any(
            row[2] == "amneziawg31"
            for row in target_was_applied["database"]["credentials"]
        )
        assert target_was_applied["profile"]
        raise injected

    monkeypatch.setattr(full, "_validate_runtime_after_restore", fail_post_apply_validation)

    with pytest.raises(InjectedPostApplyFailure) as raised:
        full.restore_uploaded_full_backup()

    assert raised.value is injected
    assert validation_calls == 2
    assert any("Автоматически возвращаю страховочный backup" in item for item in progress)
    assert any("Safety Rollback выполнен и проверен" in item for item in progress)
    assert list(full._backup_dir().glob("SG-Gateway-SAFETY-*.sgbackup"))
    assert any(command[:2] == ("systemctl", "daemon-reload") for command in service_commands)
    assert _database_bytes(database) == pre_database
    assert paths["awg2_config"].read_bytes() == pre_awg2_config
    assert paths["awg3_config"].read_bytes() == pre_awg3_config
    assert _tree_bytes(paths["awg2_runtime"]) == pre_awg2_runtime
    assert _tree_bytes(paths["awg3_runtime"]) == pre_awg3_runtime
    assert services == pre_services
    assert _profile_bytes(paths) == {}
    assert all(
        row[2] != "amneziawg31"
        for row in _database_bytes(database)["credentials"]
    )
    assert not (paths["data"] / ".sg-gateway.sqlite.full-restore").exists()
    assert not list(full._work_dir().glob("restore-*"))
    assert not list(full._work_dir().glob("rollback-*"))


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
