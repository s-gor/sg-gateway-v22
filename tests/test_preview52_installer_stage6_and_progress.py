from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text(encoding="utf-8")


def _install_fake_awg(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    awg = bin_dir / "awg"
    awg.write_text(
        """#!/bin/sh
case "$1" in
  genkey)
    printf '%s\n' 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
    ;;
  pubkey)
    cat >/dev/null
    printf '%s\n' 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB='
    ;;
  *)
    exit 2
    ;;
esac
""",
        encoding="utf-8",
    )
    awg.chmod(0o755)
    return bin_dir


def _seed_env(tmp_path: Path, *, update: bool) -> dict[str, str]:
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "log"
    bin_dir = _install_fake_awg(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "SG_GATEWAY_ENV": "production",
            "SG_GATEWAY_HOST": "127.0.0.1",
            "SG_GATEWAY_PORT": "18080",
            "SG_GATEWAY_PUBLIC_PORT": "63443",
            "SG_GATEWAY_PUBLIC_ADDRESS": "203.0.113.10",
            "SG_GATEWAY_DATA_DIR": str(data_dir),
            "SG_GATEWAY_LOG_DIR": str(log_dir),
            "SG_GATEWAY_SECRET_KEY": "test-secret",
            "SG_GATEWAY_ADMIN_PASSWORD": "test-password",
            "SG_UPDATE_MODE": "1" if update else "0",
            "SG_SEED_PUBLIC_ADDRESS": "203.0.113.10",
            "SG_SEED_CREATE_ADMIN": "1",
            "SG_GATEWAY_SERVER_NAME": "sg-gateway-fr",
            "SG_GATEWAY_COUNTRY_CODE": "fr",
            "SG_SEED_XRAY_PORT": "443",
            "SG_SEED_AWG_PORT": "585",
            "SG_SEED_REALITY_TARGET": "www.bing.com:443",
            "SG_SEED_REALITY_SNI": "www.bing.com",
            "SG_SEED_XRAY_PUBLIC_KEY": "real-xray-public-key",
            "SG_SEED_XRAY_SHORT_ID": "0123456789abcdef",
            "SG_SEED_VLESS_ENCRYPTION": "mlkem-test-pair",
            "SG_SEED_AWG_PUBLIC_KEY": "real-awg-public-key",
        }
    )
    return env


def _run_seed(tmp_path: Path, *, update: bool) -> Path:
    env = _seed_env(tmp_path, update=update)
    result = subprocess.run(
        [sys.executable, "-m", "app.install_seed"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Database " in result.stdout and "host=203.0.113.10" in result.stdout
    return Path(env["SG_GATEWAY_DATA_DIR"]) / "sg-gateway.sqlite"


def test_stage6_update_repairs_empty_hosts_instead_of_asserting(tmp_path: Path):
    # init_db deliberately starts with empty connection hosts, exactly like the
    # Preview 48/49 source database that caused Preview 51 stage 6 to fail.
    database = _run_seed(tmp_path, update=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT engine, host, port, config_json FROM connection_settings ORDER BY engine"
    ).fetchall()
    assert {row["engine"]: row["host"] for row in rows} == {
        "amneziawg": "203.0.113.10",
        "mihomo": "203.0.113.10",
        "xray": "203.0.113.10",
    }
    for row in rows:
        config = json.loads(row["config_json"])
        assert config["country_code"] == "fr"
    assert connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 1


def test_stage6_clean_seed_creates_one_sg_admin(tmp_path: Path):
    database = _run_seed(tmp_path, update=False)
    connection = sqlite3.connect(database)
    assert connection.execute(
        "SELECT COUNT(*) FROM clients WHERE name = 'sg-admin'"
    ).fetchone()[0] == 1


def test_installer_uses_sg_panel_progress_contract_and_one_error_path():
    assert "[SG-Gateway] [OK]" in INSTALLER
    assert "[SG-Gateway] [-]" in INSTALLER
    assert "Этап ${number}/${TOTAL_STAGES} · ${label}" in INSTALLER
    assert "trap - ERR INT TERM" in INSTALLER
    assert '"$PREFIX/.venv/bin/python" -m app.install_seed' in INSTALLER
    assert "assert update_connection_settings(\"xray\", xray.host" not in INSTALLER
    assert "spinner_loop" not in INSTALLER
    assert "tee -a" not in INSTALLER
    assert "etc/hostname" in INSTALLER and "etc/hosts" in INSTALLER


def test_stage6_update_forces_active_reality_public_key_and_short_id(tmp_path: Path):
    env = _seed_env(tmp_path, update=True)
    database = Path(env["SG_GATEWAY_DATA_DIR"]) / "sg-gateway.sqlite"
    # Create the database once, then inject valid-looking but stale values from
    # an interrupted installation. Preview 54 must not preserve them.
    first = subprocess.run(
        [sys.executable, "-m", "app.install_seed"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT config_json FROM connection_settings WHERE engine = 'xray'"
    ).fetchone()
    config = json.loads(row[0])
    config["public_key"] = "stale-public-key"
    config["short_id"] = "deadbeefdeadbeef"
    connection.execute(
        "UPDATE connection_settings SET config_json = ? WHERE engine = 'xray'",
        (json.dumps(config),),
    )
    connection.commit()
    connection.close()

    second = subprocess.run(
        [sys.executable, "-m", "app.install_seed"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT config_json FROM connection_settings WHERE engine = 'xray'"
    ).fetchone()
    config = json.loads(row[0])
    assert config["public_key"] == "real-xray-public-key"
    assert config["short_id"] == "0123456789abcdef"
    assert connection.execute(
        "SELECT COUNT(*) FROM clients WHERE name = 'sg-admin'"
    ).fetchone()[0] == 1
