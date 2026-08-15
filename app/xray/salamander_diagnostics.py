from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.connections.settings import get_connection_settings
from app.hostd.client import run_hostd_command
from app.xray.salamander import (
    SALAMANDER_MODE,
    SALAMANDER_MODE_NONE,
    normalise_mode,
    password_ready,
)


XRAY_CONFIG_PATH = Path("/usr/local/etc/xray/config.json")
HYSTERIA2_INBOUND_TAG = "sg-hysteria2"


def _load_live_config(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "Xray config not found"
    except (OSError, ValueError, json.JSONDecodeError):
        return {}, "Xray config is unreadable"
    if not isinstance(payload, dict):
        return {}, "Xray config root is invalid"
    return payload, ""


def _find_hysteria2_inbound(payload: dict[str, Any]) -> dict[str, Any] | None:
    inbounds = payload.get("inbounds")
    if not isinstance(inbounds, list):
        return None
    for inbound in inbounds:
        if not isinstance(inbound, dict):
            continue
        if str(inbound.get("tag") or "") == HYSTERIA2_INBOUND_TAG:
            return inbound
    return None


def _live_salamander(inbound: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(inbound, dict):
        return False, ""
    stream = inbound.get("streamSettings")
    if not isinstance(stream, dict):
        return False, ""
    finalmask = stream.get("finalmask")
    if not isinstance(finalmask, dict):
        return False, ""
    udp = finalmask.get("udp")
    if not isinstance(udp, list):
        return False, ""
    for item in udp:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != SALAMANDER_MODE:
            continue
        settings = item.get("settings")
        if not isinstance(settings, dict):
            return True, ""
        return True, str(settings.get("password") or "")
    return False, ""


def inspect(path: Path = XRAY_CONFIG_PATH) -> dict[str, Any]:
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    try:
        mode = normalise_mode(config.get("hysteria2_obfs_mode"))
    except ValueError:
        mode = SALAMANDER_MODE_NONE
    secret = str(config.get("hysteria2_obfs_password") or "")
    database_enabled = mode == SALAMANDER_MODE
    database_secret_ready = password_ready(secret)

    live_payload, live_error = _load_live_config(path)
    inbound = _find_hysteria2_inbound(live_payload)
    live_active, live_password = _live_salamander(inbound)
    live_secret_ready = password_ready(live_password)
    password_matches = bool(
        database_enabled
        and database_secret_ready
        and live_active
        and live_secret_ready
        and secret == live_password
    )

    # The web process intentionally cannot read root-only Xray config. Ask
    # privileged HostD for a safe, secret-free runtime verdict instead.
    if live_error:
        hostd = run_hostd_command("xray.salamander.status", timeout=5)
        if hostd.status == "ok" and hostd.payload.get("readable"):
            live_error = ""
            inbound = {} if hostd.payload.get("inbound_present") else None
            live_active = bool(hostd.payload.get("finalmask_udp_active"))
            live_secret_ready = bool(hostd.payload.get("live_password_configured"))
            password_matches = bool(hostd.payload.get("password_matches_database"))
    consistent = (
        (not database_enabled and not live_active)
        or password_matches
    )
    uri_parameters_present = database_enabled and database_secret_ready

    mode_label = "Salamander" if database_enabled else "None"
    return {
        "mode": mode,
        "mode_label": mode_label,
        "password_configured": database_secret_ready,
        "finalmask_udp_active": live_active,
        "client_uri_parameters_present": uri_parameters_present,
        "live_password_configured": live_secret_ready,
        "password_matches_live": password_matches,
        "consistent": consistent,
        "live_config_error": live_error,
        "inbound_present": inbound is not None,
        "safe_lines": [
            f"Hysteria2 obfuscation: {mode_label}",
            "Salamander password: " + ("configured" if database_secret_ready else "not configured"),
            "FinalMask UDP layer: " + ("active" if live_active else "inactive"),
            "Client URI parameters: " + ("present" if uri_parameters_present else "absent"),
        ],
    }
