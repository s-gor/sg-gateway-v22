from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.db import connect, init_db


@dataclass(frozen=True)
class SettingsTransaction:
    id: int
    engine: str
    previous_host: str
    previous_port: int
    previous_config: dict[str, Any]
    candidate_host: str
    candidate_port: int
    candidate_config: dict[str, Any]
    status: str


def _decode(value: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _from_row(row) -> SettingsTransaction:
    return SettingsTransaction(
        id=int(row["id"]),
        engine=str(row["engine"]),
        previous_host=str(row["previous_host"]),
        previous_port=int(row["previous_port"]),
        previous_config=_decode(row["previous_config_json"]),
        candidate_host=str(row["candidate_host"]),
        candidate_port=int(row["candidate_port"]),
        candidate_config=_decode(row["candidate_config_json"]),
        status=str(row["status"]),
    )


def pending(engine: str) -> SettingsTransaction | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM runtime_settings_transactions
            WHERE engine = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
            """,
            (engine,),
        ).fetchone()
    return _from_row(row) if row is not None else None


def _restore_stale_pending(connection, engine: str) -> None:
    rows = connection.execute(
        """
        SELECT * FROM runtime_settings_transactions
        WHERE engine = ? AND status = 'pending'
        ORDER BY id ASC
        """,
        (engine,),
    ).fetchall()
    if not rows:
        return
    oldest = rows[0]
    connection.execute(
        """
        UPDATE connection_settings
        SET host = ?, port = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE engine = ?
        """,
        (
            oldest["previous_host"],
            int(oldest["previous_port"]),
            oldest["previous_config_json"],
            engine,
        ),
    )
    connection.execute(
        """
        UPDATE runtime_settings_transactions
        SET status = 'rolled_back_stale', finished_at = CURRENT_TIMESTAMP
        WHERE engine = ? AND status = 'pending'
        """,
        (engine,),
    )


def begin(
    engine: str,
    candidate_host: str,
    candidate_port: int,
    candidate_config: dict[str, Any],
) -> SettingsTransaction:
    init_db()
    with connect() as connection:
        _restore_stale_pending(connection, engine)
        current = connection.execute(
            """
            SELECT host, port, config_json
            FROM connection_settings WHERE engine = ?
            """,
            (engine,),
        ).fetchone()
        if current is None:
            raise KeyError(f"Unknown connection engine: {engine}")
        previous_config_json = str(current["config_json"] or "{}")
        candidate_config_json = json.dumps(
            candidate_config, ensure_ascii=False, sort_keys=True
        )
        cursor = connection.execute(
            """
            INSERT INTO runtime_settings_transactions (
                engine,
                previous_host,
                previous_port,
                previous_config_json,
                candidate_host,
                candidate_port,
                candidate_config_json,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                engine,
                str(current["host"]),
                int(current["port"]),
                previous_config_json,
                candidate_host,
                int(candidate_port),
                candidate_config_json,
            ),
        )
        transaction_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE connection_settings
            SET host = ?, port = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (candidate_host, int(candidate_port), candidate_config_json, engine),
        )
        row = connection.execute(
            "SELECT * FROM runtime_settings_transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Не удалось создать транзакцию настроек")
    return _from_row(row)


def rollback(transaction_id: int, status: str = "rolled_back") -> bool:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM runtime_settings_transactions WHERE id = ?",
            (int(transaction_id),),
        ).fetchone()
        if row is None or str(row["status"]) != "pending":
            return False
        connection.execute(
            """
            UPDATE connection_settings
            SET host = ?, port = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (
                row["previous_host"],
                int(row["previous_port"]),
                row["previous_config_json"],
                row["engine"],
            ),
        )
        connection.execute(
            """
            UPDATE runtime_settings_transactions
            SET status = ?, finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, int(transaction_id)),
        )
    return True


def commit(transaction_id: int) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE runtime_settings_transactions
            SET status = 'applied', finished_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (int(transaction_id),),
        )
    return cursor.rowcount > 0


def update_candidate_config(transaction_id: int, candidate_config: dict[str, Any]) -> bool:
    """Refine a pending candidate without changing its rollback snapshot."""
    init_db()
    payload = json.dumps(candidate_config, ensure_ascii=False, sort_keys=True)
    with connect() as connection:
        row = connection.execute(
            "SELECT engine, status FROM runtime_settings_transactions WHERE id = ?",
            (int(transaction_id),),
        ).fetchone()
        if row is None or str(row["status"]) != "pending":
            return False
        connection.execute(
            """
            UPDATE runtime_settings_transactions
            SET candidate_config_json = ?
            WHERE id = ? AND status = 'pending'
            """,
            (payload, int(transaction_id)),
        )
        connection.execute(
            """
            UPDATE connection_settings
            SET config_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (payload, str(row["engine"])),
        )
    return True
