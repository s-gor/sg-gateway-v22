from __future__ import annotations

import json
import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sg_hostd import full_backup_runtime as full
from sg_hostd.runtime_contracts import assert_runtime_contract


FORMAT = "sg-gateway-data-backup"
FORMAT_VERSION = 1
PREFIX = "SG-Gateway-DATA"
VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
CANONICAL_CONFIG_DIR = Path("/etc/sg-gateway")
CANONICAL_DATA_DIR = Path("/var/lib/sg-gateway")
CANONICAL_LETSENCRYPT_DIR = Path("/etc/letsencrypt")


def _data_backup_dir() -> Path:
    root = full._data_dir() / "backups" / "data"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _work_dir() -> Path:
    root = full._data_dir() / "data-backup-work"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _archive_name(prefix: str = PREFIX) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{prefix}-{stamp}.sgbackup"


def _add_path(tar: tarfile.TarFile, source: Path, arcname: str) -> None:
    tar.add(
        source,
        arcname=arcname,
        recursive=True,
        filter=full._portable_tar_filter,
    )


def create_data_backup_archive(
    prefix: str = PREFIX,
    *,
    source_data_dir: Path | None = None,
    source_config_dir: Path | None = None,
    source_letsencrypt_dir: Path | None = None,
    destination_dir: Path | None = None,
) -> dict:
    data_dir = Path(source_data_dir or full._data_dir())
    config_dir = Path(source_config_dir or CANONICAL_CONFIG_DIR)
    letsencrypt_dir = Path(source_letsencrypt_dir or CANONICAL_LETSENCRYPT_DIR)
    output_dir = Path(destination_dir or _data_backup_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    destination = output_dir / _archive_name(prefix)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="create-", dir=_work_dir() if destination_dir is None else None) as temp_name:
        temp = Path(temp_name)
        db_snapshot = temp / "sg-gateway.sqlite"
        full._sqlite_snapshot(data_dir / "sg-gateway.sqlite", db_snapshot)

        roots: list[tuple[Path, Path]] = []
        if config_dir.exists() or config_dir.is_symlink():
            roots.append((config_dir, CANONICAL_CONFIG_DIR))
        if letsencrypt_dir.exists() or letsencrypt_dir.is_symlink():
            roots.append((letsencrypt_dir, CANONICAL_LETSENCRYPT_DIR))

        data_roots: list[tuple[Path, Path]] = []
        for name in ("security", "warp"):
            source = data_dir / name
            if source.exists() or source.is_symlink():
                data_roots.append((source, CANONICAL_DATA_DIR / name))

        certificate_domains: list[str] = []
        live = letsencrypt_dir / "live"
        if live.is_dir():
            for item in sorted(live.iterdir()):
                if item.is_dir() and (item / "fullchain.pem").is_file() and (item / "privkey.pem").is_file():
                    certificate_domains.append(item.name)

        components = [str(canonical) for _, canonical in roots]
        components.extend(str(canonical) for _, canonical in data_roots)
        components.append(str(CANONICAL_DATA_DIR / "sg-gateway.sqlite"))
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-settings",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_version": full._version(),
            "contains_private_keys": True,
            "contains_letsencrypt": letsencrypt_dir.exists(),
            "contains_letsencrypt_certificates": bool(certificate_domains),
            "certificate_domains": certificate_domains,
            "portable_restore": "destination public IP is preserved",
            "runtime_policy": "generated runtime is not archived; destination rebuilds it",
            "excluded": [
                "runtime binaries",
                "generated Xray/AWG/Mihomo/sing-box configs",
                "GeoIP cache",
                "backup history",
                "operation jobs",
            ],
            "components": components,
        }
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                db_snapshot,
                arcname=f"payload/{CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite",
                recursive=False,
            )
            for source, canonical in roots:
                _add_path(tar, source, f"payload/{canonical.relative_to('/')}")
            for source, canonical in data_roots:
                _add_path(tar, source, f"payload/{canonical.relative_to('/')}")

    os.replace(temporary, destination)
    os.chmod(destination, 0o600)
    if os.geteuid() == 0:
        uid, gid = full._panel_ids()
        os.chown(destination, uid, gid)
    return {
        "name": destination.name,
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": full._sha256(destination),
        "source_version": full._version(),
        "certificates": bool(certificate_domains),
        "certificate_domains": certificate_domains,
        "profile": "clients-and-settings",
    }


