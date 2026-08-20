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


FORMAT = "sg-gateway-clients-keys-backup"
FORMAT_VERSION = 1
PREFIX = "SG-Gateway-CLIENTS"
VERIFY_UPLOAD_NAME = "verify-upload.sgbackup"
VERIFIED_UPLOAD_NAME = "verified-upload.sgbackup"
RESTORE_UPLOAD_NAME = "restore-upload.sgbackup"
CANONICAL_DATA_DIR = Path("/var/lib/sg-gateway")

CLIENT_TABLES = (
    "clients",
    "devices",
    "device_credentials",
    "sg_subscription_tokens",
    "router_subscription_tokens",
)
REQUIRED_CLIENT_TABLES = ("clients", "devices", "device_credentials")
DELETE_ORDER = (
    "sg_subscription_tokens",
    "router_subscription_tokens",
    "device_credentials",
    "client_deployments",
    "devices",
    "clients",
)
INSERT_ORDER = (
    "clients",
    "devices",
    "device_credentials",
    "sg_subscription_tokens",
    "router_subscription_tokens",
)

# Fields copied from connection/server state when a credential was originally
# created.  They are deliberately removed from the portable archive.  Client
# identity/secrets remain untouched and are rebound to the destination server
# during promotion to the established Full Restore transaction.
_SERVER_FIELDS = {
    "amneziawg": {
        "dns",
        "server_public_key",
        "endpoint",
        "allowed_ips",
        "persistent_keepalive",
    },
    "amneziawg3": {
        "dns",
        "server_public_key",
        "endpoint",
        "allowed_ips",
        "persistent_keepalive",
    },
    "xray": {
        "host",
        "port",
        "security",
        "type",
        "flow",
        "fingerprint",
        "server_name",
        "public_key",
        "short_id",
        "vless_encryption",
    },
    "anytls": {"host", "port", "server_name"},
    "tuic": {"host", "port", "server_name"},
}


def _data_backup_dir() -> Path:
    root = full._data_dir() / "backups" / "data"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    if os.geteuid() == 0:
        uid, gid = full._panel_ids()
        os.chown(root, uid, gid)
    return root


def _work_dir() -> Path:
    root = full._data_dir() / "data-backup-work"
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _archive_name(prefix: str = PREFIX) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{prefix}-{stamp}.sgbackup"


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_names(database: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _sanitize_credential(engine: str, raw: str | None) -> str | None:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw
    if not isinstance(payload, dict):
        return raw
    for key in _SERVER_FIELDS.get(str(engine), set()):
        payload.pop(key, None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _prepare_clients_snapshot(source: Path, destination: Path) -> None:
    full._sqlite_snapshot(source, destination)
    database = sqlite3.connect(destination, timeout=15)
    try:
        database.execute("PRAGMA foreign_keys = OFF")
        tables = _table_names(database)
        missing = [name for name in REQUIRED_CLIENT_TABLES if name not in tables]
        if missing:
            raise RuntimeError(
                "SG-Gateway database is missing client tables: " + ", ".join(missing)
            )

        for table in sorted(tables - set(CLIENT_TABLES)):
            database.execute(f"DELETE FROM {_quote_ident(table)}")

        if "sqlite_sequence" in {
            str(row[0])
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }:
            placeholders = ",".join("?" for _ in CLIENT_TABLES)
            database.execute(
                f"DELETE FROM sqlite_sequence WHERE name NOT IN ({placeholders})",
                CLIENT_TABLES,
            )

        rows = database.execute(
            "SELECT id, engine, config_json FROM device_credentials ORDER BY id"
        ).fetchall()
        for row in rows:
            cleaned = _sanitize_credential(str(row[1]), row[2])
            if cleaned != row[2]:
                database.execute(
                    "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                    (cleaned, int(row[0])),
                )
        database.commit()
        # DELETE alone can leave old values in free SQLite pages. VACUUM makes
        # the archive physically contain only the client subset.
        database.execute("VACUUM")
        check = database.execute("PRAGMA integrity_check").fetchone()
        if not check or str(check[0]).lower() != "ok":
            raise RuntimeError("Client snapshot SQLite integrity_check failed")
    finally:
        database.close()


def create_data_backup_archive(
    prefix: str = PREFIX,
    *,
    source_data_dir: Path | None = None,
    source_config_dir: Path | None = None,
    source_letsencrypt_dir: Path | None = None,
    destination_dir: Path | None = None,
) -> dict:
    # source_config_dir/source_letsencrypt_dir are retained in the call
    # signature for compatibility only. Clients & Keys never archives them.
    del source_config_dir, source_letsencrypt_dir
    data_dir = Path(source_data_dir or full._data_dir())
    output_dir = Path(destination_dir or _data_backup_dir())
    output_dir.mkdir(parents=True, exist_ok=True)

    destination = output_dir / _archive_name(prefix)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="create-clients-",
        dir=_work_dir() if destination_dir is None else None,
    ) as temp_name:
        temp = Path(temp_name)
        db_snapshot = temp / "sg-gateway.sqlite"
        _prepare_clients_snapshot(data_dir / "sg-gateway.sqlite", db_snapshot)
        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-keys",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_version": full._version(),
            "contains_private_keys": True,
            "contains_letsencrypt": False,
            "contains_letsencrypt_certificates": False,
            "certificate_domains": [],
            "portable_restore": "client identities are rebound to destination server settings",
            "runtime_policy": "server settings and generated runtime are not archived",
            "excluded": [
                "connection/server settings",
                "Routing and GeoFiles",
                "WARP",
                "HTTPS and certificates",
                "runtime binaries and generated configs",
                "backup history and operation jobs",
            ],
            "client_tables": list(CLIENT_TABLES),
            "components": [str(CANONICAL_DATA_DIR / "sg-gateway.sqlite")],
        }
        manifest_path = temp / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                db_snapshot,
                arcname=f"payload/{CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite",
                recursive=False,
            )

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
        "certificates": False,
        "certificate_domains": [],
        "profile": "clients-and-keys",
    }


