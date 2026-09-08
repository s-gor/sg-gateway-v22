import importlib.util
import json
import sqlite3
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "hostd" / "sg_hostd" / "clients_keys_tls_backup_patch.py"
SPEC = importlib.util.spec_from_file_location("clients_keys_tls_backup_patch_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE connection_settings (engine TEXT PRIMARY KEY, enabled INTEGER, config_json TEXT)")
        con.execute("CREATE TABLE device_credentials (id INTEGER PRIMARY KEY, engine TEXT, status TEXT, config_json TEXT)")
        for engine in ("amneziawg", "amneziawg3"):
            con.execute("INSERT INTO connection_settings(engine, enabled, config_json) VALUES (?, 1, '{}')", (engine,))
        con.execute("INSERT INTO device_credentials(id, engine, status, config_json) VALUES (1, 'amneziawg', 'applied', ?)", (json.dumps({"private_key": "old-awg2-client-key"}),))
        con.execute("INSERT INTO device_credentials(id, engine, status, config_json) VALUES (2, 'amneziawg3', 'applied', ?)", (json.dumps({"private_key": "old-awg3-client-key"}),))
        con.commit()
    finally:
        con.close()


def test_destination_policy_keeps_runtime_repaired_awg_configs(tmp_path: Path) -> None:
    db = tmp_path / "sg-gateway.sqlite"
    _make_db(db)
    repaired = {
        "amneziawg": {
            "private_key": "old-awg2-client-key", "server_public_key": "destination-awg2-server-key",
            "endpoint": "203.0.113.10:585", "jc": 4, "jmin": 10, "jmax": 50,
            "s1": 64, "s2": 96, "h1": 1001, "h2": 1002, "h3": 1003, "h4": 1004,
        },
        "amneziawg3": {
            "private_key": "old-awg3-client-key", "server_public_key": "destination-awg3-server-key",
            "endpoint": "203.0.113.10:586", "jc": 4, "jmin": 10, "jmax": 50,
            "s1": 64, "s2": 96, "s3": 48, "s4": 12,
            "h1": "2001", "h2": "2002", "h3": "2003", "h4": "2004",
            "header_protection_key": "destination-header-key",
            "content_padding_addition": "10-100", "rekey_after_time": "100-120",
            "rekey_timeout": "3-7", "reject_after_time": "150-180",
            "keepalive_timeout": "5-15", "max_handshake_attempts": "15-20",
        },
    }
    with patch.destination_protocol_policy(db):
        con = sqlite3.connect(db)
        try:
            for row_id, engine in ((1, "amneziawg"), (2, "amneziawg3")):
                con.execute("UPDATE device_credentials SET status = 'applied', config_json = ? WHERE id = ?", (json.dumps(repaired[engine], sort_keys=True), row_id))
            con.commit()
        finally:
            con.close()
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT engine, status, config_json FROM device_credentials ORDER BY id").fetchall()
    finally:
        con.close()
    assert [row[1] for row in rows] == ["applied", "applied"]
    assert json.loads(rows[0][2]) == repaired["amneziawg"]
    assert json.loads(rows[1][2]) == repaired["amneziawg3"]

def test_destination_policy_preserves_successful_awg_runtime_status(tmp_path: Path) -> None:
    db = tmp_path / "sg-gateway.sqlite"
    _make_db(db)
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE device_credentials SET status = 'pending'")
        con.commit()
    finally:
        con.close()
    with patch.destination_protocol_policy(db):
        con = sqlite3.connect(db)
        try:
            con.execute("UPDATE device_credentials SET status = 'applied'")
            con.commit()
        finally:
            con.close()
    con = sqlite3.connect(db)
    try:
        statuses = [row[0] for row in con.execute("SELECT status FROM device_credentials ORDER BY id").fetchall()]
    finally:
        con.close()
    assert statuses == ["applied", "applied"]
