from __future__ import annotations

import os
from functools import wraps


def install(client_runtime) -> None:
    if getattr(client_runtime, "_awg31_apply_installed", False):
        return
    original = client_runtime.apply_all_clients

    @wraps(original)
    def apply_all_clients():
        result = original()
        mode = os.getenv("SG_GATEWAY_AWG31_RESTORE_MODE", "normal")
        if mode == "legacy":
            awg31 = {"ok": True, "peers": 0, "legacy_absent": True}
        elif mode == "exact":
            from sg_hostd.awg31_runtime import activate_restored_awg31

            awg31 = activate_restored_awg31(
                enabled=os.getenv("SG_GATEWAY_AWG31_RESTORE_ENABLED", "1") == "1",
                active=os.getenv("SG_GATEWAY_AWG31_RESTORE_ACTIVE", "1") == "1",
            )
        else:
            from sg_hostd.awg31_runtime import apply_awg31

            awg31 = apply_awg31()
        result.setdefault("engines", []).append(
            {
                "engine": "amneziawg31",
                "ok": bool(awg31.get("ok")),
                "message": (
                    "AWG31 absent in legacy backup"
                    if mode == "legacy"
                    else "AWG31 restored byte-for-byte"
                    if mode == "exact"
                    else "AWG31 applied"
                ),
                "clients": int(awg31.get("peers", 0)),
                "critical": True,
            }
        )
        result["ok"] = bool(result.get("ok")) and bool(awg31.get("ok"))
        return result

    client_runtime.apply_all_clients = apply_all_clients
    client_runtime._awg31_apply_installed = True
