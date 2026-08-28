from __future__ import annotations

import json
from dataclasses import dataclass

from app.constants import AMNEZIAWG3_UDP_PORT, AMNEZIAWG_UDP_PORT
from app.db import connect
from app.maintenance.operations import log_operation


@dataclass(frozen=True)
class ConnectionSettings:
    engine: str
    enabled: bool
    host: str
    port: int
    config: dict


def get_connection_settings(engine: str) -> ConnectionSettings:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT engine, enabled, host, port, config_json
            FROM connection_settings
            WHERE engine = ?
            """,
            (engine,),
        ).fetchone()

    if row is None:
        raise KeyError(f"Unknown connection engine: {engine}")

    return ConnectionSettings(
        engine=row["engine"],
        enabled=bool(row["enabled"]),
        host=row["host"],
        port=int(row["port"]),
        config=json.loads(row["config_json"]),
    )


def _clean_host(host: str) -> str | None:
    value = host.strip()
    return value or None


def _clean_port(port: int | str) -> int | None:
    try:
        value = int(port)
    except (TypeError, ValueError):
        return None
    if 1 <= value <= 65535:
        return value
    return None


def _is_public_xray_form_update() -> bool:
    """Return True only for the ordinary Connections Reality form."""

    try:
        from flask import has_request_context, request
    except ImportError:
        return False
    return bool(has_request_context() and request.endpoint == "update_xray")


def _current_engine_config(engine: str) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT config_json FROM connection_settings WHERE engine = ?",
            (engine,),
        ).fetchone()
    if row is None:
        return {}
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return config if isinstance(config, dict) else {}


def update_connection_settings(engine: str, host: str, port: int | str, config: dict) -> bool:
    clean_host = _clean_host(host)
    if engine == "amneziawg":
        clean_port = AMNEZIAWG_UDP_PORT
    elif engine == "amneziawg3":
        clean_port = AMNEZIAWG3_UDP_PORT
    else:
        clean_port = _clean_port(port)
    if clean_host is None or clean_port is None:
        log_operation(
            action="connection.update",
            target=f"connection:{engine}",
            status="error",
            message="Отклонены недопустимые параметры подключения",
        )
        return False

    stored_config = dict(config)
    if engine == "xray":
        # The Reality TCP listener has one port in both legacy endpoint metadata
        # and the current profile configuration. Keep them atomic.
        stored_config["reality_tcp_port"] = clean_port

        # public_key and short_id are derived from root-owned server identity.
        # The ordinary web form may display them, but only trusted installer or
        # maintenance code outside this route may replace them.
        if _is_public_xray_form_update():
            current_config = _current_engine_config(engine)
            for key in ("public_key", "short_id"):
                if key in current_config:
                    stored_config[key] = current_config[key]

    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE connection_settings
            SET host = ?,
                port = ?,
                config_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (
                clean_host,
                clean_port,
                json.dumps(stored_config, ensure_ascii=False, sort_keys=True),
                engine,
            ),
        )

    if cursor.rowcount == 0:
        log_operation(
            action="connection.update",
            target=f"connection:{engine}",
            status="error",
            message="Неизвестный механизм подключения",
        )
        return False

    log_operation(
        action="connection.update",
        target=f"connection:{engine}",
        message=f"Адрес {engine} обновлён: {clean_host}:{clean_port}",
    )
    return True
