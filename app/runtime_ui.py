from __future__ import annotations

from app.hostd.client import run_hostd_command


def _deployment_state(item: dict) -> dict:
    raw = item.get("deployment")
    if not isinstance(raw, dict):
        return {}
    missing = raw.get("missing")
    if not isinstance(missing, list):
        missing = []
    return {
        "required": bool(raw.get("required")),
        "ready": bool(raw.get("ready")),
        "missing": [str(value) for value in missing if str(value).strip()],
        "config_ready": bool(raw.get("config_ready")),
        "service_active": bool(raw.get("service_active")),
    }


def runtime_engine_state(engine: str) -> dict:
    """Return safe UI readiness for one runtime engine.

    Unknown hostd state is intentionally non-blocking. Credential provisioning
    remains the authoritative fail-closed preflight before new secrets are made.
    """

    wanted = str(engine or "").strip().lower()
    if not wanted:
        return {"known": False, "ready": True, "missing": [], "message": "", "deployment": {}}

    result = run_hostd_command("runtime.contract", timeout=2)
    payload = dict(result.payload or {})
    checks = payload.get("checks")
    if not isinstance(checks, list):
        checks = []

    for item in checks:
        if not isinstance(item, dict):
            continue
        if str(item.get("engine") or "").strip().lower() != wanted:
            continue
        missing = item.get("missing")
        if not isinstance(missing, list):
            missing = []
        return {
            "known": True,
            "ready": bool(item.get("ready")),
            "missing": [str(value) for value in missing if str(value).strip()],
            "message": str(item.get("message") or result.message or ""),
            "deployment": _deployment_state(item),
        }

    return {
        "known": False,
        "ready": True,
        "missing": [],
        "message": str(result.message or ""),
        "deployment": {},
    }
