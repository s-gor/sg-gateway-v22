from __future__ import annotations

import secrets
from urllib.parse import quote

from app.clients.repository import Client, Device, get_client, get_device
from app.clients.sg_subscription_store import subscription_base_url
from app.db import connect, init_db


def _ensure_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS router_subscription_tokens (
            device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_router_subscription_token(client_id: int, device_id: int) -> str:
    init_db()
    with connect() as connection:
        _ensure_table(connection)
        exists = connection.execute(
            "SELECT 1 FROM devices WHERE id = ? AND client_id = ?",
            (device_id, client_id),
        ).fetchone()
        if exists is None:
            return ""

        row = connection.execute(
            "SELECT token FROM router_subscription_tokens WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if row is not None:
            token = str(row["token"] or "").strip()
            if token.startswith("sgr1_") and len(token) >= 32:
                return token

        for _ in range(8):
            token = "sgr1_" + secrets.token_urlsafe(32)
            connection.execute(
                "INSERT OR IGNORE INTO router_subscription_tokens (device_id, token) VALUES (?, ?)",
                (device_id, token),
            )
            row = connection.execute(
                "SELECT token FROM router_subscription_tokens WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            if row is not None:
                return str(row["token"])
    raise RuntimeError("Не удалось создать Router JSON token")


def get_router_subscription_access(token: str) -> tuple[Client, Device] | None:
    clean = str(token or "").strip()
    if not clean.startswith("sgr1_") or len(clean) < 32 or len(clean) > 256:
        return None
    init_db()
    with connect() as connection:
        _ensure_table(connection)
        row = connection.execute(
            """
            SELECT d.id AS device_id, d.client_id AS client_id
            FROM router_subscription_tokens rst
            JOIN devices d ON d.id = rst.device_id
            WHERE rst.token = ?
            """,
            (clean,),
        ).fetchone()
        if row is None:
            return None
        client_id = int(row["client_id"])
        device_id = int(row["device_id"])

    client = get_client(client_id)
    device = get_device(device_id, client_id)
    if client is None or device is None or not client.enabled or not device.enabled:
        return None
    return client, device


def build_router_subscription_url(client: Client, device: Device) -> str:
    token = ensure_router_subscription_token(client.id, device.id)
    base = subscription_base_url()
    if not token or not base:
        return ""
    return f"{base}/sg/router/v1/{quote(token, safe='')}.json"


def build_router_subscription_download_url(client: Client, device: Device) -> str:
    url = build_router_subscription_url(client, device)
    return f"{url}?download=1" if url else ""


def build_openwrt_subscription_url(client: Client, device: Device) -> str:
    token = ensure_router_subscription_token(client.id, device.id)
    base = subscription_base_url()
    if not token or not base:
        return ""
    return f"{base}/sg/router/openwrt/v1/{quote(token, safe='')}.sub"
