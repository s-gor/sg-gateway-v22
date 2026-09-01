from __future__ import annotations

import json
from functools import wraps

from app.naiveproxy.runtime import DEFAULT_PORT, NaiveProxySettings, NaiveProxyUser, build_client_uri, generate_user

DEFAULT_CONNECTION = {
    "host": "",
    "port": DEFAULT_PORT,
    "config_json": json.dumps(
        {
            "domain": "",
            "certificate_path": "",
            "private_key_path": "",
            "country_code": "unknown",
        },
        ensure_ascii=False,
        sort_keys=True,
    ),
}


def _restore_connection_settings(previous) -> bool:
    from app.connections.settings import update_connection_settings

    return update_connection_settings(
        "naiveproxy",
        previous.host,
        previous.port,
        dict(previous.config),
    )


def _request_sync() -> None:
    bootstrap_previous = None
    bootstrap_changed = False
    try:
        from app.db import connect
        with connect() as connection:
            setting = connection.execute(
                "SELECT host FROM connection_settings WHERE engine = 'naiveproxy'"
            ).fetchone()
            assigned = connection.execute(
                "SELECT COUNT(*) AS total FROM device_credentials WHERE engine = 'naiveproxy'"
            ).fetchone()
        assigned_total = int(assigned["total"] or 0)
        configured_host = str(setting["host"] or "").strip() if setting else ""
        if not configured_host and assigned_total == 0:
            return
        if not configured_host:
            from app.security.tls import overview as tls_overview
            from app.connections.settings import (
                get_connection_settings,
                update_connection_settings,
            )

            tls = tls_overview()
            domain = str(tls.get("domain") or "").strip()
            if not tls.get("https_ready") or not domain:
                from app.maintenance.operations import log_operation
                log_operation(
                    "naiveproxy.sync",
                    "runtime:naiveproxy",
                    "NaiveProxy ожидает настроенный HTTPS в Security",
                    status="warning",
                )
                return
            bootstrap_previous = get_connection_settings("naiveproxy")
            updated = update_connection_settings(
                "naiveproxy",
                domain,
                DEFAULT_PORT,
                {
                    "domain": domain,
                    "certificate_path": str(tls.get("certificate_path") or ""),
                    "private_key_path": f"/etc/letsencrypt/live/{domain}/privkey.pem",
                },
            )
            if not updated:
                raise RuntimeError("Не удалось сохранить настройки NaiveProxy")
            bootstrap_changed = True

        from app.hostd.client import run_hostd_command
        from app.maintenance.operations import log_operation

        result = run_hostd_command("naiveproxy.sync", timeout=60)
        if result.status != "ok":
            rollback_note = ""
            if bootstrap_changed and bootstrap_previous is not None:
                restored = _restore_connection_settings(bootstrap_previous)
                rollback_note = (
                    "; bootstrap-настройки восстановлены"
                    if restored
                    else "; восстановить bootstrap-настройки не удалось"
                )
            log_operation(
                "naiveproxy.sync",
                "runtime:naiveproxy",
                (result.message or "NaiveProxy sync failed") + rollback_note,
                status="error",
            )
    except Exception as exc:
        rollback_note = ""
        if bootstrap_changed and bootstrap_previous is not None:
            try:
                restored = _restore_connection_settings(bootstrap_previous)
            except Exception:
                restored = False
            rollback_note = (
                "; bootstrap-настройки восстановлены"
                if restored
                else "; восстановить bootstrap-настройки не удалось"
            )
        try:
            from app.maintenance.operations import log_operation
            log_operation(
                "naiveproxy.sync",
                "runtime:naiveproxy",
                str(exc) + rollback_note,
                status="error",
            )
        except Exception:
            pass


