from __future__ import annotations

from app.hostd.client import run_hostd_command


class ClientWorkflowError(RuntimeError):
    pass


def apply_clients_runtime() -> dict:
    result = run_hostd_command("clients.apply", timeout=300)
    payload = dict(result.payload)
    payload.setdefault("message", result.message)
    payload.setdefault("ok", result.status == "ok")
    if result.status != "ok":
        raise ClientWorkflowError(
            result.message or "Не удалось применить клиентские конфигурации"
        )
    return payload
