from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tarfile
from pathlib import Path

import pytest


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


def test_data_backup_contains_only_portable_source_of_truth(tmp_path: Path) -> None:
    data = tmp_path / "data"
    config = tmp_path / "config"
    letsencrypt = tmp_path / "letsencrypt"
    output = tmp_path / "out"
    data.mkdir()
    config.mkdir()
    (data / "security").mkdir()
    (data / "security" / "backups").mkdir()
    (data / "security" / "jobs").mkdir()
    (data / "warp").mkdir()
    (data / "geoip").mkdir()
    letsencrypt.mkdir()

    db = data / "sg-gateway.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE clients(id INTEGER PRIMARY KEY, enabled INTEGER)")
        con.execute("INSERT INTO clients(id, enabled) VALUES (1, 1)")
        con.commit()
    finally:
        con.close()

    (config / "engine-secrets.env").write_text("TEST=1\n", encoding="utf-8")
    (data / "security" / "tls-state.json").write_text("{}\n", encoding="utf-8")
    (data / "security" / "backups" / "old.db").write_text("no\n", encoding="utf-8")
    (data / "security" / "jobs" / "job.json").write_text("no\n", encoding="utf-8")
    (data / "warp" / "account.toml").write_text("test\n", encoding="utf-8")
    (data / "geoip" / "cache.dat").write_text("no\n", encoding="utf-8")

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_config_dir=config,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=output,
    )
    archive = Path(created["path"])
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
    assert "payload/var/lib/sg-gateway/sg-gateway.sqlite" in names
    assert "payload/etc/sg-gateway/engine-secrets.env" in names
    assert "payload/var/lib/sg-gateway/security/tls-state.json" in names
    assert "payload/var/lib/sg-gateway/warp/account.toml" in names
    assert not any("security/backups" in name for name in names)
    assert not any("security/jobs" in name for name in names)
    assert not any("/geoip" in name for name in names)
    assert not any("/usr/local/etc/xray" in name for name in names)
    assert not any("/etc/amnezia/amneziawg" in name for name in names)


def test_data_promotion_is_accepted_by_full_restore_validator(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "source-data"
    config = tmp_path / "source-config"
    letsencrypt = tmp_path / "source-letsencrypt"
    source_out = tmp_path / "source-out"
    data.mkdir()
    config.mkdir()
    letsencrypt.mkdir()
    db = data / "sg-gateway.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TABLE clients(id INTEGER PRIMARY KEY, enabled INTEGER)")
        con.execute("INSERT INTO clients(id, enabled) VALUES (1, 1)")
        con.commit()
    finally:
        con.close()
    (config / "engine-secrets.env").write_text("TEST=1\n", encoding="utf-8")

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_config_dir=config,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=source_out,
    )

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
    monkeypatch.setattr(data_backup_runtime.full, "_ensure_dirs", lambda: None)
    monkeypatch.setattr(data_backup_runtime.full, "_backup_dir", lambda: full_store)

    result = data_backup_runtime.promote_uploaded_data_backup()
    promoted = Path(result["full_restore_upload"])
    with tarfile.open(promoted, "r:gz") as tar:
        names = tar.getnames()
    assert "payload" not in names
    assert all(name == "manifest.json" or name.startswith("payload/") for name in names)

    extracted = tmp_path / "full-extracted"
    extracted.mkdir()
    manifest = data_backup_runtime.full._extract_archive(promoted, extracted)
    assert manifest["format"] == data_backup_runtime.full.FORMAT
    assert manifest["data_profile"] is True
    assert (extracted / "payload/var/lib/sg-gateway/sg-gateway.sqlite").is_file()


def test_data_backup_ui_and_hostd_commands_are_wired() -> None:
    main = (ROOT / "app/main.py").read_text(encoding="utf-8")
    template = (ROOT / "app/web/templates/maintenance.html").read_text(encoding="utf-8")
    commands = (ROOT / "hostd/sg_hostd/commands.py").read_text(encoding="utf-8")
    data_source = (ROOT / "hostd/sg_hostd/data_backup_runtime.py").read_text(encoding="utf-8")
    assert '"/maintenance/data-backups"' in main
    assert '"/maintenance/data-backups/restore"' in main
    assert "backup.data.promote" in main
    assert "Клиенты и настройки" in template
    assert "Runtime Contract" in template
    assert '"runtime.contract": _runtime_contract_status' in commands
    assert '"backup.data.create": _data_backup_create' in commands
    assert '"backup.data.verify": _data_backup_verify' in commands
    assert '"backup.data.promote": _data_backup_promote' in commands
    assert "os.chown(root, uid, gid)" in data_source
