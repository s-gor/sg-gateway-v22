from __future__ import annotations

import os
import sqlite3
from functools import wraps
from pathlib import Path


RESTORE_CONTEXT_ENV = "SG_GATEWAY_CLIENTS_KEYS_RESTORE"


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


def _restore_readiness_issue(runtime, settings: dict) -> str:
    """Return only destination-readiness failures that are safe to defer.

    Credential/schema validation happens in runtime._load() before this helper.
    Ordinary client apply does not set RESTORE_CONTEXT_ENV and therefore keeps
    the established strict NaiveProxy transaction semantics.
    """

    if os.environ.get(RESTORE_CONTEXT_ENV) != "1":
        return ""

    domain = str(settings.get("domain") or "").strip()
    if not domain:
        return "NaiveProxy connection is not configured"

    try:
        port = int(settings.get("port") or 0)
    except (TypeError, ValueError):
        return ""
    if not 1 <= port <= 65535:
        return ""

    binary = Path(getattr(runtime, "BINARY", "/opt/sg-gateway/naiveproxy/bin/caddy"))
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return "NaiveProxy runtime is not installed"

    certificate = Path(
        str(settings.get("certificate_path") or "")
        or f"/etc/letsencrypt/live/{domain}/fullchain.pem"
    )
    private_key = Path(
        str(settings.get("private_key_path") or "")
        or f"/etc/letsencrypt/live/{domain}/privkey.pem"
    )
    if not certificate.is_file() or not private_key.is_file():
        return "NaiveProxy TLS certificate is not ready"

    return ""


def _deferred_result(base: dict, settings: dict, credential_ids: list[int], reason: str) -> dict:
    engine = {
        "engine": "naiveproxy",
        "ok": False,
        "deferred": True,
        "message": f"NaiveProxy dormant: {reason}",
        "clients": 0,
        "critical": False,
        "service": "sg-gateway-naiveproxy.service",
        "port": int(settings.get("port") or 8447),
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
            readiness_issue = _restore_readiness_issue(runtime, settings)
            if readiness_issue:
                return _deferred_result(
                    base,
                    settings,
                    credential_ids,
                    readiness_issue,
                )
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
