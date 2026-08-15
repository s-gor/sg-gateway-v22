from __future__ import annotations

"""SG-Panel VLESS Reality contract adapted for SG-Gateway.

This module intentionally mirrors the known-working SG-Panel Preview 9 FIX36
server and client contract for the two domain-free channels used by SG-Gateway:
VLESS Reality TCP and VLESS XHTTP Reality.
"""

import json
import re
from typing import Any
from urllib.parse import quote

REALITY_TCP_FLOW = "xtls-rprx-vision"
VLESSENC_SERVER_MODE_DEFAULT = "auto"
VLESSENC_CLIENT_MODE_DEFAULT = "stream-one"

STANDARD_FINGERPRINTS = {
    "chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized"
}
FINGERPRINT_ALIASES = {
    "ff": "firefox",
    "google": "chrome",
}


def fingerprint_for_xray(value: str | None) -> str:
    profile = (value or "firefox").strip()
    if not profile:
        return "firefox"
    lowered = profile.lower()
    profile = lowered if lowered in STANDARD_FINGERPRINTS else profile
    if len(profile) > 80 or not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
        raise ValueError("Некорректное значение fingerprint")
    return FINGERPRINT_ALIASES.get(profile, profile)


def reality_settings(
    *,
    dest: str,
    server_name: str,
    private_key: str,
    short_ids: list[str],
) -> dict[str, Any]:
    values = [str(value).strip() for value in short_ids if str(value).strip()]
    if not values:
        raise ValueError("Не задан ShortID Reality")
    return {
        "show": False,
        "dest": str(dest).strip(),
        "xver": 0,
        "serverNames": [str(server_name).strip()],
        "privateKey": str(private_key).strip(),
        "shortIds": values,
    }


# SG_GATEWAY_PLACEHOLDER_80_443_V1
def reality_tcp_inbound(
    *,
    clients: list[dict[str, Any]],
    port: int,
    listen: str = "0.0.0.0",
    dest: str,
    server_name: str,
    private_key: str,
    short_id: str,
) -> dict[str, Any]:
    return {
        "tag": "sg-vless-reality-tcp",
        "listen": str(listen),
        "port": int(port),
        "protocol": "vless",
        "settings": {"clients": clients, "decryption": "none"},
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": reality_settings(
                dest=dest,
                server_name=server_name,
                private_key=private_key,
                short_ids=[short_id],
            ),
        },
    }


def xhttp_reality_inbound(
    *,
    clients: list[dict[str, Any]],
    port: int,
    path: str,
    decryption: str,
    dest: str,
    server_name: str,
    private_key: str,
    short_id: str,
) -> dict[str, Any]:
    return {
        "tag": "sg-vless-xhttp-reality",
        "listen": "0.0.0.0",
        "port": int(port),
        "protocol": "vless",
        "settings": {"clients": clients, "decryption": str(decryption)},
        "streamSettings": {
            "network": "xhttp",
            "security": "reality",
            "realitySettings": reality_settings(
                dest=dest,
                server_name=server_name,
                private_key=private_key,
                short_ids=[short_id],
            ),
            "xhttpSettings": {
                "path": str(path),
                "mode": VLESSENC_SERVER_MODE_DEFAULT,
            },
        },
    }


def reality_tcp_link(
    *,
    uuid: str,
    host: str,
    port: int,
    title: str,
    fingerprint: str,
    server_name: str,
    public_key: str,
    short_id: str,
) -> str:
    fp = quote(fingerprint_for_xray(fingerprint), safe="")
    query = (
        "encryption=none&type=tcp&security=reality"
        f"&pbk={quote(str(public_key), safe='-_')}"
        f"&fp={fp}&sni={quote(str(server_name), safe='')}"
        f"&sid={quote(str(short_id), safe='')}"
        f"&flow={REALITY_TCP_FLOW}&spx=%2F"
    )
    return (
        f"vless://{uuid}@{host}:{int(port)}?{query}"
        f"#{quote(str(title), safe='')}"
    )


def xhttp_reality_link(
    *,
    uuid: str,
    host: str,
    port: int,
    title: str,
    fingerprint: str,
    server_name: str,
    public_key: str,
    short_id: str,
    path: str,
    encryption: str,
    client_mode: str = VLESSENC_CLIENT_MODE_DEFAULT,
    xmux: dict[str, Any] | None = None,
) -> str:
    fp = quote(fingerprint_for_xray(fingerprint), safe="")
    encrypted = quote(str(encryption), safe="-._~")
    extra = ""
    if xmux:
        extra_json = json.dumps(
            {"xmux": dict(xmux)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        extra = f"&extra={quote(extra_json, safe='')}"
    query = (
        f"encryption={encrypted}&flow={REALITY_TCP_FLOW}"
        "&type=xhttp&security=reality"
        f"&pbk={quote(str(public_key), safe='-_')}"
        f"&fp={fp}&sni={quote(str(server_name), safe='')}"
        f"&sid={quote(str(short_id), safe='')}"
        f"&path={quote(str(path), safe='')}"
        f"&mode={quote(str(client_mode or VLESSENC_CLIENT_MODE_DEFAULT), safe='-_')}"
        f"{extra}&spx=%2F"
    )
    return (
        f"vless://{uuid}@{host}:{int(port)}?{query}"
        f"#{quote(str(title), safe='')}"
    )
