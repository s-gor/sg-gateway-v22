from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "hostd"
    / "sg_hostd"
    / "naiveproxy_runtime.py"
)
SPEC = importlib.util.spec_from_file_location(
    "sg_naiveproxy_transaction_runtime",
    MODULE_PATH,
)
runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime)


def _make_db(
    path: Path,
    *,
    credential: dict,
    certificate: Path,
    private_key: Path,
) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE connection_settings (
            engine TEXT, host TEXT, port INTEGER, config_json TEXT
        );
        CREATE TABLE clients (id INTEGER, enabled INTEGER);
        CREATE TABLE devices (id INTEGER, client_id INTEGER, enabled INTEGER);
        CREATE TABLE device_credentials (
            id INTEGER,
            device_id INTEGER,
            engine TEXT,
            status TEXT,
            config_json TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO connection_settings VALUES (?, ?, ?, ?)",
        (
            "naiveproxy",
            "vpn.example.com",
            8447,
            json.dumps(
                {
                    "certificate_path": str(certificate),
                    "private_key_path": str(private_key),
                }
            ),
        ),
    )
    connection.execute("INSERT INTO clients VALUES (1, 1)")
    connection.execute("INSERT INTO devices VALUES (1, 1, 1)")
    connection.execute(
        """
        INSERT INTO device_credentials
        VALUES (1, 1, 'naiveproxy', 'creating', ?)
        """,
        (json.dumps(credential),),
    )
    connection.commit()
    connection.close()


def _point_runtime(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "etc"
    state_dir = tmp_path / "state"
    tls_dir = config_dir / "tls"
    binary = tmp_path / "caddy"
    binary.write_text("binary", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(runtime, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(runtime, "CONFIG_PATH", config_dir / "Caddyfile")
    monkeypatch.setattr(runtime, "STATE_DIR", state_dir)
    monkeypatch.setattr(runtime, "STATE_PATH", state_dir / "state.json")
    monkeypatch.setattr(runtime, "TLS_DIR", tls_dir)
    monkeypatch.setattr(runtime, "TLS_CERTIFICATE", tls_dir / "fullchain.pem")
    monkeypatch.setattr(runtime, "TLS_PRIVATE_KEY", tls_dir / "privkey.pem")
    monkeypatch.setattr(runtime, "BINARY", binary)


def test_restored_credential_cannot_inject_caddyfile(tmp_path, monkeypatch):
    certificate = tmp_path / "source-cert"
    private_key = tmp_path / "source-key"
    certificate.write_text("cert", encoding="utf-8")
    private_key.write_text("key", encoding="utf-8")
    database = tmp_path / "sg-gateway.sqlite"
    _make_db(
        database,
        credential={
            "username": "alice\nadmin off",
            "password": "A" * 32,
        },
        certificate=certificate,
        private_key=private_key,
    )
    monkeypatch.setattr(runtime, "DB_PATH", database)

    with pytest.raises(RuntimeError, match="credential 1 is invalid"):
        runtime._load()


def test_failed_restart_restores_config_state_certificate_and_key(
    tmp_path,
    monkeypatch,
):
    certificate = tmp_path / "source-cert"
    private_key = tmp_path / "source-key"
    certificate.write_text("new-cert", encoding="utf-8")
    private_key.write_text("new-key", encoding="utf-8")
    database = tmp_path / "sg-gateway.sqlite"
    _make_db(
        database,
        credential={"username": "alice", "password": "A" * 32},
        certificate=certificate,
        private_key=private_key,
    )
    monkeypatch.setattr(runtime, "DB_PATH", database)
    _point_runtime(tmp_path, monkeypatch)
    runtime.TLS_DIR.mkdir(parents=True)
    runtime.STATE_DIR.mkdir(parents=True)
    runtime.CONFIG_PATH.write_text("old-config", encoding="utf-8")
    runtime.STATE_PATH.write_text("old-state", encoding="utf-8")
    runtime.TLS_CERTIFICATE.write_text("old-cert", encoding="utf-8")
    runtime.TLS_PRIVATE_KEY.write_text("old-key", encoding="utf-8")

    def fake_run(command, timeout=30):
        if command[:3] == ["systemctl", "is-active", "--quiet"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["systemctl", "enable", "--now"]:
            return subprocess.CompletedProcess(
                command,
                1,
                "",
                "restart failed",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runtime, "_run", fake_run)
    with pytest.raises(RuntimeError, match="restart failed"):
        runtime.sync()

    assert runtime.CONFIG_PATH.read_text(encoding="utf-8") == "old-config"
    assert runtime.STATE_PATH.read_text(encoding="utf-8") == "old-state"
    assert runtime.TLS_CERTIFICATE.read_text(encoding="utf-8") == "old-cert"
    assert runtime.TLS_PRIVATE_KEY.read_text(encoding="utf-8") == "old-key"


def test_first_apply_commits_only_validated_tls_and_config(
    tmp_path,
    monkeypatch,
):
    certificate = tmp_path / "source-cert"
    private_key = tmp_path / "source-key"
    certificate.write_text("new-cert", encoding="utf-8")
    private_key.write_text("new-key", encoding="utf-8")
    database = tmp_path / "sg-gateway.sqlite"
    _make_db(
        database,
        credential={"username": "alice", "password": "A" * 32},
        certificate=certificate,
        private_key=private_key,
    )
    monkeypatch.setattr(runtime, "DB_PATH", database)
    _point_runtime(tmp_path, monkeypatch)

    def fake_run(command, timeout=30):
        if command[:3] == ["systemctl", "is-active", "--quiet"]:
            return subprocess.CompletedProcess(command, 3, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(runtime, "_run", fake_run)
    result = runtime.sync()

    assert result["ok"] is True
    assert runtime.TLS_CERTIFICATE.read_text(encoding="utf-8") == "new-cert"
    assert runtime.TLS_PRIVATE_KEY.read_text(encoding="utf-8") == "new-key"
    assert ":8447, vpn.example.com:8447" in runtime.CONFIG_PATH.read_text(
        encoding="utf-8"
    )
