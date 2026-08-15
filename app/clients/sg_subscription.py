from __future__ import annotations

import base64
import json
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.clients.exports import build_protocol_export, protocol_ready
from app.clients.repository import Client, device_access_tokens, list_devices

SG_SUBSCRIPTION_FORMAT = "sg-subscription"
SG_SUBSCRIPTION_VERSION = 1

_PROFILE_SPECS = (
    ("xray_reality_tcp", "xray_reality_tcp", "xray-reality-tcp", "VLESS Reality TCP", "vless", "uri"),
    ("xray_xhttp_reality", "xray_xhttp_reality", "xray-xhttp-reality", "VLESS XHTTP Reality", "vless", "uri"),
    ("xray_xhttp_tls", "xray_xhttp_tls", "xray-xhttp-tls", "VLESS XHTTP TLS", "vless", "uri"),
    ("xray_hysteria2", "xray_hysteria2", "hysteria2", "Hysteria 2", "hysteria2", "uri"),
    ("amneziawg", "amneziawg", "amneziawg", "AmneziaWG 2.0", "amneziawg", "config"),
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
    except Exception:
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
        devices.append({
            "id": device.id,
            "name": device.name,
            "primary": bool(device.is_primary),
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


def _subscription_label(client_name: str, device: dict, profile_name: str) -> str:
    device_name = "Основное устройство" if device.get("primary") else str(device.get("name") or "Устройство")
    return f"{client_name} · {device_name} · {profile_name}"


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
        "device": device.get("name"),
        "primary": bool(device.get("primary")),
        "encoding": "base64url",
        "data": encoded,
    }
    return "# SG-CONFIG " + json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))


def build_sg_subscription_text(client: Client) -> str:
    """Build the SG v1 human-readable backward-compatible envelope with URI and SG-CONFIG records."""
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
        device_name = "Основное устройство" if device.get("primary") else str(device.get("name") or "Устройство")
        lines.append(
            "# SG-DEVICE "
            + json.dumps(
                {
                    "id": device.get("id"),
                    "name": device_name,
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
                label = _subscription_label(client.name, device, str(profile.get("name") or profile.get("id") or "Профиль"))
                lines.append(_with_fragment(str(profile["uri"]), label))
            elif profile.get("format") == "config" and profile.get("config"):
                lines.append(_config_marker(profile, device))

    return "\n".join(lines) + "\n"
