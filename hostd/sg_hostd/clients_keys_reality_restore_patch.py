from __future__ import annotations

import json
import sqlite3
from functools import wraps
from pathlib import Path
from types import ModuleType

from sg_hostd import clients_keys_tls_backup_patch as tls_backup_patch


def _apply_restored_xray_profiles_required(full: ModuleType, protocol_policy: dict) -> dict:
    """Reconcile destination Reality profiles after temporary restore policy exits."""

    settings = protocol_policy.get("settings") if isinstance(protocol_policy, dict) else {}
    profiles = protocol_policy.get("xray_profiles") if isinstance(protocol_policy, dict) else []
    if isinstance(settings, dict) and settings.get("xray") is False:
        return {"ok": True, "skipped": True, "reason": "xray-disabled"}

    enabled_profiles = {str(item) for item in (profiles or [])}
    if not ({"reality_tcp", "xhttp_reality"} & enabled_profiles):
        return {"ok": True, "skipped": True, "reason": "reality-disabled"}

    python = Path("/opt/sg-gateway/.venv/bin/python")
    if not python.is_file():
        return {
            "ok": False,
            "deferred": True,
            "error": "SG-Gateway venv Python is missing",
        }

    code = (
        "import json,sys; "
        "from sg_hostd.client_runtime import apply_xray_runtime; "
        "r=apply_xray_runtime(force_profiles=True); "
        "print(json.dumps(r,ensure_ascii=False,default=str)); "
        "sys.exit(0 if r.get('ok') else 1)"
    )
    runtime_env = dict(full._runtime_subprocess_env())
    runtime_env["SG_GATEWAY_CLIENTS_KEYS_RESTORE"] = "1"
    result = full._probe(
        [str(python), "-c", code],
        timeout=180,
        env=runtime_env,
    )
    output = (result.stdout or result.stderr or "").strip()
    payload: dict = {}
    if output:
        try:
            decoded = json.loads(output)
            if isinstance(decoded, dict):
                payload = decoded
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if result.returncode != 0 or payload.get("ok") is False:
        return {
            "ok": False,
            "deferred": True,
            "error": output[-3200:] or "Xray Reality post-restore reconcile deferred",
        }
    payload.setdefault("ok", True)
    payload["deferred"] = False
    return payload


def _destination_protocol_policy(database_path: Path) -> dict:
    database = sqlite3.connect(database_path, timeout=15)
    try:
        settings, xray_profiles = tls_backup_patch._connection_policy(database)
    finally:
        database.close()
    return {
        "settings": settings,
        "xray_profiles": sorted(xray_profiles),
    }


def install(portable: ModuleType, full: ModuleType) -> None:
    if getattr(portable, "_reality_restore_runtime_v1_installed", False):
        return

    original = portable._restore_clients_keys

    @wraps(original)
    def restored(full_module: ModuleType, hard: ModuleType) -> dict:
        result = original(full_module, hard)
        live_database = full_module._data_dir() / "sg-gateway.sqlite"
        policy = _destination_protocol_policy(live_database)
        xray_result = _apply_restored_xray_profiles_required(full_module, policy)

        result["xray_post_restore_reconciled"] = bool(xray_result.get("ok"))
        if xray_result.get("ok"):
            if not xray_result.get("skipped"):
                result["xray_active"] = True
            return result

        result["client_runtime_deferred"] = True
        engines = {
            str(item).strip().lower()
            for item in result.get("client_runtime_deferred_engines", [])
            if str(item).strip()
        }
        engines.add("xray")
        result["client_runtime_deferred_engines"] = sorted(engines)
        result["xray_post_restore_error"] = str(
            xray_result.get("error") or "Xray Reality post-restore reconcile deferred"
        )
        return result

    portable._restore_clients_keys = restored
    portable._apply_restored_xray_profiles_required = _apply_restored_xray_profiles_required
    portable._reality_restore_runtime_v1_installed = True
