from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sg_hostd import full_backup_runtime as full_backup


VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"


def _verify_archive(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="verify-", dir=full_backup._work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = full_backup._extract_archive(archive, temp)
        payload = temp / "payload"
        db_path = payload / full_backup._data_dir().relative_to("/") / "sg-gateway.sqlite"
        if not db_path.is_file():
            raise RuntimeError("Backup does not contain the SG-Gateway database")

        database_size = db_path.stat().st_size
        database = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
        try:
            row = database.execute("PRAGMA integrity_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise RuntimeError("Uploaded SQLite database is damaged")
            table_count = int(
                database.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
            )
        finally:
            database.close()

        if table_count <= 0:
            raise RuntimeError("SG-Gateway database contains no application tables")

        return {
            "verified": True,
            "format": str(manifest.get("format") or ""),
            "format_version": int(manifest.get("format_version") or 0),
            "source_version": str(manifest.get("source_version") or "unknown"),
            "created_at": str(manifest.get("created_at") or ""),
            "size_bytes": archive.stat().st_size,
            "sha256": full_backup._sha256(archive),
            "database_size_bytes": database_size,
            "database_tables": table_count,
            "contains_letsencrypt": bool(manifest.get("contains_letsencrypt")),
            "contains_letsencrypt_certificates": bool(manifest.get("contains_letsencrypt_certificates")),
            "certificate_domains": list(manifest.get("certificate_domains") or []),
            "components": len(list(manifest.get("components") or [])),
            "checks": {
                "gzip_tar": "ok",
                "safe_paths": "ok",
                "manifest": "ok",
                "sqlite_integrity": "ok",
            },
        }


def verify_uploaded_full_backup() -> dict:
    """Validate an uploaded .sgbackup without modifying live server state."""
    full_backup._ensure_dirs()
    archive = full_backup._backup_dir() / VERIFY_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded .sgbackup file for verification not found")

    try:
        return _verify_archive(archive)
    finally:
        archive.unlink(missing_ok=True)
