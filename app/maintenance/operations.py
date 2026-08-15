from __future__ import annotations

from dataclasses import dataclass

from app.db import connect


@dataclass(frozen=True)
class OperationEntry:
    id: int
    action: str
    target: str
    status: str
    message: str
    created_at: str


def log_operation(action: str, target: str, message: str, status: str = "ok") -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO operation_log (action, target, status, message)
            VALUES (?, ?, ?, ?)
            """,
            (action, target, status, message),
        )


def list_operations(limit: int = 25) -> list[OperationEntry]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, action, target, status, message, created_at
            FROM operation_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        OperationEntry(
            id=row["id"],
            action=row["action"],
            target=row["target"],
            status=row["status"],
            message=row["message"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def count_operations() -> int:
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM operation_log").fetchone()
    return int(row["total"])