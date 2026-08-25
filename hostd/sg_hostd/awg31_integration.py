from __future__ import annotations

from functools import wraps


def install(client_runtime) -> None:
    if getattr(client_runtime, "_awg31_apply_installed", False):
        return
    original = client_runtime.apply_all_clients

    @wraps(original)
    def apply_all_clients():
        result = original()
        from sg_hostd.awg31_runtime import apply_awg31

        awg31 = apply_awg31()
        result.setdefault("engines", []).append(
            {
                "engine": "amneziawg31",
                "ok": bool(awg31.get("ok")),
                "message": "AWG31 applied",
                "clients": int(awg31.get("peers", 0)),
                "critical": True,
            }
        )
        result["ok"] = bool(result.get("ok")) and bool(awg31.get("ok"))
        return result

    client_runtime.apply_all_clients = apply_all_clients
    client_runtime._awg31_apply_installed = True
