from __future__ import annotations

import sqlite3
from functools import wraps


def _profile_present() -> bool:
    from sg_hostd import naiveproxy_runtime

    database = sqlite3.connect(naiveproxy_runtime.DB_PATH)
    try:
        tables = {
            str(row[0])
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        settings = 0
        credentials = 0
        if "connection_settings" in tables:
            settings = int(
                database.execute(
                    "SELECT COUNT(*) FROM connection_settings WHERE engine = 'naiveproxy'"
                ).fetchone()[0]
            )
        if "device_credentials" in tables:
            credentials = int(
                database.execute(
                    "SELECT COUNT(*) FROM device_credentials WHERE engine = 'naiveproxy'"
                ).fetchone()[0]
            )
        return bool(settings or credentials)
    finally:
        database.close()


def _sync_if_configured() -> None:
    from sg_hostd import naiveproxy_runtime

    if not _profile_present():
        return
    settings, users, _ = naiveproxy_runtime._load()
    if not str(settings.get("domain") or "").strip() and not users:
        return
    naiveproxy_runtime.sync()


def install(_full, data, operations) -> None:
    if getattr(install, "_installed", False):
        return

    data._SERVER_FIELDS.setdefault(
        "naiveproxy", {"host", "port", "domain", "certificate_path", "private_key_path"}
    )

    original_rebind = data._rebind_client_credentials

    @wraps(original_rebind)
    def rebind(database):
        original_rebind(database)
        host, port, config = data._connection_setting(database, "naiveproxy")
        rows = database.execute(
            "SELECT id, config_json FROM device_credentials WHERE engine = 'naiveproxy'"
        ).fetchall()
        import json

        for row_id, raw in rows:
            try:
                payload = json.loads(raw or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            payload["host"] = str(host or config.get("domain") or "")
            payload["port"] = int(port or 8447)
            database.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(row_id)),
            )

    data._rebind_client_credentials = rebind

    original_tls = operations.run_tls_maintenance

    @wraps(original_tls)
    def tls_maintenance(action: str):
        result = original_tls(action)
        _sync_if_configured()
        return result

    operations.run_tls_maintenance = tls_maintenance
    install._installed = True
