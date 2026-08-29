from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.clients.exports import build_protocol_export, protocol_ready
from app.clients.repository import Client, device_access_tokens, list_devices

SG_SUBSCRIPTION_FORMAT = "sg-subscription"
SG_SUBSCRIPTION_VERSION = 1
SG_ROUTER_SUBSCRIPTION_FORMAT = "sg-router-subscription"
SG_ROUTER_SUBSCRIPTION_VERSION = 1

_PROFILE_SPECS = (
    ("xray_reality_tcp", "xray_reality_tcp", "xray-reality-tcp", "VLESS Reality TCP", "vless", "uri"),
    ("xray_xhttp_reality", "xray_xhttp_reality", "xray-xhttp-reality", "VLESS XHTTP Reality", "vless", "uri"),
    ("xray_xhttp_tls", "xray_xhttp_tls", "xray-xhttp-tls", "VLESS XHTTP TLS", "vless", "uri"),
    ("xray_hysteria2", "xray_hysteria2", "hysteria2", "Hysteria 2", "hysteria2", "uri"),
    ("amneziawg", "amneziawg", "amneziawg", "AmneziaWG 2.0", "amneziawg", "config"),
    ("amneziawg3", "amneziawg3", "amneziawg3", "AmneziaWG 3.1", "amneziawg", "config"),
    ("mieru", "mihomo", "mieru", "Mieru", "mieru", "uri"),
    ("anytls", "anytls", "anytls", "AnyTLS", "anytls", "uri"),
    ("tuic", "tuic", "tuic", "TUIC v5", "tuic", "uri"),
)


def canonical_profile_ids() -> tuple[str, ...]:
    return tuple(item[0] for item in _PROFILE_SPECS)


def _canonical_uri(profile_id: str, value: str) -> str:
    clean = str(value or "").strip()
    if not clean or profile_id not in {"anytls", "tuic"}:
        return clean
    parts = urlsplit(clean)
    first: dict[str, str] = {}
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key not in first:
            first[key] = item
    allowed = (
        ("sni", "insecure")
        if profile_id == "anytls"
        else ("congestion_control", "udp_relay_mode", "alpn", "sni")
    )
    query = urlencode([(key, first[key]) for key in allowed if key in first])
    return urlunsplit((parts.scheme, parts.netloc, "/", query, parts.fragment))


def _subscription_device_name(device: dict) -> str:
    if device.get("primary"):
        return ""
    return str(device.get("name") or "").strip()


def _profile_entry(client: Client, device, spec: tuple[str, ...]) -> dict:
    profile_id, _, export_kind, name, protocol, payload_kind = spec
    entry = {
        "id": profile_id,
        "name": name,
        "protocol": protocol,
        "format": payload_kind,
        "ready": False,
    }
    try:
        if not protocol_ready(client, export_kind, device):
            return entry
        export = build_protocol_export(client, export_kind, device)
        if not export.body:
            return entry
    except Exception:  # noqa: BLE001 - one broken export must not break the whole feed
        return entry
    entry["ready"] = True
    entry["media_type"] = export.media_type
    if payload_kind == "uri":
        entry["uri"] = _canonical_uri(profile_id, export.body)
    else:
        entry["config"] = export.body
    return entry


def build_sg_subscription_document(client: Client) -> dict:
    devices = []
    total_assigned = 0
    total_ready = 0
    for device in list_devices(client.id):
        assigned = set(device_access_tokens(device.id))
        profiles = []
        for spec in _PROFILE_SPECS:
            if spec[1] not in assigned:
                continue
            profile = _profile_entry(client, device, spec)
            profiles.append(profile)
            total_assigned += 1
            if profile["ready"]:
                total_ready += 1
        is_primary = bool(device.is_primary)
        devices.append({
            "id": device.id,
            "name": "" if is_primary else str(device.name or "").strip(),
            "primary": is_primary,
            "enabled": bool(device.enabled),
            "expires_at": device.expires_at,
            "profiles": profiles,
        })
    return {
        "format": SG_SUBSCRIPTION_FORMAT,
        "version": SG_SUBSCRIPTION_VERSION,
        "scope": "client",
        "client": {
            "id": client.id,
            "name": client.name,
            "enabled": bool(client.enabled),
            "expires_at": client.expires_at,
        },
        "summary": {
            "devices": len(devices),
            "profiles_assigned": total_assigned,
            "profiles_ready": total_ready,
        },
        "devices": devices,
    }


