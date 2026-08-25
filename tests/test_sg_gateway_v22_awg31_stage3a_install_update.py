from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

# Load the clients package before the autouse fixture imports mihomo.service;
# this avoids exercising the accepted stage-2 Flask hook through a partial
# mihomo import.
from app.clients import repository as _repository  # noqa: F401
from app.maintenance.awg31_stage3a import (
    AWG3_GO_SHA256,
    AWG3_TOOLS_SHA256,
    AWG31_GO_SHA256,
    AWG31_TOOLS_SHA256,
    Stage3AInstaller,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeOS:
    def __init__(self, fail_contains: str | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.fail_contains = fail_contains

    def run(self, *command: str) -> None:
        self.commands.append(tuple(command))
        rendered = " ".join(command)
        if self.fail_contains and self.fail_contains in rendered:
            raise RuntimeError(f"injected OS failure: {rendered}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seed_database(path: Path, *, include_existing_awg31: bool = False) -> None:
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
            INSERT INTO clients(id, name) VALUES (1, 'alpha'), (2, 'beta');
            INSERT INTO devices(id, client_id, name, is_primary)
            VALUES (11, 1, 'main', 1), (22, 2, 'phone', 1);
            INSERT INTO connection_settings(engine, host, port, config_json)
            VALUES (
              'amneziawg31', 'awg31.internal', 587,
              '{"endpoint":"awg31.internal:587","i1":"<b 0x160301>","i2":"<r 16><t>","i3":"<rd 12>","i4":"<rc 24>","i5":"<b 0x01020304><r 8>","jc":2,"jmin":10,"jmax":20,"s1":1,"s2":2,"s3":3,"s4":4,"h1":"1-2","h2":"3","h3":"4","h4":"5"}'
            );
            """
        )
        for device_id in (11, 22):
            for engine, marker in (
                ("amneziawg", f"awg2-{device_id}"),
                ("amneziawg3", f"awg3-{device_id}"),
            ):
                payload = json.dumps(
                    {"marker": marker, "private_key": marker + "-private", "public_key": marker + "-public"},
                    sort_keys=True,
                )
                db.execute(
                    "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json) "
                    "VALUES (?, ?, 'applied', ?, ?)",
                    (device_id, engine, marker, payload),
                )
        if include_existing_awg31:
            payload = json.dumps(
                {
                    "profile": "awg31",
                    "private_key": "preserved-awg31-private",
                    "public_key": "preserved-awg31-public",
                    "address": "10.131.0.12/32",
                    "endpoint": "awg31.internal:587",
                    "transport": "udp",
                },
                sort_keys=True,
            )
            db.execute(
                "INSERT INTO device_credentials(device_id, engine, status, engine_object_id, config_json) "
                "VALUES (11, 'amneziawg31', 'applied', 'preserved-awg31-public', ?)",
                (payload,),
            )


def _rows(path: Path, engines: tuple[str, ...]) -> list[tuple]:
    placeholders = ",".join("?" for _ in engines)
    with sqlite3.connect(path) as db:
        return db.execute(
            f"SELECT device_id, engine, status, engine_object_id, config_json "
            f"FROM device_credentials WHERE engine IN ({placeholders}) ORDER BY device_id, engine",
            engines,
        ).fetchall()


@pytest.fixture(scope="module")
def provisioned(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("awg31-stage3a-clean")
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database, include_existing_awg31=True)
    awg2_config = root / "etc/amnezia/amneziawg/awg0.conf"
    awg3_config = root / "etc/amnezia/amneziawg/awg3.conf"
    awg3_unit = root / "etc/systemd/system/sg-gateway-awg3.service"
    awg2_runtime = root / "opt/sg-gateway/awg2/keep"
    for path, body in (
        (awg2_config, "awg2-config-byte-for-byte"),
        (awg3_config, "awg3-config-byte-for-byte"),
        (awg3_unit, "awg3-service-byte-for-byte"),
        (awg2_runtime, "awg2-runtime-byte-for-byte"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    fake = FakeOS()
    installer = Stage3AInstaller(source_root=ROOT, root=root, os_boundary=fake)
    before_legacy = _rows(database, ("amneziawg", "amneziawg3"))
    result = installer.migrate(database=database)
    preserved_files = {
        awg2_config: "awg2-config-byte-for-byte",
        awg3_config: "awg3-config-byte-for-byte",
        awg3_unit: "awg3-service-byte-for-byte",
        awg2_runtime: "awg2-runtime-byte-for-byte",
    }
    return root, database, fake, installer, before_legacy, result, preserved_files


def test_clean_install_creates_isolated_awg31_runtime_paths_and_service(provisioned) -> None:
    root, _, fake, _, _, result, preserved_files = provisioned
    expected = (
        root / "opt/sg-gateway/deploy/sg-gateway-awg31.service",
        root / "opt/sg-gateway/deploy/sg-gateway-awg31-userspace.sh",
        root / "opt/sg-gateway/deploy/sg-gateway-awg31ctl",
        root / "opt/sg-gateway/deploy/repair-awg31-runtime.sh",
        root / "opt/sg-gateway/awg31/bin/awg",
        root / "opt/sg-gateway/awg31/bin/awg-quick",
        root / "opt/sg-gateway/awg31/bin/amneziawg-go",
        root / "etc/amnezia/amneziawg/awg31/awg31.conf",
        root / "etc/amnezia/amneziawg/awg31/peers",
        root / "var/lib/sg-gateway/awg31",
        root / "etc/systemd/system/sg-gateway-awg31.service",
    )
    assert all(path.exists() for path in expected)
    for path in expected[:7]:
        if path.suffix != ".service":
            assert os.access(path, os.X_OK), path
    unit = (root / "etc/systemd/system/sg-gateway-awg31.service").read_text()
    helper = (root / "opt/sg-gateway/deploy/sg-gateway-awg31-userspace.sh").read_text()
    server = (root / "etc/amnezia/amneziawg/awg31/awg31.conf").read_text()
    assert "sg-gateway-awg31-userspace.sh" in unit
    assert "IFACE=awg31" in helper
    assert "10.131.0.1/24" in helper
    assert "ListenPort = 587" in server
    assert "tcp" not in (unit + helper + server).lower()
    assert result.created_credentials == 1
    assert result.peer_configs == 2
    with sqlite3.connect(root / "var/lib/sg-gateway/sg-gateway.sqlite") as db:
        settings_payload = json.loads(
            db.execute(
                "SELECT config_json FROM connection_settings WHERE engine = 'amneziawg31'"
            ).fetchone()[0]
        )
    assert settings_payload["server_public_key"]
    assert (root / "etc/amnezia/amneziawg/awg31/peers/device-11.conf").is_file()
    assert (root / "etc/amnezia/amneziawg/awg31/peers/device-22.conf").is_file()
    assert ("systemctl", "daemon-reload") in fake.commands
    assert ("systemctl", "enable", "sg-gateway-awg31.service") in fake.commands
    assert ("systemctl", "restart", "sg-gateway-awg31.service") in fake.commands
    assert ("systemctl", "try-restart", "sg-gateway-awg3.service") in fake.commands
    for path, expected_body in preserved_files.items():
        assert path.read_text() == expected_body


def test_runtime_sources_are_sha_verified_and_awg3_30_is_separate(provisioned) -> None:
    root, _, _, _, _, _, _ = provisioned
    vendor = root / "opt/sg-gateway/vendor/cores"
    assert _sha256(vendor / "amneziawg-tools-3.1.20260812.tar.gz") == AWG31_TOOLS_SHA256
    assert _sha256(vendor / "amneziawg-go-linux-amd64-v3.1.20260814") == AWG31_GO_SHA256
    assert _sha256(vendor / "amneziawg-tools-3.0.20260805.tar.gz") == AWG3_TOOLS_SHA256
    assert _sha256(vendor / "amneziawg-go-linux-amd64-v3.0.0") == AWG3_GO_SHA256
    awg31_version = os.popen(str(root / "opt/sg-gateway/awg31/bin/awg") + " --version").read()
    awg3_version = os.popen(str(root / "opt/sg-gateway/awg3/bin/awg") + " --version").read()
    assert "3.1.20260812" in awg31_version
    assert "3.0.20260805" in awg3_version
    assert (root / "opt/sg-gateway/awg31").resolve() != (root / "opt/sg-gateway/awg3").resolve()


def test_migration_preserves_awg2_awg3_and_existing_awg31_keys_idempotently(provisioned) -> None:
    _, database, fake, installer, before_legacy, _, preserved_files = provisioned
    after_first = _rows(database, ("amneziawg31",))
    assert len(after_first) == 2
    preserved = json.loads(next(row[4] for row in after_first if row[0] == 11))
    assert preserved["private_key"] == "preserved-awg31-private"
    assert preserved["public_key"] == "preserved-awg31-public"
    assert _rows(database, ("amneziawg", "amneziawg3")) == before_legacy
    for path, expected_body in preserved_files.items():
        assert path.read_text() == expected_body

    second = installer.migrate(database=database)
    after_second = _rows(database, ("amneziawg31",))
    assert second.created_credentials == 0
    assert after_second == after_first
    assert _rows(database, ("amneziawg", "amneziawg3")) == before_legacy
    assert fake.commands.count(("systemctl", "try-restart", "sg-gateway-awg3.service")) == 2
    for path, expected_body in preserved_files.items():
        assert path.read_text() == expected_body


def test_rollback_removes_partial_awg31_and_allows_retry(tmp_path: Path) -> None:
    root = tmp_path / "root"
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database)
    before_legacy = _rows(database, ("amneziawg", "amneziawg3"))
    awg3_marker = root / "opt/sg-gateway/awg3/original-runtime.marker"
    awg2_config = root / "etc/amnezia/amneziawg/awg0.conf"
    awg3_config = root / "etc/amnezia/amneziawg/awg3.conf"
    awg3_unit = root / "etc/systemd/system/sg-gateway-awg3.service"
    for path, body in (
        (awg3_marker, "original-awg3"),
        (awg2_config, "original-awg2-config"),
        (awg3_config, "original-awg3-config"),
        (awg3_unit, "original-awg3-service"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    failing = Stage3AInstaller(
        source_root=ROOT,
        root=root,
        os_boundary=FakeOS(fail_contains="restart sg-gateway-awg31.service"),
    )
    with pytest.raises(RuntimeError, match="injected OS failure"):
        failing.migrate(database=database)

    assert _rows(database, ("amneziawg31",)) == []
    assert _rows(database, ("amneziawg", "amneziawg3")) == before_legacy
    assert not (root / "opt/sg-gateway/awg31").exists()
    assert not (root / "etc/systemd/system/sg-gateway-awg31.service").exists()
    assert not (root / "etc/amnezia/amneziawg/awg31").exists()
    assert awg3_marker.read_text() == "original-awg3"
    assert awg2_config.read_text() == "original-awg2-config"
    assert awg3_config.read_text() == "original-awg3-config"
    assert awg3_unit.read_text() == "original-awg3-service"
    assert not (root / "opt/sg-gateway/vendor/cores/amneziawg-tools-3.1.20260812.tar.gz").exists()
    assert not (root / "opt/sg-gateway/vendor/cores/amneziawg-go-linux-amd64-v3.1.20260814").exists()

    retry = Stage3AInstaller(source_root=ROOT, root=root, os_boundary=FakeOS())
    result = retry.migrate(database=database)
    assert result.created_credentials == 2
    assert len(_rows(database, ("amneziawg31",))) == 2


def test_uninstall_removes_only_awg31_and_preserves_records_without_purge(tmp_path: Path) -> None:
    root = tmp_path / "root"
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database, include_existing_awg31=True)
    fake = FakeOS()
    installer = Stage3AInstaller(source_root=ROOT, root=root, os_boundary=fake)
    installer.migrate(database=database)
    legacy_before = _rows(database, ("amneziawg", "amneziawg3"))
    awg31_before = _rows(database, ("amneziawg31",))
    awg2_marker = root / "opt/sg-gateway/awg2/keep"
    awg3_marker = root / "etc/amnezia/amneziawg/awg3.conf"
    awg2_marker.parent.mkdir(parents=True, exist_ok=True)
    awg3_marker.parent.mkdir(parents=True, exist_ok=True)
    awg2_marker.write_text("awg2")
    awg3_marker.write_text("awg3")

    installer.uninstall(database=database, purge_data=False)
    assert not (root / "opt/sg-gateway/awg31").exists()
    assert not (root / "etc/amnezia/amneziawg/awg31").exists()
    assert not (root / "var/lib/sg-gateway/awg31").exists()
    assert not (root / "etc/systemd/system/sg-gateway-awg31.service").exists()
    assert awg2_marker.read_text() == "awg2"
    assert awg3_marker.read_text() == "awg3"
    assert _rows(database, ("amneziawg", "amneziawg3")) == legacy_before
    assert _rows(database, ("amneziawg31",)) == awg31_before
    assert ("ip", "link", "delete", "awg31") in fake.commands
    assert not (root / "var/run/amneziawg/awg31.sock").exists()


def test_uninstall_explicit_purge_deletes_only_awg31_records(tmp_path: Path) -> None:
    root = tmp_path / "root"
    database = root / "var/lib/sg-gateway/sg-gateway.sqlite"
    _seed_database(database, include_existing_awg31=True)
    installer = Stage3AInstaller(source_root=ROOT, root=root, os_boundary=FakeOS())
    installer.migrate(database=database)
    legacy_before = _rows(database, ("amneziawg", "amneziawg3"))
    installer.uninstall(database=database, purge_data=True)
    assert _rows(database, ("amneziawg31",)) == []
    assert _rows(database, ("amneziawg", "amneziawg3")) == legacy_before


def test_installer_updater_and_uninstall_entrypoints_are_wired_without_workflows() -> None:
    install = (ROOT / "install.sh").read_text()
    update = (ROOT / "deploy/update-from-github.sh").read_text()
    uninstall = (ROOT / "deploy/uninstall-awg31.sh").read_text()
    install_core = (ROOT / "deploy/install-core.sh").read_text()
    update_core = (ROOT / "deploy/update-from-github-core.sh").read_text()
    assert "app.maintenance.awg31_stage3a migrate" in install
    assert "Bootstrap commit:" in update
    assert "app.maintenance.awg31_stage3a migrate" in update_core
    assert "run_stage3a_migration" in update_core
    assert "stage_backup_and_prepare" in install_core
    assert "capture_service_state" in update_core
    assert "app.maintenance.awg31_stage3a uninstall" in uninstall
    assert "--purge-data" in uninstall
    assert not (ROOT / ".github/workflows/export-awg31-worktree.yml").exists()
    assert not (ROOT / ".github/workflows/export-python-wheelhouse.yml").exists()