def _read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != FORMAT or int(payload.get("format_version") or 0) != FORMAT_VERSION:
        raise RuntimeError("Unsupported SG-Gateway DATA backup format")
    return payload


def _extract_archive(archive: Path, target: Path) -> dict:
    with tarfile.open(archive, "r:gz") as tar:
        members = [member for member in tar.getmembers() if not full._is_internal_history_member(member.name)]
        full._validate_members(tar, target, members)
        tar.extractall(target, members=members)
    manifest = target / "manifest.json"
    if not manifest.is_file():
        raise RuntimeError("manifest.json is missing")
    return _read_manifest(manifest)


def _verify_database(db_path: Path) -> tuple[int, int]:
    if not db_path.is_file():
        raise RuntimeError("Backup does not contain the SG-Gateway database")
    database_size = db_path.stat().st_size
    database = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15)
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
    return database_size, table_count


def _verify_archive(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="verify-data-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        db_path = temp / "payload" / CANONICAL_DATA_DIR.relative_to("/") / "sg-gateway.sqlite"
        database_size, table_count = _verify_database(db_path)
        return {
            "verified": True,
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-settings",
            "source_version": str(manifest.get("source_version") or "unknown"),
            "created_at": str(manifest.get("created_at") or ""),
            "size_bytes": archive.stat().st_size,
            "sha256": full._sha256(archive),
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


def verify_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / VERIFY_UPLOAD_NAME
    verified = directory / VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded DATA .sgbackup file for verification not found")
    verified.unlink(missing_ok=True)
    try:
        payload = _verify_archive(archive)
        archive.replace(verified)
        return payload
    finally:
        archive.unlink(missing_ok=True)


def promote_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded DATA .sgbackup file for restore not found")

    with tempfile.TemporaryDirectory(prefix="promote-data-", dir=_work_dir()) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        payload_root = temp / "payload"
        db_path = payload_root / CANONICAL_DATA_DIR.relative_to("/") / "sg-gateway.sqlite"
        _verify_database(db_path)
        contract = assert_runtime_contract(
            database_path=db_path,
            strict_optional=True,
            include_all_critical=True,
        )

        full._ensure_dirs()
        destination = full._backup_dir() / full.RESTORE_UPLOAD_NAME
        temporary = destination.with_name(f".{destination.name}.data-promote.tmp")
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)

        full_manifest = {
            "format": full.FORMAT,
            "format_version": full.FORMAT_VERSION,
            "created_at": str(manifest.get("created_at") or datetime.now(timezone.utc).isoformat()),
            "source_version": str(manifest.get("source_version") or "unknown"),
            "contains_private_keys": True,
            "contains_letsencrypt": bool(manifest.get("contains_letsencrypt")),
            "contains_letsencrypt_certificates": bool(manifest.get("contains_letsencrypt_certificates")),
            "certificate_domains": list(manifest.get("certificate_domains") or []),
            "portable_restore": "destination public IP is preserved",
            "excluded_history": ["security/backups", "security/jobs"],
            "components": list(manifest.get("components") or []),
            "data_profile": True,
            "promoted_from": FORMAT,
        }
        manifest_path = temp / "promoted-full-manifest.json"
        manifest_path.write_text(json.dumps(full_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(payload_root, arcname="payload", recursive=True, filter=full._portable_tar_filter)

        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        archive.unlink(missing_ok=True)
        return {
            "promoted": True,
            "source_version": str(manifest.get("source_version") or "unknown"),
            "runtime_contract": contract,
            "full_restore_upload": str(destination),
        }
