from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrivilegedResult:
    status: str
    message: str
    payload: dict


_ACTIONS: dict[str, tuple[str, str, int]] = {
    "geofiles.check": ("app.routing.geofiles_helper", "check", 240),
    "geofiles.apply": ("app.routing.geofiles_helper", "apply", 240),
    "geofiles.rollback": ("app.routing.geofiles_helper", "rollback", 240),
    "routing.apply": ("app.routing.templates_helper", "apply", 180),
    "routing.rollback": ("app.routing.templates_helper", "rollback", 180),
    "warp.install": ("app.routing.warp_helper", "install", 600),
    "warp.recreate": ("app.routing.warp_helper", "recreate", 600),
    "warp.enable": ("app.routing.warp_helper", "enable", 240),
    "warp.disable": ("app.routing.warp_helper", "disable", 240),
    "warp.remove": ("app.routing.warp_helper", "remove", 240),
    "warp.test": ("app.routing.warp_helper", "test", 180),
    "warp.export_json": ("app.routing.warp_helper", "export-json", 60),
}

_PYTHON = Path("/opt/sg-gateway/.venv/bin/python")
_FALLBACK = Path("/usr/bin/python3")


def execute_privileged_action(command: str) -> PrivilegedResult:
    spec = _ACTIONS.get(command)
    if spec is None:
        return PrivilegedResult(
            status="error",
            message="Privileged action is not allowed",
            payload={},
        )

    module, action, timeout = spec
    python = _PYTHON if _PYTHON.is_file() else _FALLBACK
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
            [str(python), "-m", module, action],
            cwd="/opt/sg-gateway",
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PrivilegedResult(
            status="error",
            message=f"{command}: превышено время ожидания",
            payload={},
        )
    except OSError as exc:
        return PrivilegedResult(
            status="error",
            message=f"{command}: {exc}",
            payload={},
        )

    raw = (result.stdout or result.stderr or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "message": raw or f"{command} failed",
        }

    ok = result.returncode == 0 and bool(payload.get("ok"))
    message = str(
        payload.get("message")
        or (f"{command} completed" if ok else f"{command} failed")
    )
    details = {
        key: value
        for key, value in payload.items()
        if key not in {"ok", "message"}
    }
    details["returncode"] = result.returncode

    return PrivilegedResult(
        status="ok" if ok else "error",
        message=message,
        payload=details,
    )
