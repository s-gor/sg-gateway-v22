from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import data_backup_runtime, runtime_contracts


def _active_engine_db(path: Path, engine: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE clients (id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL);
            CREATE TABLE devices (id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL, enabled INTEGER NOT NULL);
            CREATE TABLE device_credentials (device_id INTEGER NOT NULL, engine TEXT NOT NULL, status TEXT NOT NULL);
            INSERT INTO clients(id, enabled) VALUES (1, 1);
            INSERT INTO devices(id, client_id, enabled) VALUES (1, 1, 1);
            """
        )
        con.execute(
            "INSERT INTO device_credentials(device_id, engine, status) VALUES (1, ?, 'applied')",
            (engine,),
        )
        con.commit()
    finally:
        con.close()


def _clients_database(path: Path, *, server_host: str, server_key: str, client_private: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                expires_at TEXT,
                is_primary INTEGER NOT NULL,
                last_seen_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE client_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL,
                engine_object_id TEXT,
                config_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL,
                engine_object_id TEXT,
                config_json TEXT,
                rotated_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                config_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE operation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE runtime_settings_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                previous_host TEXT NOT NULL,
                previous_port INTEGER NOT NULL,
                previous_config_json TEXT NOT NULL,
                candidate_host TEXT NOT NULL,
                candidate_port INTEGER NOT NULL,
                candidate_config_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE sg_subscription_tokens (
                client_id INTEGER PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE router_subscription_tokens (
                device_id INTEGER PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            """
        )
        con.execute(
            "INSERT INTO clients VALUES (1, 'Alice', 1, NULL, '2026-08-20 10:00:00')"
        )
        con.execute(
            "INSERT INTO devices VALUES (1, 1, 'Основной доступ', 1, NULL, 1, NULL, '2026-08-20 10:00:00')"
        )
        credential = {
            "client_name": "Alice",
            "private_key": client_private,
            "public_key": "CLIENT-PUBLIC",
            "address": "10.66.0.3/32",
            "server_public_key": server_key,
            "endpoint": f"{server_host}:585",
            "dns": "1.1.1.1",
            "allowed_ips": "0.0.0.0/0, ::/0",
            "persistent_keepalive": 25,
        }
        con.execute(
            "INSERT INTO device_credentials VALUES (1, 1, 'amneziawg', 'applied', 'CLIENT-PUBLIC', ?, NULL, '2026-08-20 10:00:00')",
            (json.dumps(credential),),
        )
        con.execute(
            "INSERT INTO client_deployments VALUES (1, 1, 'amneziawg', 'applied', 'CLIENT-PUBLIC', ?, '2026-08-20 10:00:00')",
            (json.dumps(credential),),
        )
        settings = {
            "dns": "1.1.1.1",
            "server_public_key": server_key,
            "allowed_ips": "0.0.0.0/0, ::/0",
            "persistent_keepalive": 25,
        }
        con.execute(
            "INSERT INTO connection_settings VALUES ('amneziawg', 1, ?, 585, ?, '2026-08-20 10:00:00')",
            (server_host, json.dumps(settings)),
        )
        con.execute(
            "INSERT INTO operation_log VALUES (1, 'secret.server.action', 'server', 'ok', 'server history', '2026-08-20 10:00:00')"
        )
        con.execute(
            "INSERT INTO sg_subscription_tokens VALUES (1, 'sg1_keep_me', '2026-08-20 10:00:00')"
        )
        con.execute(
            "INSERT INTO router_subscription_tokens VALUES (1, 'sgr1_keep_me', '2026-08-20 10:00:00')"
        )
        con.commit()
    finally:
        con.close()


