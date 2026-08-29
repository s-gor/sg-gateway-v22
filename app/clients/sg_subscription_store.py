from __future__ import annotations

import secrets
from urllib.parse import quote

from flask import has_request_context, request

from app.clients.repository import Client, get_client
from app.config import load_config
from app.db import connect, init_db
from app.security.tls import overview as tls_overview


def _ensure_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sg_subscription_tokens (
            client_id INTEGER PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _is_enabled_for_client(connection, client_id: int) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM device_credentials dc
        JOIN devices d ON d.id = dc.device_id
        WHERE d.client_id = ? AND dc.engine = 'sgclient'
        LIMIT 1
        """,
        (client_id,),
    ).fetchone()
    return row is not None


def ensure_client_subscription_token(client_id: int) -> str:
    init_db()
    with connect() as connection:
        _ensure_table(connection)
        exists = connection.execute(
            "SELECT 1 FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if exists is None or not _is_enabled_for_client(connection, client_id):
            return ""

        row = connection.execute(
            "SELECT token FROM sg_subscription_tokens WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if row is not None:
            token = str(row["token"] or "").strip()
            if token.startswith("sg1_") and len(token) >= 32:
                return token

        for _ in range(8):
            token = "sg1_" + secrets.token_urlsafe(32)
            connection.execute(
                "INSERT OR IGNORE INTO sg_subscription_tokens (client_id, token) VALUES (?, ?)",
                (client_id, token),
            )
            row = connection.execute(
                "SELECT token FROM sg_subscription_tokens WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if row is not None:
                return str(row["token"])
    raise RuntimeError("Не удалось создать SG Subscription token")


def get_client_by_subscription_token(token: str) -> Client | None:
    clean = str(token or "").strip()
    if not clean.startswith("sg1_") or len(clean) < 32 or len(clean) > 256:
        return None
    init_db()
    with connect() as connection:
        _ensure_table(connection)
        row = connection.execute(
            "SELECT client_id FROM sg_subscription_tokens WHERE token = ?",
            (clean,),
        ).fetchone()
        if row is None:
            return None
        client_id = int(row["client_id"])
        if not _is_enabled_for_client(connection, client_id):
            return None
    return get_client(client_id)


def subscription_base_url() -> str:
    tls = tls_overview()
    public_url = str(tls.get("public_url") or "").strip()
    if tls.get("https_ready") and public_url:
        return public_url.rstrip("/")

    config = load_config()
    address = str(config.public_address or "").strip()
    if address:
        if address.startswith(("http://", "https://")):
            return address.rstrip("/")
        host = f"[{address}]" if ":" in address and not address.startswith("[") else address
        suffix = "" if int(config.public_port) == 80 else f":{int(config.public_port)}"
        return f"http://{host}{suffix}"

    if has_request_context():
        return request.host_url.rstrip("/")
    return ""


def build_sg_subscription_url(client: Client) -> str:
    token = ensure_client_subscription_token(client.id)
    base = subscription_base_url()
    if not token or not base:
        return ""
    return f"{base}/sg/sub/v1/{quote(token, safe='')}"