def _read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("format") != FORMAT
        or int(payload.get("format_version") or 0) != FORMAT_VERSION
        or payload.get("profile") != "clients-and-keys"
    ):
        raise RuntimeError("Unsupported SG-Gateway Clients & Keys backup format")
    return payload


def _extract_archive(archive: Path, target: Path) -> dict:
    with tarfile.open(archive, "r:gz") as tar:
        members = [
            member
            for member in tar.getmembers()
            if not full._is_internal_history_member(member.name)
        ]
        full._validate_members(tar, target, members)
        tar.extractall(target, members=members)
    manifest = target / "manifest.json"
    if not manifest.is_file():
        raise RuntimeError("manifest.json is missing")
    return _read_manifest(manifest)


def _verify_database(db_path: Path) -> tuple[int, int]:
    if not db_path.is_file():
        raise RuntimeError("Backup does not contain the SG-Gateway client database")
    database_size = db_path.stat().st_size
    database = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=15
    )
    try:
        row = database.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("Uploaded SQLite database is damaged")
        tables = _table_names(database)
        missing = [name for name in REQUIRED_CLIENT_TABLES if name not in tables]
        if missing:
            raise RuntimeError("Backup is missing client tables: " + ", ".join(missing))
        for table in sorted(tables - set(CLIENT_TABLES)):
            count = int(
                database.execute(
                    f"SELECT COUNT(*) FROM {_quote_ident(table)}"
                ).fetchone()[0]
            )
            if count:
                raise RuntimeError(
                    f"Clients & Keys backup unexpectedly contains server table data: {table}"
                )
        rows = database.execute(
            "SELECT engine, config_json FROM device_credentials"
        ).fetchall()
        for engine, raw in rows:
            try:
                payload = json.loads(raw or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            leaked = sorted(_SERVER_FIELDS.get(str(engine), set()) & set(payload))
            if leaked:
                raise RuntimeError(
                    f"Clients & Keys credential contains server fields for {engine}: "
                    + ", ".join(leaked)
                )
        client_table_count = len(tables & set(CLIENT_TABLES))
    finally:
        database.close()
    return database_size, client_table_count


def _verify_archive(archive: Path) -> dict:
    with tempfile.TemporaryDirectory(
        prefix="verify-clients-", dir=_work_dir()
    ) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        db_path = (
            temp
            / "payload"
            / CANONICAL_DATA_DIR.relative_to("/")
            / "sg-gateway.sqlite"
        )
        database_size, table_count = _verify_database(db_path)
        return {
            "verified": True,
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "profile": "clients-and-keys",
            "source_version": str(manifest.get("source_version") or "unknown"),
            "created_at": str(manifest.get("created_at") or ""),
            "size_bytes": archive.stat().st_size,
            "sha256": full._sha256(archive),
            "database_size_bytes": database_size,
            "database_tables": table_count,
            "contains_letsencrypt": False,
            "contains_letsencrypt_certificates": False,
            "certificate_domains": [],
            "components": 1,
            "checks": {
                "gzip_tar": "ok",
                "safe_paths": "ok",
                "manifest": "ok",
                "sqlite_integrity": "ok",
                "server_state_excluded": "ok",
            },
        }


def verify_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / VERIFY_UPLOAD_NAME
    verified = directory / VERIFIED_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError(
            "Uploaded Clients & Keys .sgbackup file for verification not found"
        )
    verified.unlink(missing_ok=True)
    try:
        payload = _verify_archive(archive)
        archive.replace(verified)
        return payload
    finally:
        archive.unlink(missing_ok=True)


def _copy_table(source: sqlite3.Connection, destination: sqlite3.Connection, table: str) -> None:
    source_tables = _table_names(source)
    if table not in source_tables:
        return
    destination_tables = _table_names(destination)
    if table not in destination_tables:
        row = source.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        sql = str(row[0] or "") if row else ""
        if not sql:
            raise RuntimeError(f"Cannot create destination client table: {table}")
        destination.execute(sql)

    source_columns = [
        str(row[1]) for row in source.execute(f"PRAGMA table_info({_quote_ident(table)})")
    ]
    destination_columns = {
        str(row[1]) for row in destination.execute(f"PRAGMA table_info({_quote_ident(table)})")
    }
    columns = [name for name in source_columns if name in destination_columns]
    if not columns:
        return
    quoted = ", ".join(_quote_ident(name) for name in columns)
    placeholders = ", ".join("?" for _ in columns)
    rows = source.execute(
        f"SELECT {quoted} FROM {_quote_ident(table)}"
    ).fetchall()
    if rows:
        destination.executemany(
            f"INSERT INTO {_quote_ident(table)} ({quoted}) VALUES ({placeholders})",
            rows,
        )


def _connection_setting(database: sqlite3.Connection, engine: str) -> tuple[str, int, dict]:
    if "connection_settings" not in _table_names(database):
        return "", 0, {}
    row = database.execute(
        "SELECT host, port, config_json FROM connection_settings WHERE engine = ?",
        (engine,),
    ).fetchone()
    if row is None:
        return "", 0, {}
    try:
        config = json.loads(row[2] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        config = {}
    return str(row[0] or ""), int(row[1] or 0), config if isinstance(config, dict) else {}


def _endpoint(host: str, port: int) -> str:
    clean = str(host or "").strip()
    if ":" in clean and not clean.startswith("["):
        clean = f"[{clean}]"
    return f"{clean}:{int(port)}" if clean and port else clean


def _rebind_client_credentials(database: sqlite3.Connection) -> None:
    awg_host, awg_port, awg = _connection_setting(database, "amneziawg")
    awg3_host, awg3_port, awg3 = _connection_setting(database, "amneziawg3")
    xray_host, xray_port, xray = _connection_setting(database, "xray")
    public_host = str(full._destination_public_address() or xray_host or awg_host or "").strip()
    tls_state = full._restored_tls_state()
    tls_domain = str(tls_state.get("domain") or "").strip()

    rows = database.execute(
        "SELECT id, engine, config_json FROM device_credentials ORDER BY id"
    ).fetchall()
    for row_id, engine_raw, raw in rows:
        engine = str(engine_raw)
        try:
            payload = json.loads(raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        if engine == "amneziawg":
            payload.update(
                {
                    "dns": awg.get("dns", "1.1.1.1"),
                    "server_public_key": awg.get("server_public_key", ""),
                    "endpoint": _endpoint(awg_host or public_host, awg_port),
                    "allowed_ips": awg.get("allowed_ips", "0.0.0.0/0, ::/0"),
                    "persistent_keepalive": awg.get("persistent_keepalive", 25),
                }
            )
        elif engine == "amneziawg3":
            payload.update(
                {
                    "dns": awg3.get("dns", "1.1.1.1"),
                    "server_public_key": awg3.get("server_public_key", ""),
                    "endpoint": _endpoint(awg3_host or public_host, awg3_port),
                    "allowed_ips": awg3.get("allowed_ips", "0.0.0.0/0, ::/0"),
                    "persistent_keepalive": awg3.get("persistent_keepalive", "25-35"),
                    "generation": 3,
                }
            )
        elif engine == "xray":
            payload["host"] = xray_host or public_host
            payload["port"] = xray_port
            for key in (
                "security",
                "type",
                "flow",
                "fingerprint",
                "server_name",
                "public_key",
                "short_id",
                "vless_encryption",
            ):
                if key in xray:
                    payload[key] = xray[key]
        elif engine == "anytls":
            payload["host"] = public_host
            payload["port"] = 9443
            payload["server_name"] = tls_domain
        elif engine == "tuic":
            payload["host"] = public_host
            payload["port"] = 10443
            payload["server_name"] = tls_domain

        database.execute(
            "UPDATE device_credentials SET config_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(row_id)),
        )


def _build_merged_destination_database(source_clients: Path, destination: Path) -> None:
    current = full._data_dir() / "sg-gateway.sqlite"
    full._sqlite_snapshot(current, destination)
    source = sqlite3.connect(
        f"file:{source_clients.as_posix()}?mode=ro", uri=True, timeout=15
    )
    merged = sqlite3.connect(destination, timeout=15)
    try:
        merged.execute("PRAGMA foreign_keys = OFF")
        for table in DELETE_ORDER:
            if table in _table_names(merged):
                merged.execute(f"DELETE FROM {_quote_ident(table)}")
        for table in INSERT_ORDER:
            _copy_table(source, merged, table)
        _rebind_client_credentials(merged)
        merged.commit()
        row = merged.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("Merged client database failed SQLite integrity_check")
    finally:
        merged.close()
        source.close()


def promote_uploaded_data_backup() -> dict:
    directory = _data_backup_dir()
    archive = directory / RESTORE_UPLOAD_NAME
    if not archive.is_file():
        raise RuntimeError("Uploaded Clients & Keys .sgbackup file for restore not found")

    with tempfile.TemporaryDirectory(
        prefix="promote-clients-", dir=_work_dir()
    ) as temp_name:
        temp = Path(temp_name)
        manifest = _extract_archive(archive, temp)
        source_db = (
            temp
            / "payload"
            / CANONICAL_DATA_DIR.relative_to("/")
            / "sg-gateway.sqlite"
        )
        _verify_database(source_db)

        merged_db = temp / "merged-sg-gateway.sqlite"
        _build_merged_destination_database(source_db, merged_db)
        contract = assert_runtime_contract(
            database_path=merged_db,
            strict_optional=True,
            include_all_critical=True,
        )

        full._ensure_dirs()
        destination = full._backup_dir() / full.RESTORE_UPLOAD_NAME
        temporary = destination.with_name(f".{destination.name}.clients-promote.tmp")
        destination.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)

        full_manifest = {
            "format": full.FORMAT,
            "format_version": full.FORMAT_VERSION,
            "created_at": str(
                manifest.get("created_at") or datetime.now(timezone.utc).isoformat()
            ),
            "source_version": str(manifest.get("source_version") or "unknown"),
            "contains_private_keys": True,
            "contains_letsencrypt": False,
            "contains_letsencrypt_certificates": False,
            "certificate_domains": [],
            "portable_restore": "destination server settings are preserved",
            "excluded_history": ["security/backups", "security/jobs"],
            "components": [str(CANONICAL_DATA_DIR / "sg-gateway.sqlite")],
            "data_profile": True,
            "clients_keys_profile": True,
            "promoted_from": FORMAT,
        }
        manifest_path = temp / "promoted-full-manifest.json"
        manifest_path.write_text(
            json.dumps(full_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with tarfile.open(temporary, "w:gz", dereference=False) as tar:
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
            tar.add(
                merged_db,
                arcname=f"payload/{CANONICAL_DATA_DIR.relative_to('/')}/sg-gateway.sqlite",
                recursive=False,
            )

        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        archive.unlink(missing_ok=True)
        return {
            "promoted": True,
            "source_version": str(manifest.get("source_version") or "unknown"),
            "runtime_contract": contract,
            "full_restore_upload": str(destination),
            "profile": "clients-and-keys",
        }
