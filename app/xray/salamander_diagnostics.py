from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.connections.settings import get_connection_settings
from app.hostd.client import run_hostd_command
from app.xray.salamander import (
    GECKO_MODE,
    GECKO_PACKET_SIZE,
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


def _live_obfs(inbound: dict[str, Any] | None) -> tuple[str, str, str]:
    if not isinstance(inbound, dict):
        return SALAMANDER_MODE_NONE, "", ""
    stream = inbound.get("streamSettings")
    if not isinstance(stream, dict):
        return SALAMANDER_MODE_NONE, "", ""
    finalmask = stream.get("finalmask")
    if not isinstance(finalmask, dict):
        return SALAMANDER_MODE_NONE, "", ""
    udp = finalmask.get("udp")
    if not isinstance(udp, list):
        return SALAMANDER_MODE_NONE, "", ""
    for item in udp:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != SALAMANDER_MODE:
            continue
        settings = item.get("settings")
        if not isinstance(settings, dict):
            return SALAMANDER_MODE, "", ""
        packet_size = str(settings.get("packetSize") or "")
        mode = GECKO_MODE if packet_size == GECKO_PACKET_SIZE else SALAMANDER_MODE
        return mode, str(settings.get("password") or ""), packet_size
    return SALAMANDER_MODE_NONE, "", ""


def inspect(path: Path = XRAY_CONFIG_PATH) -> dict[str, Any]:
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    try:
        mode = normalise_mode(config.get("hysteria2_obfs_mode"))
    except ValueError:
        mode = SALAMANDER_MODE_NONE
    secret = str(config.get("hysteria2_obfs_password") or "")
    database_enabled = mode != SALAMANDER_MODE_NONE
    database_secret_ready = password_ready(secret)

    live_payload, live_error = _load_live_config(path)
    inbound = _find_hysteria2_inbound(live_payload)
    live_mode, live_password, live_packet_size = _live_obfs(inbound)
    live_active = live_mode != SALAMANDER_MODE_NONE
    live_secret_ready = password_ready(live_password)
    mode_matches = mode == live_mode
    password_matches = bool(
        database_enabled
        and database_secret_ready
        and live_active
        and live_secret_ready
        and secret == live_password
    )
    packet_size_ready = bool(
        mode != GECKO_MODE or live_packet_size == GECKO_PACKET_SIZE
    )

    # The web process may not be able to read root-owned Xray config. The
    # existing privileged command predates the public Gecko mode and reports
    # password equality only for DB mode "salamander". For Gecko, an applied
    # Xray candidate already validated the exact password + packetSize, so the
    # safe HostD fallback can use the presence verdict without changing HostD.
    if live_error:
        hostd = run_hostd_command("xray.salamander.status", timeout=5)
        if hostd.status == "ok" and hostd.payload.get("readable"):
            live_error = ""
            inbound = {} if hostd.payload.get("inbound_present") else None
            live_active = bool(hostd.payload.get("finalmask_udp_active"))
            live_secret_ready = bool(hostd.payload.get("live_password_configured"))
            hostd_password_matches = bool(hostd.payload.get("password_matches_database"))
            if mode == GECKO_MODE:
                password_matches = bool(
                    database_secret_ready and live_active and live_secret_ready
                )
            else:
                password_matches = hostd_password_matches
            if password_matches:
                live_mode = mode
                mode_matches = True
                packet_size_ready = True

    consistent = (
        (not database_enabled and not live_active)
        or (password_matches and mode_matches and packet_size_ready)
    )
    uri_parameters_present = database_enabled and database_secret_ready
    mode_label = {
        SALAMANDER_MODE_NONE: "None",
        SALAMANDER_MODE: "Salamander",
        GECKO_MODE: "Gecko",
    }.get(mode, "Unknown")

    return {
        "mode": mode,
        "mode_label": mode_label,
        "password_configured": database_secret_ready,
        "finalmask_udp_active": live_active,
        "live_mode": live_mode,
        "gecko_packet_size": GECKO_PACKET_SIZE if mode == GECKO_MODE else "",
        "gecko_packet_size_ready": packet_size_ready if mode == GECKO_MODE else True,
        "client_uri_parameters_present": uri_parameters_present,
        "live_password_configured": live_secret_ready,
        "password_matches_live": password_matches,
        "consistent": consistent,
        "live_config_error": live_error,
        "inbound_present": inbound is not None,
        "safe_lines": [
            f"Hysteria2 obfuscation: {mode_label}",
            "Hysteria2 obfs password: " + ("configured" if database_secret_ready else "not configured"),
            "Gecko packetSize: " + (GECKO_PACKET_SIZE if mode == GECKO_MODE else "disabled"),
            "FinalMask UDP layer: " + ("active" if live_active else "inactive"),
            "Client URI parameters: " + ("present" if uri_parameters_present else "absent"),
        ],
    }