def reserved_ports() -> dict[int, str]:
    from app.db import connect

    result: dict[int, str] = {}
    with connect() as connection:
        rows = connection.execute(
            "SELECT engine, port, config_json FROM connection_settings WHERE engine != 'naiveproxy'"
        ).fetchall()
    for row in rows:
        engine = str(row["engine"])
        try:
            port = int(row["port"])
        except (TypeError, ValueError):
            port = 0
        if 1 <= port <= 65535:
            result[port] = engine
        try:
            config = json.loads(row["config_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if isinstance(config, dict):
            for key, value in config.items():
                if not str(key).endswith("_port"):
                    continue
                try:
                    candidate = int(value)
                except (TypeError, ValueError):
                    continue
                if 1 <= candidate <= 65535:
                    result[candidate] = f"{engine}.{key}"
    return result


def _patch_mutations(repository) -> None:
    names = (
        "create_client",
        "create_device",
        "update_client",
        "update_device",
        "set_client_enabled",
        "set_device_enabled",
        "delete_client",
        "delete_device",
        "restore_client_snapshot",
    )
    for name in names:
        original = getattr(repository, name, None)
        if original is None or getattr(original, "_naiveproxy_sync_wrapper", False):
            continue

        @wraps(original)
        def wrapped(*args, __original=original, **kwargs):
            result = __original(*args, **kwargs)
            if result is not False:
                _request_sync()
            return result

        wrapped._naiveproxy_sync_wrapper = True
        setattr(repository, name, wrapped)


def install() -> None:
    if getattr(install, "_installed", False):
        return

    from app import db
    from app.engines import provisioning

    db.DEFAULT_CONNECTIONS.setdefault("naiveproxy", dict(DEFAULT_CONNECTION))
    original_builder = provisioning.build_engine_config

    def build_engine_config(engine: str, access_id: int, access_name: str):
        if engine != "naiveproxy":
            return original_builder(engine, access_id, access_name)
        settings = provisioning.get_connection_settings("naiveproxy")
        user = generate_user(f"sg-{access_id}", client_id=str(access_id))
        domain = str(settings.host or settings.config.get("domain") or "").strip()
        payload = {
            "client_name": access_name,
            "device_id": access_id,
            "username": user.username,
            "password": user.password,
            "host": domain,
            "port": int(settings.port or DEFAULT_PORT),
            "scheme": "naive+https",
        }
        return user.username, json.dumps(payload, ensure_ascii=False, sort_keys=True)

    provisioning.build_engine_config = build_engine_config

    from app.clients import repository

    repository.build_engine_config = build_engine_config
    if "naiveproxy" not in repository.SUPPORTED_ENGINES:
        repository.SUPPORTED_ENGINES += ("naiveproxy",)
    if "naiveproxy" not in repository.RUNTIME_ENGINES:
        repository.RUNTIME_ENGINES += ("naiveproxy",)
    repository.TLS_PROTOCOL_TOKENS.add("naiveproxy")
    _patch_mutations(repository)

    from app.clients import exports

    original_protocol_engine = exports.protocol_engine
    original_build_export = exports.build_protocol_export
    original_protocol_ready = exports.protocol_ready

    def build_naiveproxy_link(client, device=None):
        config = exports._deployment_config(client, "naiveproxy", device)
        settings = provisioning.get_connection_settings("naiveproxy")
        domain = str(settings.host or settings.config.get("domain") or config.get("host") or "").strip()
        user = NaiveProxyUser(
            username=str(config.get("username") or ""),
            password=str(config.get("password") or ""),
            enabled=True,
            client_id=str(config.get("device_id") or ""),
        )
        body = build_client_uri(
            NaiveProxySettings(domain=domain, port=int(settings.port or DEFAULT_PORT)),
            user,
            f"{exports._label(client, device)} · NaiveProxy",
        )
        return exports.ClientExport(
            filename=f"sg-gateway-{exports._slug(client, device)}-naiveproxy.txt",
            media_type="text/plain; charset=utf-8",
            body=body,
        )

    def protocol_engine(kind: str) -> str:
        return "naiveproxy" if kind == "naiveproxy" else original_protocol_engine(kind)

    def build_protocol_export(client, kind: str, device=None):
        if kind == "naiveproxy":
            return build_naiveproxy_link(client, device)
        return original_build_export(client, kind, device)

    def protocol_ready(client, kind: str, device=None) -> bool:
        if kind != "naiveproxy":
            return original_protocol_ready(client, kind, device)
        try:
            return bool(
                exports.is_export_ready(client, "naiveproxy", device)
                and exports.tls_overview().get("https_ready")
                and build_naiveproxy_link(client, device).body
            )
        except Exception:
            return False

    exports.build_naiveproxy_link = build_naiveproxy_link
    exports.protocol_engine = protocol_engine
    exports.build_protocol_export = build_protocol_export
    exports.protocol_ready = protocol_ready

    from app.clients import sg_subscription

    spec = ("naiveproxy", "naiveproxy", "naiveproxy", "NaiveProxy", "naiveproxy", "uri")
    if spec not in sg_subscription._PROFILE_SPECS:
        sg_subscription._PROFILE_SPECS += (spec,)

    db.init_db()
    install._installed = True
