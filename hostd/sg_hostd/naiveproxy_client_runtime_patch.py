from __future__ import annotations

import sqlite3
from functools import wraps


def _profile_present(runtime) -> bool:
    database = sqlite3.connect(runtime.DB_PATH)
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


def install(client_runtime, commands, runtime) -> None:
    if getattr(client_runtime, "_naiveproxy_apply_installed", False):
        return

    original = client_runtime.apply_all_clients

    @wraps(original)
    def apply_all_clients() -> dict:
        base = original()
        if not isinstance(base, dict):
            raise client_runtime.ClientRuntimeError(
                "Client runtime returned an invalid result"
            )
        if not base.get("ok"):
            return base
        if not _profile_present(runtime):
            return base

        try:
            settings, users, credential_ids = runtime._load()
            configured = bool(str(settings.get("domain") or "").strip())
            if not configured and not credential_ids:
                return base
            payload = runtime.sync()
            if not payload.get("ok", True):
                raise RuntimeError("NaiveProxy runtime apply failed")
        except Exception as exc:
            redact = getattr(runtime, "_redact", str)
            raise client_runtime.ClientRuntimeError(
                f"NaiveProxy: {redact(str(exc))}"
            ) from exc

        engine = {
            "engine": "naiveproxy",
            "ok": True,
            "message": "NaiveProxy применён; клиентов: "
            + str(int(payload.get("users") or len(users))),
            "clients": int(payload.get("users") or len(users)),
            "critical": True,
            "service": str(
                payload.get("service") or "sg-gateway-naiveproxy.service"
            ),
            "port": int(payload.get("port") or settings.get("port") or 8447),
            "credentials": len(credential_ids),
        }
        result = dict(base)
        result["engines"] = [*list(base.get("engines") or []), engine]
        base_message = str(base.get("message") or "").strip()
        result["message"] = (
            base_message + "; " + engine["message"]
            if base_message
            else engine["message"]
        )
        result["ok"] = True
        return result

    client_runtime.apply_all_clients = apply_all_clients
    commands.apply_all_clients = apply_all_clients
    client_runtime._naiveproxy_apply_installed = True