def test_runtime_contract_blocks_missing_awg3_before_apply(tmp_path: Path) -> None:
    db = tmp_path / "sg-gateway.sqlite"
    _active_engine_db(db, "amneziawg3")
    awg = tmp_path / "awg"
    awg_quick = tmp_path / "awg-quick"
    helper = tmp_path / "helper.sh"
    unit = tmp_path / "awg3.service"
    for path in (awg, awg_quick, helper, unit):
        path.write_text("x\n", encoding="utf-8")
    for path in (awg, awg_quick, helper):
        os.chmod(path, 0o755)
    missing_go = tmp_path / "amneziawg-go"

    specs = {
        "amneziawg3": runtime_contracts.RuntimeSpec(
            "amneziawg3",
            "AWG3",
            True,
            (
                runtime_contracts.Requirement("awg", (str(awg),), True),
                runtime_contracts.Requirement("awg-quick", (str(awg_quick),), True),
                runtime_contracts.Requirement("amneziawg-go", (str(missing_go),), True),
                runtime_contracts.Requirement("helper", (str(helper),), True),
                runtime_contracts.Requirement("unit", (str(unit),)),
            ),
        )
    }
    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    assert result["ok"] is False
    assert "AWG3 требует восстановления" in result["message"]
    assert "Настройки и клиенты не изменены" in result["message"]

    missing_go.write_text("x\n", encoding="utf-8")
    os.chmod(missing_go, 0o755)
    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    assert result["ok"] is True


