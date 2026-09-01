from __future__ import annotations

from functools import wraps


def _sync_if_configured() -> None:
    from sg_hostd import naiveproxy_runtime

    try:
        settings, users, _ = naiveproxy_runtime._load()
    except Exception:
        return
    if not str(settings.get("domain") or "").strip() and not users:
        return
    naiveproxy_runtime.sync()


def install(full, data, operations) -> None:
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

    original_restore = full.restore_uploaded_full_backup

    @wraps(original_restore)
    def restore(*args, **kwargs):
        result = original_restore(*args, **kwargs)
        _sync_if_configured()
        return result

    full.restore_uploaded_full_backup = restore
    install._installed = True
