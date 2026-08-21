from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sg_hostd import clients_keys_tls_backup_patch as tls_patch
from sg_hostd import data_backup_runtime


def _runtime_db(path: Path) -> None:
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
                '{"uuid":"uuid-1","profiles":["xhttp_tls"]}'
            );
            INSERT INTO device_credentials VALUES (
                2, 1, 'anytls', 'applied', 'anytls-1',
                '{"password":"keep-me"}'
            );
            INSERT INTO connection_settings VALUES (
                'xray', 1, 'new.example', 443,
                '{"reality_tcp_enabled":false,"xhttp_reality_enabled":false,"xhttp_tls_enabled":false,"hysteria2_enabled":false}',
                CURRENT_TIMESTAMP
            );
            INSERT INTO connection_settings VALUES (
                'mihomo', 1, 'new.example', 2099,
                '{"mieru_enabled":false,"anytls_enabled":false,"tuic_enabled":false}',
                CURRENT_TIMESTAMP
            );
            """
        )
        con.commit()
    finally:
        con.close()


def _clients_db(path: Path) -> None:
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
                1, 1, 'xray', 'applied', 'uuid-1', '{"uuid":"uuid-1"}'
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
    archive.mkdir(parents=True)
    live.mkdir(parents=True)
    renewal.mkdir(parents=True)
    (archive / "fullchain1.pem").write_text("CERT\n", encoding="utf-8")
    (archive / "privkey1.pem").write_text("KEY\n", encoding="utf-8")
    (live / "fullchain.pem").symlink_to(f"../../archive/{domain}/fullchain1.pem")
    (live / "privkey.pem").symlink_to(f"../../archive/{domain}/privkey1.pem")
    (renewal / f"{domain}.conf").write_text("[renewalparams]\n", encoding="utf-8")


def test_portable_contract_uses_data_backup_hook_and_restores_filtered_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "destination.sqlite"
    _runtime_db(database)
    captured: dict = {}

    def contract(**kwargs):
        captured.update(kwargs)
        con = sqlite3.connect(database)
        try:
            xray_status, xray_raw = con.execute(
                "SELECT status, config_json FROM device_credentials WHERE id = 1"
            ).fetchone()
            anytls_status = con.execute(
                "SELECT status FROM device_credentials WHERE id = 2"
            ).fetchone()[0]
        finally:
            con.close()
        assert xray_status == "disabled"
        assert json.loads(xray_raw)["profiles"] == ["xhttp_tls"]
        assert anytls_status == "disabled"
        return {"ok": True, "checks": []}

    monkeypatch.setattr(data_backup_runtime, "assert_runtime_contract", contract)
    result = tls_patch._runtime_contract_for_destination(data_backup_runtime, database)
    assert result["ok"] is True
    assert result["disabled_destination_protocols_skipped"] is True
    assert captured["include_all_critical"] is True
    assert "xray" not in captured["specs"]

    con = sqlite3.connect(database)
    try:
        xray_status, xray_raw = con.execute(
            "SELECT status, config_json FROM device_credentials WHERE id = 1"
        ).fetchone()
        anytls_status = con.execute(
            "SELECT status FROM device_credentials WHERE id = 2"
        ).fetchone()[0]
    finally:
        con.close()
    assert xray_status == "applied"
    assert json.loads(xray_raw)["profiles"] == ["xhttp_tls"]
    assert anytls_status == "applied"


def test_clients_keys_does_not_archive_stale_certificate_when_https_is_not_ready(
    tmp_path: Path, monkeypatch
) -> None:
    data = tmp_path / "data"
    out = tmp_path / "out"
    work = tmp_path / "work"
    letsencrypt = tmp_path / "letsencrypt"
    (data / "security").mkdir(parents=True)
    out.mkdir()
    work.mkdir()
    _clients_db(data / "sg-gateway.sqlite")
    domain = "vpn.example.org"
    (data / "security" / "tls-state.json").write_text(
        json.dumps({"domain": domain, "https_ready": False}),
        encoding="utf-8",
    )
    _tls_tree(letsencrypt, domain)
    monkeypatch.setattr(data_backup_runtime, "_work_dir", lambda: work)

    created = data_backup_runtime.create_data_backup_archive(
        source_data_dir=data,
        source_letsencrypt_dir=letsencrypt,
        destination_dir=out,
    )
    assert created["certificates"] is False
    assert created["certificate_domains"] == []