def build_router_subscription_document(client: Client, device_id: int) -> dict | None:
    """Build the small device-scoped JSON contract used by router subscriptions."""
    document = build_sg_subscription_document(client)
    device = next(
        (item for item in document["devices"] if int(item.get("id") or 0) == int(device_id)),
        None,
    )
    if device is None or not device.get("enabled"):
        return None

    profiles = []
    for profile in device.get("profiles", []):
        if not profile.get("ready"):
            continue
        payload_type = str(profile.get("format") or "")
        value = str(profile.get("uri") or profile.get("config") or "")
        if payload_type not in {"uri", "config"} or not value:
            continue
        profiles.append({
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or ""),
            "protocol": str(profile.get("protocol") or ""),
            "type": payload_type,
            "value": value,
        })

    return {
        "format": SG_ROUTER_SUBSCRIPTION_FORMAT,
        "version": SG_ROUTER_SUBSCRIPTION_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scope": "device",
        "client": {
            "id": client.id,
            "name": client.name,
        },
        "device": {
            "id": int(device.get("id") or 0),
            "name": _subscription_device_name(device),
            "primary": bool(device.get("primary")),
            "expires_at": device.get("expires_at"),
        },
        "summary": {
            "profiles": len(profiles),
        },
        "profiles": profiles,
    }


def build_keenetic_subscription_body(client: Client, device_id: int) -> str:
    """Return the plain VLESS feed consumed by Xkeen UI on Keenetic."""
    document = build_router_subscription_document(client, device_id)
    if document is None:
        return ""
    links = [
        str(profile.get("value") or "").strip()
        for profile in document.get("profiles", [])
        if profile.get("protocol") == "vless"
        and profile.get("type") == "uri"
        and str(profile.get("value") or "").strip().startswith("vless://")
    ]
    return "\n".join(links) + ("\n" if links else "")


def _subscription_label(client_name: str, device: dict, profile_name: str) -> str:
    parts = [client_name]
    device_name = _subscription_device_name(device)
    if device_name:
        parts.append(device_name)
    parts.append(profile_name)
    return " · ".join(parts)


def _with_fragment(uri: str, label: str) -> str:
    parts = urlsplit(str(uri or "").strip())
    if not parts.scheme:
        return str(uri or "").strip()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, quote(label, safe="")))


def _config_marker(profile: dict, device: dict) -> str:
    raw = str(profile.get("config") or "").encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    metadata = {
        "profile": profile.get("id"),
        "name": profile.get("name"),
        "device_id": device.get("id"),
        "device": _subscription_device_name(device),
        "primary": bool(device.get("primary")),
        "encoding": "base64url",
        "data": encoded,
    }
    return "# SG-CONFIG " + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))



def _ready_uri_lines(document: dict) -> list[str]:
    client_name = str((document.get("client") or {}).get("name") or "SG")
    lines: list[str] = []
    for device in document.get("devices", []):
        for profile in device.get("profiles", []):
            if not profile.get("ready") or profile.get("format") != "uri" or not profile.get("uri"):
                continue
            label = _subscription_label(
                client_name,
                device,
                str(profile.get("name") or profile.get("id") or "Профиль"),
            )
            lines.append(_with_fragment(str(profile["uri"]), label))
    return lines


def build_compatible_subscription_body(client: Client) -> str:
    """Return the proven v2rayN-style Base64 transport for all ready URI profiles."""
    document = build_sg_subscription_document(client)
    decoded = "\n".join(_ready_uri_lines(document))
    if decoded:
        decoded += "\n"
    return base64.b64encode(decoded.encode("utf-8")).decode("ascii")


def build_sg_subscription_text(client: Client) -> str:
    """Build the SG v1 human-readable envelope with URI and SG-CONFIG records."""
    document = build_sg_subscription_document(client)
    summary = document["summary"]
    lines = [
        "# SG-SUBSCRIPTION/1",
        "# scope=client",
        f"# client={client.name}",
        f"# devices={summary['devices']}",
        f"# profiles-assigned={summary['profiles_assigned']}",
        f"# profiles-ready={summary['profiles_ready']}",
    ]

    for device in document["devices"]:
        lines.append(
            "# SG-DEVICE "
            + json.dumps(
                {
                    "id": device.get("id"),
                    "name": _subscription_device_name(device),
                    "primary": bool(device.get("primary")),
                    "enabled": bool(device.get("enabled")),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        for profile in device.get("profiles", []):
            if not profile.get("ready"):
                continue
            if profile.get("format") == "uri" and profile.get("uri"):
                label = _subscription_label(
                    client.name,
                    device,
                    str(profile.get("name") or profile.get("id") or "Профиль"),
                )
                lines.append(_with_fragment(str(profile["uri"]), label))
            elif profile.get("format") == "config" and profile.get("config"):
                lines.append(_config_marker(profile, device))

    return "\n".join(lines) + "\n"
