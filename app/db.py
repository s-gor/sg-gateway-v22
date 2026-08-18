from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

from app.config import load_config
from app.constants import AMNEZIAWG3_UDP_PORT, AMNEZIAWG_UDP_PORT

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Legacy Preview 28-45 table.  It is intentionally retained as a read-only
-- migration source so upgrades can preserve every existing UUID/password.
CREATE TABLE IF NOT EXISTS client_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    engine TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    engine_object_id TEXT,
    config_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, engine)
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    expires_at TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_one_primary
ON devices(client_id)
WHERE is_primary = 1;

CREATE INDEX IF NOT EXISTS idx_devices_client
ON devices(client_id, id);

CREATE TABLE IF NOT EXISTS device_credentials (
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

CREATE INDEX IF NOT EXISTS idx_device_credentials_engine
ON device_credentials(engine, status);

CREATE TABLE IF NOT EXISTS connection_settings (
    engine TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runtime_settings_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine TEXT NOT NULL,
    previous_host TEXT NOT NULL,
    previous_port INTEGER NOT NULL,
    previous_config_json TEXT NOT NULL,
    candidate_host TEXT NOT NULL,
    candidate_port INTEGER NOT NULL,
    candidate_config_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_runtime_settings_transactions_engine_status
ON runtime_settings_transactions(engine, status, id);

"""


DEFAULT_CONNECTIONS = {
    "amneziawg": {
        "host": "",
        "port": AMNEZIAWG_UDP_PORT,
        "config_json": (
            '{"dns":"1.1.1.1","country_code":"nl","server_public_key":"PLACEHOLDER_SERVER_PUBLIC_KEY",'
            '"allowed_ips":"0.0.0.0/0, ::/0","persistent_keepalive":25}'
        ),
    },
    "amneziawg3": {
        "host": "",
        "port": AMNEZIAWG3_UDP_PORT,
        "config_json": (
            '{"dns":"1.1.1.1","country_code":"nl","server_public_key":"PLACEHOLDER_AWG3_SERVER_PUBLIC_KEY",'
            '"allowed_ips":"0.0.0.0/0, ::/0","persistent_keepalive":"25-35","generation":3}'
        ),
    },
    "xray": {
        "host": "",
        "port": 443,
        "config_json": (
            '{"security":"reality","country_code":"nl","type":"tcp","flow":"xtls-rprx-vision",'
            '"fingerprint":"chrome","server_name":"www.cloudflare.com",'
            '"public_key":"PLACEHOLDER_REALITY_PUBLIC_KEY","short_id":"PLACEHOLDER_SHORT_ID","vless_encryption":"PLACEHOLDER_VLESS_ENCRYPTION","xhttp_reality_mode":"stream-one","xhttp_tls_mode":"auto"}'
        ),
    },
    "mihomo": {
        "host": "",
        "port": 2099,
        "config_json": (
            '{"country_code":"unknown","domain":"","mieru_enabled":true,'
            '"mieru_port":2099,"mieru_transport":"TCP",'
            '"mieru_multiplexing":"MULTIPLEXING_LOW",'
            '"mieru_handshake":"HANDSHAKE_STANDARD",'
            '"mieru_user_hint_mandatory":true,'
            '"anytls_enabled":false,"anytls_port":8443,'
            '"anytls_padding_scheme":"",'
            '"tuic_enabled":false,"tuic_port":10443,'
            '"tuic_congestion_controller":"bbr",'
            '"tuic_udp_relay_mode":"native","tuic_alpn":"h3"}'
        ),
    },
}


def get_database_path() -> Path:
    return load_config().data_dir / "sg-gateway.sqlite"


def connect() -> sqlite3.Connection:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _seed_connection_settings(connection: sqlite3.Connection) -> None:
    for engine, values in DEFAULT_CONNECTIONS.items():
        connection.execute(
            """
            INSERT OR IGNORE INTO connection_settings (engine, enabled, host, port, config_json)
            VALUES (?, 1, ?, ?, ?)
            """,
            (engine, values["host"], values["port"], values["config_json"]),
        )


def _normalise_xray_credential(value: str | None) -> str | None:
    """Preserve old links while splitting VLESS and Hysteria credentials.

    Preview 45 used the VLESS UUID as Hysteria auth.  During migration we keep
    that value as `hysteria_auth`, so an upgrade never invalidates a working
    Hysteria link.  New devices receive an independent auth token.
    """
    if not value:
        return value
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value
    if not isinstance(payload, dict):
        return value
    if not str(payload.get("hysteria_auth") or "").strip():
        fallback = str(payload.get("uuid") or "").strip()
        if fallback:
            payload["hysteria_auth"] = fallback
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return value


def _format_endpoint_host(host: str) -> str:
    value = str(host or "").strip()
    if ":" in value and not value.startswith("["):
        return f"[{value}]"
    return value


def _migrate_amneziawg_udp_585(connection: sqlite3.Connection) -> None:
    """Enforce the SG-Gateway AmneziaWG UDP 585 product contract.

    This migration is additive and idempotent. It also updates stored device
    endpoints so database state, UI and exported profiles cannot disagree.
    """
    row = connection.execute(
        "SELECT host, port FROM connection_settings WHERE engine = 'amneziawg'"
    ).fetchone()
    if row is None:
        return

    host = _format_endpoint_host(row["host"])
    if int(row["port"]) != AMNEZIAWG_UDP_PORT:
        connection.execute(
            "UPDATE connection_settings SET port = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE engine = 'amneziawg'",
            (AMNEZIAWG_UDP_PORT,),
        )

    if not host:
        return
    endpoint = f"{host}:{AMNEZIAWG_UDP_PORT}"
    rows = connection.execute(
        "SELECT id, config_json FROM device_credentials WHERE engine = 'amneziawg'"
    ).fetchall()
    for credential in rows:
        try:
            config = json.loads(credential["config_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if not isinstance(config, dict) or config.get("endpoint") == endpoint:
            continue
        config["endpoint"] = endpoint
        connection.execute(
            "UPDATE device_credentials SET config_json = ? WHERE id = ?",
            (json.dumps(config, ensure_ascii=False, sort_keys=True), int(credential["id"])),
        )


def _migrate_xray_hysteria2_salamander(connection: sqlite3.Connection) -> None:
    """Add server-level Hysteria2 obfuscation state without changing old links."""
    row = connection.execute(
        "SELECT host, port, config_json FROM connection_settings WHERE engine = 'xray'"
    ).fetchone()
    if row is None:
        return
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        config = {}
    if not isinstance(config, dict):
        config = {}

    changed = False
    defaults = {
        "hysteria2_obfs_mode": "none",
        "hysteria2_obfs_password": None,
        "hysteria2_finalmask": {},
        "hysteria2_salamander_managed": True,
        "hysteria2_uri_scheme": "hysteria2",
    }
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
            changed = True

    mode = str(config.get("hysteria2_obfs_mode") or "none").strip().lower()
    if mode not in {"none", "salamander", "gecko"}:
        config["hysteria2_obfs_mode"] = "none"
        changed = True
    if config.get("hysteria2_finalmask") is None:
        config["hysteria2_finalmask"] = {}
        changed = True
    if not isinstance(config.get("hysteria2_finalmask"), dict):
        # Do not guess how to rewrite malformed custom FinalMask. Keep the
        # feature disabled and preserve the old raw value for diagnostics.
        config["hysteria2_finalmask_invalid"] = config.get("hysteria2_finalmask")
        config["hysteria2_finalmask"] = {}
        config["hysteria2_obfs_mode"] = "none"
        changed = True

    if changed:
        connection.execute(
            """
            UPDATE connection_settings
            SET config_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE engine = 'xray'
            """,
            (json.dumps(config, ensure_ascii=False, sort_keys=True),),
        )


def _migrate_clients_to_devices(connection: sqlite3.Connection) -> None:
    """Create one primary access for every legacy client and copy credentials.

    The legacy table is never deleted.  This makes upgrades reversible and
    guarantees that UUIDs, passwords and selected profiles are copied exactly,
    without regeneration.
    """
    clients = connection.execute(
        "SELECT id, enabled, expires_at, created_at FROM clients ORDER BY id"
    ).fetchall()
    for client in clients:
        client_id = int(client["id"])
        primary = connection.execute(
            """
            SELECT id FROM devices
            WHERE client_id = ? AND is_primary = 1
            ORDER BY id LIMIT 1
            """,
            (client_id,),
        ).fetchone()
        if primary is None:
            cursor = connection.execute(
                """
                INSERT INTO devices (
                    client_id, name, enabled, expires_at, is_primary, created_at
                )
                VALUES (?, 'Основной доступ', 1, ?, 1, ?)
                """,
                (client_id, client["expires_at"], client["created_at"]),
            )
            primary_id = int(cursor.lastrowid)
        else:
            primary_id = int(primary["id"])

        legacy = connection.execute(
            """
            SELECT engine, status, engine_object_id, config_json, created_at
            FROM client_deployments
            WHERE client_id = ?
            ORDER BY id
            """,
            (client_id,),
        ).fetchall()
        for item in legacy:
            config_json = item["config_json"]
            if str(item["engine"]) == "xray":
                config_json = _normalise_xray_credential(config_json)
            connection.execute(
                """
                INSERT OR IGNORE INTO device_credentials (
                    device_id, engine, status, engine_object_id,
                    config_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    primary_id,
                    item["engine"],
                    item["status"],
                    item["engine_object_id"],
                    config_json,
                    item["created_at"],
                ),
            )

    # Also repair xray rows that were created by a partially upgraded build.
    rows = connection.execute(
        "SELECT id, config_json FROM device_credentials WHERE engine = 'xray'"
    ).fetchall()
    for row in rows:
        normalised = _normalise_xray_credential(row["config_json"])
        if normalised != row["config_json"]:
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (normalised, int(row["id"])),
            )


def _migrate_sgclient_subscription_tokens(connection: sqlite3.Connection) -> None:
    # One stable public subscription token per SG Client device.
    rows = connection.execute(
        "SELECT id, config_json FROM device_credentials "
        "WHERE engine = 'sgclient' ORDER BY id"
    ).fetchall()
    for row in rows:
        try:
            config = json.loads(row["config_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        token = str(config.get("subscription_token") or "").strip()
        if len(token) >= 24:
            continue
        config["subscription_token"] = secrets.token_urlsafe(32)
        connection.execute(
            "UPDATE device_credentials SET config_json = ? WHERE id = ?",
            (
                json.dumps(config, ensure_ascii=False, sort_keys=True),
                int(row["id"]),
            ),
        )


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        if not _column_exists(connection, "client_deployments", "config_json"):
            connection.execute("ALTER TABLE client_deployments ADD COLUMN config_json TEXT")
        _seed_connection_settings(connection)
        _migrate_amneziawg_udp_585(connection)
        _migrate_xray_hysteria2_salamander(connection)
        _migrate_clients_to_devices(connection)
        _migrate_sgclient_subscription_tokens(connection)
