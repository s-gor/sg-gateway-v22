from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import load_config


@dataclass(frozen=True)
class HostdResult:
    command: str
    status: str
    message: str
    payload: dict


def hostd_health() -> HostdResult:
    url = f"{load_config().hostd_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return HostdResult(
            command="hostd.health",
            status="warning",
            message=f"sg-hostd is unavailable: {exc}",
            payload={"connected": False},
        )

    return HostdResult(
        command="hostd.health",
        status=payload.get("status", "warning"),
        message="sg-hostd is reachable",
        payload={"connected": True, **payload},
    )


def run_hostd_command(
    command: str,
    timeout: float = 5,
) -> HostdResult:
    url = f"{load_config().hostd_url.rstrip('/')}/commands/{command}"
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        return HostdResult(
            command=command,
            status="error",
            message=payload.get("message", f"sg-hostd rejected command: {exc.code}"),
            payload=payload.get("payload", {}),
        )
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return HostdResult(
            command=command,
            status="warning",
            message=f"sg-hostd command unavailable: {exc}",
            payload={"connected": False},
        )

    return HostdResult(
        command=payload.get("command", command),
        status=payload.get("status", "warning"),
        message=payload.get("message", ""),
        payload=payload.get("payload", {}),
    )