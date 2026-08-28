from __future__ import annotations

from pathlib import Path

from app.clients.repository import (
    device_access_tokens,
    get_primary_device,
    update_client,
)
from app.db import connect, init_db


MARKER_NAME = ".seeded-admin-awg3.pending"
SEEDED_ADMIN_NAME = "sg-admin"


def pending_marker(database: Path) -> Path:
    return database.resolve().parent / MARKER_NAME


def mark_seeded_admin_pending(database: Path) -> Path:
    marker = pending_marker(database)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(SEEDED_ADMIN_NAME + "\n", encoding="utf-8")
    marker.chmod(0o600)
    return marker


def ensure_seeded_admin_awg3(*, database: Path | None = None) -> bool:
    """Add AWG3 to the clean-install admin after its runtime unit exists.

    The marker makes this a clean-install-only migration. Existing installations
    and manually created clients are never modified merely because Stage3A runs.
    """

    if database is not None:
        marker = pending_marker(database)
        if not marker.is_file():
            return False

    init_db()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, expires_at
            FROM clients
            WHERE name = ? COLLATE NOCASE
            ORDER BY id
            LIMIT 1
            """,
            (SEEDED_ADMIN_NAME,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Не найден стартовый клиент sg-admin для добавления AWG3")

    client_id = int(row["id"])
    primary = get_primary_device(client_id)
    if primary is None:
        raise RuntimeError("У стартового клиента sg-admin отсутствует основной доступ")

    access = device_access_tokens(primary.id)
    if "amneziawg3" in access:
        if database is not None:
            pending_marker(database).unlink(missing_ok=True)
        return False

    requested = [*access, "amneziawg3"]
    if not update_client(
        client_id,
        str(row["name"]),
        row["expires_at"],
        ",".join(requested),
    ):
        raise RuntimeError("Не удалось добавить AWG3 в стартовый профиль sg-admin")

    if database is not None:
        pending_marker(database).unlink(missing_ok=True)
    return True
