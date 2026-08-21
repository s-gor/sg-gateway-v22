from __future__ import annotations

import json
import sqlite3
import tarfile
from pathlib import Path

from sg_hostd import data_backup_runtime
from sg_hostd import clients_keys_tls_backup_patch as tls_patch


def _client_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER);
            CREATE TABLE devices (id INTEGER PRIMARY KEY, client_id INTEGER, name TEXT, enabled INTEGER, is_primary INTEGER);
            CREATE TABLE device_credentials (
                id INTEGER PRIMARY KEY, device_id INTEGER, engine TEXT, status TEXT,
                engine_object_id TEXT, config_json TEXT
            );
            CREATE TABLE connection_settings (
                engine TEXT PRIMARY KEY, enabled INTEGER, host TEXT, port INTEGER,
                config_json TEXT, updated_at TEXT
            );
            INSERT INTO clients VALUES (1, 'Alice', 1);
            INSERT INTO devices VALUES (1, 1, 'Main', 1, 1);
            INSERT INTO device_credentials VALUES (
                1, 1, 'xray', 'applied', 'uuid-1',
                '{"uuid":"uuid-1","profiles":["reality_tcp","xhttp_tls"]}'
            );
            INSERT INTO connection_settings VALUES (
                'xray', 1, 'new.example', 443,
                '{"reality_tcp_enabled":true,"xhttp_reality_enabled":false,"xhttp_tls_enabled":false,"hysteria2_enabled":false}',
                CURRENT_TIMESTAMP
            );
            """
        )
        con.commit()
    finally:
        con.close()


def _tls_tree(root: Path, domain: str) -> None:
    archive = root / "archive" / domain
    live = root / "live" / domain
    renewal = root / "renewal"
    account = root / "accounts" / "acme-v02.api.letsencrypt.org" / "directory" / "acct123"
    archive.mkdir(parents=True)
    live.mkdir(parents=True)
    renewal.mkdir(parents=True)
    account.mkdir(parents=True)
    (archive / "fullchain1.pem").write_text("CERTIFICATE\n", encoding="utf-8")
    (archive / "privkey1.pem").write_text("PRIVATE KEY\n", encoding="utf-8")
    (live / "fullchain.pem").symlink_to(f"../../archive/{domain}/fullchain1.pem")
    (live / "privkey.pem").symlink_to(f"../../archive/{domain}/privkey1.pem")
    (renewal / f"{domain}.conf").write_text(
        "[renewalparams]\naccount = acct123\n",
        encoding="utf-8",
    )
    (account / "meta.json").write_text("{}\n", encoding="utf-8")


def test_clients_keys_backup_adds_only_active_https_identity(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    out = tmp_path / "out"
    work = tmp_path / "work"
    letsencrypt = tmp_path / "letsencrypt"
    (data / "security").mkdir(parents=True)
    out.mkdir()
    work.mkdir()
    _client_db(data / "sg-gateway.sqlite")
    domain = "vpn.example.org"
    (data / "security" / "tls-state.json").write_text(
        json.dumps(
            {
                "domain": domain,
                "https_ready": True,
                "public_port": 65443,
                "panel_port": 65443,
                "backend_port": 18080,
                "backup": "source-machine-backup",
                "certificate": {"serial": "123"},
            }
        ),
        encoding="utf-8",
    )
    _tls_tree(letsencrypt, domain)
    monkeypatch.setattr(data_backup_runtime, "_work_dir", lambda: work)

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=out,
    )
    assert created["certificates"] is True
    assert created["certificate_domains"] == [domain]

    archive = Path(created["path"])
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
        assert f"payload/etc/letsencrypt/live/{domain}/fullchain.pem" in names
        assert f"payload/etc/letsencrypt/live/{domain}/privkey.pem" in names
        assert f"payload/etc/letsencrypt/archive/{domain}/fullchain1.pem" in names
        assert f"payload/etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org/directory/acct123/meta.json" in names
        state_member = tar.extractfile(
            f"payload/{data_backup_runtime.CANONICAL_DATA_DIR.relative_to('/')}/security/tls-state.json"
        )
        assert state_member is not None
        state = json.loads(state_member.read().decode("utf-8"))
        assert state["domain"] == domain
        assert state["certificate_path"] == f"/etc/letsencrypt/live/{domain}/fullchain.pem"
        assert "public_port" not in state
        assert "panel_port" not in state
        assert "backend_port" not in state
        assert "backup" not in state

    verified = data_backup_runtime._verify_archive(archive)
    assert verified["contains_letsencrypt_certificates"] is True
    assert verified["certificate_domains"] == [domain]
    assert verified["checks"]["tls_identity"] == "ok"


def test_destination_protocol_policy_filters_only_runtime_view_and_restores_db(tmp_path: Path) -> None:
    db_path = tmp_path / "destination.sqlite"
    _client_db(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO device_credentials VALUES (2, 1, 'amneziawg3', 'applied', 'awg3', '{}')"
        )
        con.execute(
            "INSERT INTO connection_settings VALUES ('amneziawg3', 0, 'new.example', 586, '{}', CURRENT_TIMESTAMP)"
        )
        con.commit()
    finally:
        con.close()

    with tls_patch.destination_protocol_policy(db_path):
        con = sqlite3.connect(db_path)
        try:
            xray_status, xray_raw = con.execute(
                "SELECT status, config_json FROM device_credentials WHERE id = 1"
            ).fetchone()
            awg3_status = con.execute(
                "SELECT status FROM device_credentials WHERE id = 2"
            ).fetchone()[0]
        finally:
            con.close()
        assert xray_status == "applied"
        assert json.loads(xray_raw)["profiles"] == ["reality_tcp"]
        assert awg3_status == "disabled"

    con = sqlite3.connect(db_path)
    try:
        xray_status, xray_raw = con.execute(
            "SELECT status, config_json FROM device_credentials WHERE id = 1"
        ).fetchone()
        awg3_status = con.execute(
            "SELECT status FROM device_credentials WHERE id = 2"
        ).fetchone()[0]
    finally:
        con.close()
    assert xray_status == "applied"
    assert json.loads(xray_raw)["profiles"] == ["reality_tcp", "xhttp_tls"]
    assert awg3_status == "applied"


def test_portable_runtime_contract_skips_destination_disabled_critical_engine(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "destination.sqlite"
    _client_db(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute("UPDATE connection_settings SET enabled = 0 WHERE engine = 'xray'")
        con.commit()
    finally:
        con.close()

    from sg_hostd import runtime_contracts

    monkeypatch.setattr(
        runtime_contracts,
        "_requirement_ready",
        lambda requirement: (_ for _ in ()).throw(AssertionError("disabled engine inspected")),
    )
    result = tls_patch._runtime_contract_for_destination(data_backup_runtime, db_path)
    assert result["ok"] is True
    assert result["checks"] == []
    assert result["disabled_destination_protocols_skipped"] is True
