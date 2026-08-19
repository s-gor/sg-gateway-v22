from __future__ import annotations

from app.hostd.client import run_hostd_command


def runtime_engine_state(engine: str) -> dict:
    """Return safe UI readiness for one runtime engine.

    Unknown hostd state is intentionally non-blocking. Credential provisioning
    remains the authoritative fail-closed preflight before new secrets are made.
    """

    wanted = str(engine or "").strip().lower()
    if not wanted:
        return {"known": False, "ready": True, "missing": [], "message": ""}

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
        }

    return {
        "known": False,
        "ready": True,
        "missing": [],
        "message": str(result.message or ""),
    }
