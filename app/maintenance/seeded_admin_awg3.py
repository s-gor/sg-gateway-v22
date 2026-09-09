from __future__ import annotations

from pathlib import Path


MARKER_NAME = ".seeded-admin-awg3.pending"
SEEDED_ADMIN_NAME = "sg-admin"


def pending_marker(database: Path) -> Path:
    return database.resolve().parent / MARKER_NAME


def mark_seeded_admin_pending(database: Path) -> Path:
    """Keep the historical marker contract without provisioning retired AWG3."""

    marker = pending_marker(database)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(SEEDED_ADMIN_NAME + "\n", encoding="utf-8")
    marker.chmod(0o600)
    return marker


def ensure_seeded_admin_awg3(*, database: Path | None = None) -> bool:
    """Compatibility no-op: AWG3.0 is retired and must never be added to sg-admin."""

    if database is not None:
        pending_marker(database).unlink(missing_ok=True)
    return False
