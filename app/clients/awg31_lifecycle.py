from __future__ import annotations

import base64
import json
import secrets
from pathlib import Path
from typing import Any

from app.db import connect, init_db

PROFILE_ID = "awg31"
ENGINE_ID = "amneziawg31"
ENDPOINT = "awg31.internal:587"
TRANSPORT = "udp"
INTERFACE = "awg31"
NETWORK = "10.131.0.0/24"
DNS = "1.1.1.1"
CONFIG_ROOT = Path("/etc/amnezia/amneziawg/awg31")
SERVER_CONFIG = CONFIG_ROOT / "awg31.conf"
PEER_CONFIG_DIR = CONFIG_ROOT / "peers"
RUNTIME_ROOT = Path("/opt/sg-gateway/awg31")
STATE_ROOT = Path("/var/lib/sg-gateway/awg31")


def _x25519_public(private: bytes) -> bytes:
    scalar = int.from_bytes(private, "little")
    prime = 2**255 - 19
    x1, x2, z2, x3, z3, swap = 9, 1, 0, 9, 1, 0
    for bit in range(254, -1, -1):
        current = (scalar >> bit) & 1
        swap ^= current
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = current
        a = (x2 + z2) % prime
        aa = a * a % prime
        b = (x2 - z2) % prime
        bb = b * b % prime
        e = (aa - bb) % prime
        c = (x3 + z3) % prime
        d = (x3 - z3) % prime
        da = d * a % prime
        cb = c * b % prime
        x3 = (da + cb) ** 2 % prime
        z3 = x1 * (da - cb) ** 2 % prime
        x2 = aa * bb % prime
        z2 = e * (aa + 121665 * e) % prime
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return (x2 * pow(z2, prime - 2, prime) % prime).to_bytes(32, "little")


def _generate_keypair() -> tuple[str, str]:
    raw = bytearray(secrets.token_bytes(32))
    raw[0] &= 248
    raw[31] &= 127
    raw[31] |= 64
    private = bytes(raw)
    public = _x25519_public(private)
    return (
        base64.b64encode(private).decode("ascii"),
        base64.b64encode(public).decode("ascii"),
    )


def _label(row: Any) -> str:
    return str(row["client_name"]) if bool(row["is_primary"]) else f"{row['client_name']} · {row['device_name']}"


def _address(device_id: int) -> str:
    return f"10.131.0.{2 + ((device_id - 1) % 253)}/32"


def _payload(
    row: Any,
    preserved: dict[str, Any] | None = None,
    *,
    settings_parameters: dict[str, Any] | None = None,
    server_public_key: str | None = None,
    header_protection_key: str | None = None,
) -> dict[str, Any]:
    current = dict(preserved or {})
    if not current.get("private_key") or not current.get("public_key"):
        current["private_key"], current["public_key"] = _generate_keypair()
    if settings_parameters is None or server_public_key is None or header_protection_key is None:
        from app.connections.awg31 import get_settings

        settings = get_settings()
        if settings_parameters is None:
            settings_parameters = dict(settings.parameters)
        if server_public_key is None:
            server_public_key = settings.server_public_key
        if header_protection_key is None:
            header_protection_key = settings.header_protection_key
    current.update(
        {
            "profile": PROFILE_ID,
            "engine": ENGINE_ID,
            "client_name": _label(row),
            "address": _address(int(row["device_id"])),
            "dns": DNS,
            "endpoint": ENDPOINT,
            "transport": TRANSPORT,
            "interface": INTERFACE,
            "network": NETWORK,
            "allowed_ips": "0.0.0.0/0",
            "persistent_keepalive": 25,
            "generation": 31,
            "server_public_key": server_public_key,
            "header_protection_key": header_protection_key,
            **{name.lower(): value for name, value in settings_parameters.items()},
        }
    )
    return current


def build_credential_payload(
    *,
    device_id: int,
    device_name: str,
    is_primary: bool,
    client_name: str,
    preserved: dict[str, Any] | None = None,
    settings_parameters: dict[str, Any] | None = None,
    server_public_key: str | None = None,
    header_protection_key: str | None = None,
) -> dict[str, Any]:
    """Build one AWG31 credential without mutating repository globals."""
    return _payload(
        {
            "device_id": device_id,
            "device_name": device_name,
            "is_primary": is_primary,
            "client_name": client_name,
        },
        preserved,
        settings_parameters=settings_parameters,
        server_public_key=server_public_key,
        header_protection_key=header_protection_key,
    )


def _device_row(connection, device_id: int):
    return connection.execute(
        """
        SELECT d.id AS device_id, d.name AS device_name, d.is_primary,
               c.id AS client_id, c.name AS client_name
        FROM devices d JOIN clients c ON c.id = d.client_id
        WHERE d.id = ?
        """,
        (device_id,),
    ).fetchone()


def _stored_payload(connection, device_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT config_json FROM device_credentials WHERE device_id = ? AND engine = ?",
        (device_id, ENGINE_ID),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["config_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def ensure_peer(device_id: int, preserved: dict[str, Any] | None = None) -> None:
    init_db()
    with connect() as connection:
        row = _device_row(connection, device_id)
        if row is None:
            raise ValueError(f"Unknown device: {device_id}")
        existing = preserved if preserved is not None else _stored_payload(connection, device_id)
        payload = _payload(row, existing)
        connection.execute(
            """
            INSERT INTO device_credentials (device_id, engine, status, engine_object_id, config_json)
            VALUES (?, ?, 'pending', ?, ?)
            ON CONFLICT(device_id, engine) DO UPDATE SET
                status = 'pending', engine_object_id = excluded.engine_object_id,
                config_json = excluded.config_json
            """,
            (
                device_id,
                ENGINE_ID,
                payload["public_key"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )


def delete_peer(device_id: int) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM device_credentials WHERE device_id = ? AND engine = ?",
            (device_id, ENGINE_ID),
        )
    return bool(cursor.rowcount)


def _client_devices(client_id: int) -> list[int]:
    with connect() as connection:
        return [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM devices WHERE client_id = ? ORDER BY id", (client_id,)
            ).fetchall()
        ]


def _snapshot(client_id: int) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    with connect() as connection:
        for device_id in _client_devices(client_id):
            payload = _stored_payload(connection, device_id)
            if payload is not None:
                result[device_id] = payload
    return result
