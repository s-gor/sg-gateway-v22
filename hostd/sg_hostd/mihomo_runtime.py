from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MihomoRuntimeResult:
    status: str
    message: str
    payload: dict


_ALLOWED_ACTIONS = {"apply", "test", "restart", "rollback"}
_PYTHON = Path("/opt/sg-gateway/.venv/bin/python")
_FALLBACK_PYTHON = Path("/usr/bin/python3")


def execute_mihomo_action(action: str) -> MihomoRuntimeResult:
    if action not in _ALLOWED_ACTIONS:
        return MihomoRuntimeResult(
            status="error",
            message="Mihomo action is not allowed",
            payload={},
        )

    python = _PYTHON if _PYTHON.is_file() else _FALLBACK_PYTHON
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": "/opt/sg-gateway",
            "SG_GATEWAY_DATA_DIR": env.get(
                "SG_GATEWAY_DATA_DIR",
                "/var/lib/sg-gateway",
            ),
            "SG_GATEWAY_LOG_DIR": env.get(
                "SG_GATEWAY_LOG_DIR",
                "/var/log/sg-gateway",
            ),
        }
    )

    try:
        result = subprocess.run(
            [str(python), "-m", "app.mihomo.helper", action],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=env,
            cwd="/opt/sg-gateway",
        )
    except subprocess.TimeoutExpired:
        return MihomoRuntimeResult(
            status="error",
            message=f"Mihomo {action}: превышено время ожидания",
            payload={},
        )
    except OSError as exc:
        return MihomoRuntimeResult(
            status="error",
            message=f"Mihomo {action}: {exc}",
            payload={},
        )

    raw = (result.stdout or result.stderr or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "message": raw or f"Mihomo {action} failed",
        }

    ok = result.returncode == 0 and bool(payload.get("ok"))
    message = str(
        payload.get("message")
        or (f"Mihomo {action} completed" if ok else f"Mihomo {action} failed")
    )
    details = {
        key: value
        for key, value in payload.items()
        if key not in {"ok", "message"}
    }
    details["returncode"] = result.returncode

    return MihomoRuntimeResult(
        status="ok" if ok else "error",
        message=message,
        payload=details,
    )