def test_awg3_deployment_state_does_not_block_client_apply_recovery(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "sg-gateway.sqlite"
    _active_engine_db(db, "amneziawg3")
    files = [tmp_path / name for name in ("awg", "awg-quick", "amneziawg-go", "helper", "unit")]
    for path in files:
        path.write_text("x\n", encoding="utf-8")
    for path in files[:4]:
        os.chmod(path, 0o755)

    specs = {
        "amneziawg3": runtime_contracts.RuntimeSpec(
            "amneziawg3",
            "AWG3",
            True,
            (
                runtime_contracts.Requirement("awg", (str(files[0]),), True),
                runtime_contracts.Requirement("awg-quick", (str(files[1]),), True),
                runtime_contracts.Requirement("amneziawg-go", (str(files[2]),), True),
                runtime_contracts.Requirement("helper", (str(files[3]),), True),
                runtime_contracts.Requirement("unit", (str(files[4]),)),
            ),
        )
    }
    config = tmp_path / "awg3.conf"
    monkeypatch.setattr(runtime_contracts, "AWG3_CONFIG_PATH", config)
    monkeypatch.setattr(runtime_contracts, "_service_active", lambda unit: False)

    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    check = result["checks"][0]
    assert result["ok"] is True
    assert check["ready"] is True
    assert check["deployment"]["required"] is True
    assert check["deployment"]["ready"] is False
    assert check["deployment"]["config_ready"] is False
    assert check["deployment"]["service_active"] is False
    assert len(check["deployment"]["missing"]) == 2

    config.write_text("[Interface]\n", encoding="utf-8")
    monkeypatch.setattr(runtime_contracts, "_service_active", lambda unit: True)
    result = runtime_contracts.inspect_runtime_contract(database_path=db, specs=specs)
    check = result["checks"][0]
    assert result["ok"] is True
    assert check["ready"] is True
    assert check["deployment"] == {
        "required": True,
        "ready": True,
        "missing": [],
        "config_ready": True,
        "service_active": True,
    }


def test_apply_contract_runs_before_engine_mutation_and_awg3_empty_is_safe() -> None:
    client_source = (ROOT / "hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    apply_all = client_source.split("def apply_all_clients()", 1)[1]
    assert apply_all.index("assert_runtime_contract(") < apply_all.index("_repair_deployment_configs()")
    assert apply_all.index("assert_runtime_contract(") < apply_all.index("_apply_awg()")

    awg3_source = (ROOT / "hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    apply_awg3 = awg3_source.split("def apply_awg3()", 1)[1]
    assert apply_awg3.index("if not rows:") < apply_awg3.index("_tool(AWG3_AWG)")


def test_full_restore_contract_is_before_safety_backup() -> None:
    source = (ROOT / "hostd/sg_hostd/full_backup_runtime.py").read_text(encoding="utf-8")
    restore = source.split("def restore_uploaded_full_backup()", 1)[1]
    assert restore.index("assert_runtime_contract(") < restore.index("create_full_backup_archive(prefix=\"SG-Gateway-SAFETY\")")


def test_clients_keys_backup_physically_excludes_server_state(tmp_path: Path) -> None:
    data = tmp_path / "data"
    config = tmp_path / "config"
    letsencrypt = tmp_path / "letsencrypt"
    output = tmp_path / "out"
    data.mkdir()
    config.mkdir()
    letsencrypt.mkdir()
    (data / "security").mkdir()
    (data / "warp").mkdir()
    _clients_database(
        data / "sg-gateway.sqlite",
        server_host="old.example",
        server_key="OLD-SERVER-KEY",
        client_private="CLIENT-PRIVATE-KEEP",
    )
    (config / "engine-secrets.env").write_text("SERVER_SECRET=do-not-copy\n", encoding="utf-8")
    (data / "security" / "tls-state.json").write_text('{"domain":"old.example"}\n', encoding="utf-8")
    (data / "warp" / "account.toml").write_text("do-not-copy\n", encoding="utf-8")
    (letsencrypt / "private.pem").write_text("do-not-copy\n", encoding="utf-8")

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_config_dir=config,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=output,
    )
    assert Path(created["path"]).name.startswith("SG-Gateway-CLIENTS-")
    assert created["profile"] == "clients-and-keys"

    archive = Path(created["path"])
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
        assert names == {
            "manifest.json",
            "payload/var/lib/sg-gateway/sg-gateway.sqlite",
        }
        tar.extractall(extracted)

    manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "clients-and-keys"
    assert manifest["contains_letsencrypt"] is False

    db = extracted / "payload/var/lib/sg-gateway/sg-gateway.sqlite"
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT name FROM clients").fetchone()[0] == "Alice"
        assert con.execute("SELECT token FROM sg_subscription_tokens").fetchone()[0] == "sg1_keep_me"
        assert con.execute("SELECT token FROM router_subscription_tokens").fetchone()[0] == "sgr1_keep_me"
        assert con.execute("SELECT COUNT(*) FROM connection_settings").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM operation_log").fetchone()[0] == 0
        payload = json.loads(con.execute("SELECT config_json FROM device_credentials").fetchone()[0])
        assert con.execute("SELECT COUNT(*) FROM client_deployments").fetchone()[0] == 0
    finally:
        con.close()
    assert payload["private_key"] == "CLIENT-PRIVATE-KEEP"
    assert payload["public_key"] == "CLIENT-PUBLIC"
    assert "server_public_key" not in payload
    assert "endpoint" not in payload
    assert "dns" not in payload
    assert b"OLD-SERVER-KEY" not in db.read_bytes()
    assert b"old.example" not in db.read_bytes()


def test_clients_keys_promotion_preserves_destination_server_settings(tmp_path: Path, monkeypatch) -> None:
    source_data = tmp_path / "source-data"
    source_out = tmp_path / "source-out"
    source_data.mkdir()
    _clients_database(
        source_data / "sg-gateway.sqlite",
        server_host="old.example",
        server_key="OLD-SERVER-KEY",
        client_private="CLIENT-PRIVATE-KEEP",
    )
    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=source_data,
        destination_dir=source_out,
    )

    destination_data = tmp_path / "destination-data"
    destination_data.mkdir()
    _clients_database(
        destination_data / "sg-gateway.sqlite",
        server_host="new.example",
        server_key="NEW-SERVER-KEY",
        client_private="DESTINATION-OLD-CLIENT",
    )
    con = sqlite3.connect(destination_data / "sg-gateway.sqlite")
    try:
        con.execute("UPDATE connection_settings SET config_json = ? WHERE engine = 'amneziawg'", (
            json.dumps({
                "dns": "9.9.9.9",
                "server_public_key": "NEW-SERVER-KEY",
                "allowed_ips": "0.0.0.0/0, ::/0",
                "persistent_keepalive": 31,
            }),
        ))
        con.commit()
    finally:
        con.close()

    data_store = tmp_path / "data-store"
    work = tmp_path / "work"
    full_store = tmp_path / "full-store"
    data_store.mkdir()
    work.mkdir()
    full_store.mkdir()
    shutil.copy2(Path(created["path"]), data_store / data_backup_runtime.RESTORE_UPLOAD_NAME)

    monkeypatch.setattr(data_backup_runtime, "_data_backup_dir", lambda: data_store)
    monkeypatch.setattr(data_backup_runtime, "_work_dir", lambda: work)
    monkeypatch.setattr(data_backup_runtime, "assert_runtime_contract", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(data_backup_runtime.full, "_data_dir", lambda: destination_data)
    monkeypatch.setattr(data_backup_runtime.full, "_destination_public_address", lambda: "new.example")
    monkeypatch.setattr(data_backup_runtime.full, "_restored_tls_state", lambda: {"domain": "new.example"})
    monkeypatch.setattr(data_backup_runtime.full, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(data_backup_runtime.full, "_backup_dir", lambda: full_store)

    result = data_backup_runtime.promote_uploaded_data_backup()
    promoted = Path(result["full_restore_upload"])
    extracted = tmp_path / "promoted"
    extracted.mkdir()
    manifest = data_backup_runtime.full._extract_archive(promoted, extracted)
    assert manifest["data_profile"] is True
    assert manifest["clients_keys_profile"] is True

    db = extracted / "payload/var/lib/sg-gateway/sg-gateway.sqlite"
    con = sqlite3.connect(db)
    try:
        settings = con.execute(
            "SELECT host, port, config_json FROM connection_settings WHERE engine = 'amneziawg'"
        ).fetchone()
        payload = json.loads(con.execute("SELECT config_json FROM device_credentials").fetchone()[0])
        sg_token = con.execute("SELECT token FROM sg_subscription_tokens").fetchone()[0]
    finally:
        con.close()

    assert settings[0] == "new.example"
    assert settings[1] == 585
    assert json.loads(settings[2])["server_public_key"] == "NEW-SERVER-KEY"
    assert payload["private_key"] == "CLIENT-PRIVATE-KEEP"
    assert payload["server_public_key"] == "NEW-SERVER-KEY"
    assert payload["endpoint"] == "new.example:585"
    assert payload["dns"] == "9.9.9.9"
    assert payload["persistent_keepalive"] == 31
    assert sg_token == "sg1_keep_me"
    assert b"OLD-SERVER-KEY" not in db.read_bytes()
    assert b"old.example" not in db.read_bytes()


def test_clients_keys_ui_and_hostd_commands_are_wired() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    data_source = (ROOT / "hostd/sg_hostd/data_backup_runtime.py").read_text(encoding="utf-8")
    ui = (ROOT / "app/web/static/sg-maintenance-recovery-v1.js").read_text(encoding="utf-8")
    assert '"/maintenance/data-backups"' in main
    assert '"/maintenance/data-backups/restore"' in main
    assert "backup.data.promote" in main
    assert "sg-data-backup-card" in template
    assert "CLIENTS & KEYS" in ui
    assert "Клиенты и ключи" in ui
    assert "Настройки сервера не меняются" in ui
    assert '"runtime.contract": _runtime_contract_status' in commands
    assert '"backup.data.create": _data_backup_create' in commands
    assert '"backup.data.verify": _data_backup_verify' in commands
    assert '"backup.data.promote": _data_backup_promote' in commands
    assert 'FORMAT = "sg-gateway-clients-keys-backup"' in data_source
    assert '"profile": "clients-and-keys"' in data_source
    assert 'database.execute("VACUUM")' in data_source
