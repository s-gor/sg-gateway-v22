from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from flask import has_request_context, request

from app.clients.repository import (
    Client,
    Device,
    get_primary_device,
    list_client_deployments,
    list_device_credentials,
)
from app.config import load_config
from app.connections.settings import get_connection_settings
from app.connections.public_endpoint import public_host, working_tls_domain
from app.mihomo.service import build_device_yaml
from app.net import format_host, format_host_port

from app.security.tls import overview as tls_overview
from app.xray.profiles import REALITY_TCP_FLOW, overview as xray_profiles_overview
from app.xray.xmux import XmuxError, effective_client_extra
from app.xray.sg_panel_vless import reality_tcp_link, xhttp_reality_link
from app.xray.settings_transactions import pending as pending_settings_transaction


@dataclass(frozen=True)
class ClientExport:
    filename: str
    media_type: str
    body: str


def _resolve_device(client: Client, device: Device | None) -> Device | None:
    return device if device is not None else get_primary_device(client.id)


def _deployments(client: Client, device: Device | None = None) -> dict:
    # Keep the legacy primary wrapper here: several existing extension tests
    # monkeypatch list_client_deployments and must continue to work.
    rows = (
        list_device_credentials(device.id)
        if device is not None
        else list_client_deployments(client.id)
    )
    return {item.engine: item for item in rows}


def _deployment_config(
    client: Client,
    engine: str,
    device: Device | None = None,
) -> dict:
    deployment = _deployments(client, device).get(engine)
    if deployment is None or not deployment.config_json:
        return {}
    try:
        value = json.loads(deployment.config_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _label(client: Client, device: Device | None) -> str:
    if device is None or device.is_primary:
        return client.name
    return f"{client.name} · {device.name}"


def _slug(client: Client, device: Device | None) -> str:
    return f"{client.id}" if device is None else f"{client.id}-device-{device.id}"


# SG_GATEWAY_02110_DOMAIN_EXPORT_FIX1
# SG_GATEWAY_02112_ALL_CONNECTIONS_DOMAIN_FIX3
def _working_tls_domain() -> str:
    return working_tls_domain()


def _public_export_host(*fallbacks: object) -> str:
    return public_host(*fallbacks)


def _format_endpoint(host: str, port: int) -> str:
    return format_host_port(host, port)


def is_export_ready(
    client: Client,
    engine: str,
    device: Device | None = None,
) -> bool:
    resolved = _resolve_device(client, device)
    deployment = _deployments(client, device).get(engine)
    return bool(
        client.enabled
        and (resolved is None or resolved.enabled)
        and deployment is not None
        and deployment.status == "applied"
    )


def _selected_xray_profiles(
    client: Client,
    device: Device | None = None,
) -> list[str]:
    config = _deployment_config(client, "xray", device)
    selected = config.get("profiles")
    if isinstance(selected, list):
        result = [str(item) for item in selected if str(item).strip()]
        if result:
            return result
    return ["reality_tcp", "xhttp_reality"]


def build_awg_config(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "amneziawg", device)
    label = _label(client, device)
    endpoint = str(config.get("endpoint") or "")
    try:
        awg_settings = get_connection_settings("amneziawg")
        endpoint_host = _public_export_host(awg_settings.host)
        endpoint_port = int(awg_settings.port or 585)
        if endpoint_host:
            endpoint = _format_endpoint(endpoint_host, endpoint_port)
    except Exception:
        pass
    body = f"""# SG-Gateway AmneziaWG
# Access: {label}

[Interface]
PrivateKey = {config.get("private_key", "")}
Address = {config.get("address", "")}
DNS = {config.get("dns", "1.1.1.1")}
Jc = {config.get("jc", "")}
Jmin = {config.get("jmin", "")}
Jmax = {config.get("jmax", "")}
S1 = {config.get("s1", "")}
S2 = {config.get("s2", "")}
H1 = {config.get("h1", "")}
H2 = {config.get("h2", "")}
H3 = {config.get("h3", "")}
H4 = {config.get("h4", "")}

[Peer]
PublicKey = {config.get("server_public_key", "")}
Endpoint = {endpoint}
AllowedIPs = {config.get("allowed_ips", "0.0.0.0/0, ::/0")}
PersistentKeepalive = {config.get("persistent_keepalive", 25)}
"""
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-amneziawg.conf",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def build_awg3_config(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "amneziawg3", device)
    label = _label(client, device)
    endpoint = str(config.get("endpoint") or "")
    try:
        settings = get_connection_settings("amneziawg3")
        endpoint_host = _public_export_host(settings.host)
        endpoint_port = int(settings.port or 586)
        if endpoint_host:
            endpoint = _format_endpoint(endpoint_host, endpoint_port)
    except Exception:
        pass
    body = f"""# SG-Gateway AmneziaWG 3.1
# Access: {label}

[Interface]
PrivateKey = {config.get("private_key", "")}
Address = {config.get("address", "")}
DNS = {config.get("dns", "1.1.1.1")}
Jc = {config.get("jc", "")}
Jmin = {config.get("jmin", "")}
Jmax = {config.get("jmax", "")}
S1 = {config.get("s1", "")}
S2 = {config.get("s2", "")}
S3 = {config.get("s3", "")}
S4 = {config.get("s4", "")}
H1 = {config.get("h1", "")}
H2 = {config.get("h2", "")}
H3 = {config.get("h3", "")}
H4 = {config.get("h4", "")}
HeaderProtectionKey = {config.get("header_protection_key", "")}
ContentPaddingAddition = {config.get("content_padding_addition", "")}
RekeyAfterTime = {config.get("rekey_after_time", "")}
RekeyTimeout = {config.get("rekey_timeout", "")}
RejectAfterTime = {config.get("reject_after_time", "")}
KeepaliveTimeout = {config.get("keepalive_timeout", "")}
MaxHandshakeAttempts = {config.get("max_handshake_attempts", "")}

[Peer]
PublicKey = {config.get("server_public_key", "")}
Endpoint = {endpoint}
AllowedIPs = {config.get("allowed_ips", "0.0.0.0/0, ::/0")}
PersistentKeepalive = {config.get("persistent_keepalive", "25-35")}
"""
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-amneziawg3.conf",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def _xray_profile(profile_id: str):
    state = xray_profiles_overview()
    return state, next(
        (item for item in state["profiles"] if item.id == profile_id),
        None,
    )


def _rewrite_xhttp_link(body: str, profile_id: str, config: dict) -> str:
    """Apply the SG-Panel client-side XMUX contract to one ready XHTTP link."""
    if not body or profile_id not in {"xhttp_reality", "xhttp_tls"}:
        return body

    try:
        extra = effective_client_extra(config)
    except XmuxError:
        # Invalid restored expert JSON must never leak a malformed Client Extra.
        extra = {}

    parts = urlsplit(body)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    rewritten: list[tuple[str, str]] = []
    mode_seen = False
    for key, value in pairs:
        if key == "extra":
            continue
        if profile_id == "xhttp_reality" and key == "mode":
            value = "stream-one"
            mode_seen = True
        rewritten.append((key, value))

    if profile_id == "xhttp_reality" and not mode_seen:
        rewritten.append(("mode", "stream-one"))
    if extra:
        rewritten.append(
            ("extra", json.dumps(extra, ensure_ascii=False, separators=(",", ":")))
        )

    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(rewritten), parts.fragment)
    )


def build_xray_profile_link(
    client: Client,
    profile_id: str,
    device: Device | None = None,
) -> ClientExport:
    config = _deployment_config(client, "xray", device)
    selected = _selected_xray_profiles(client, device)
    state, profile = _xray_profile(profile_id)
    filename = f"sg-gateway-{_slug(client, device)}-{profile_id}.txt"
    if profile is None or profile_id not in selected:
        return ClientExport(filename, "text/plain; charset=utf-8", "")

    safe_name = quote(f"{_label(client, device)} · {profile.title}", safe="")
    # SG-Panel contract: the access stores the UUID/profile selection, while
    # every server-dependent value comes from the current server state. This
    # prevents old client rows from exporting links for rotated/stale keys.
    current = get_connection_settings("xray")
    current_config = dict(current.config)
    current_host = str(current.host or "")
    pending = pending_settings_transaction("xray")
    if pending is not None:
        # While a candidate is being tested/applied, public links must remain
        # compatible with the still-live configuration. The candidate becomes
        # visible only after the runtime commits the transaction.
        current_config = dict(pending.previous_config)
        current_host = str(pending.previous_host or "")
        enabled_key = {
            "reality_tcp": "reality_tcp_enabled",
            "xhttp_reality": "xhttp_reality_enabled",
            "xhttp_tls": "xhttp_tls_enabled",
            "hysteria2": "hysteria2_enabled",
        }.get(profile_id, "")
        if enabled_key and not bool(current_config.get(enabled_key, profile_id in {"reality_tcp", "xhttp_reality"})):
            return ClientExport(filename, "text/plain; charset=utf-8", "")
        port_key = {
            "reality_tcp": "reality_tcp_port",
            "xhttp_reality": "xhttp_reality_port",
            "xhttp_tls": "xhttp_tls_port",
            "hysteria2": "hysteria2_port",
        }.get(profile_id, "")
        path_key = {
            "xhttp_reality": "xhttp_reality_path",
            "xhttp_tls": "xhttp_tls_path",
        }.get(profile_id, "")
        mode_key = {
            "xhttp_reality": "xhttp_reality_mode",
            "xhttp_tls": "xhttp_tls_mode",
        }.get(profile_id, "")
        xmux_key = {
            "xhttp_reality": "xhttp_reality_xmux_enabled",
            "xhttp_tls": "xhttp_tls_xmux_enabled",
        }.get(profile_id, "")
        if port_key:
            legacy_default = pending.previous_port if profile_id == "reality_tcp" else profile.port
            profile = type("AppliedProfile", (), {
                "id": profile.id,
                "title": profile.title,
                "port": int(current_config.get(port_key) or legacy_default),
                "path": str(current_config.get(path_key) or profile.path) if path_key else "",
                "mode": str(current_config.get(mode_key) or getattr(profile, "mode", "")) if mode_key else "",
                "xmux_enabled": True if xmux_key else False,
                "xmux": getattr(profile, "xmux", None),
            })()

    def usable(value: object) -> bool:
        text = str(value or "").strip()
        return bool(text) and "PLACEHOLDER" not in text.upper()

    current_ready = bool(
        usable(current.host)
        and usable(current_config.get("public_key"))
        and usable(current_config.get("short_id"))
    )
    server_config = current_config if current_ready else config
    host = _public_export_host(
        (current_host if current_ready else ""),
        config.get("host"),
        state.get("host"),
    )
    user_id = str(config.get("uuid") or "")
    fingerprint = str(server_config.get("fingerprint") or "firefox")
    server_name = str(server_config.get("server_name") or "bing.com")
    public_key = str(server_config.get("public_key") or "")
    short_id = str(server_config.get("short_id") or "")
    vless_encryption = str(server_config.get("vless_encryption") or "").strip()

    if profile_id == "reality_tcp":
        body = reality_tcp_link(
            uuid=user_id,
            host=host,
            port=profile.port,
            title=f"{_label(client, device)} · {profile.title}",
            fingerprint=fingerprint,
            server_name=server_name,
            public_key=public_key,
            short_id=short_id,
        )
    elif profile_id == "xhttp_reality":
        if not vless_encryption or "PLACEHOLDER" in vless_encryption.upper():
            body = ""
        else:
            body = xhttp_reality_link(
                uuid=user_id,
                host=host,
                port=profile.port,
                title=f"{_label(client, device)} · {profile.title}",
                fingerprint=fingerprint,
                server_name=server_name,
                public_key=public_key,
                short_id=short_id,
                path=profile.path,
                encryption=vless_encryption,
                client_mode=getattr(profile, "mode", "") or "stream-one",
                xmux=(
                    getattr(profile, "xmux", None)
                    if getattr(profile, "xmux_enabled", False)
                    else None
                ),
            )
    elif profile_id == "xhttp_tls":
        domain = _working_tls_domain() or str(state.get("tls_domain") or "")
        if not vless_encryption or "PLACEHOLDER" in vless_encryption.upper():
            body = ""
        else:
            query_values = {
                    "type": "xhttp",
                    "security": "tls",
                    "flow": REALITY_TCP_FLOW,
                    "encryption": vless_encryption,
                    "fp": fingerprint,
                    "sni": domain,
                    "alpn": "h2",
                    "path": profile.path,
                    "mode": getattr(profile, "mode", "") or "auto",
                }
            if getattr(profile, "xmux_enabled", False) and getattr(profile, "xmux", None):
                query_values["extra"] = json.dumps(
                    {"xmux": dict(profile.xmux)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            query = urlencode(query_values)
            endpoint = format_host_port(host, profile.port)
            body = f"vless://{user_id}@{endpoint}?{query}#{safe_name}"
    elif profile_id == "hysteria2":
        domain = _working_tls_domain() or str(state.get("tls_domain") or "")
        auth = str(config.get("hysteria_auth") or user_id)
        query_values = {
            "sni": domain,
            "insecure": "0",
        }
        obfs_mode = str(server_config.get("hysteria2_obfs_mode") or "none").strip().lower()
        obfs_password = str(server_config.get("hysteria2_obfs_password") or "").strip()
        endpoint = format_host_port(host, profile.port)
        if obfs_mode in {"salamander", "gecko"}:
            if not obfs_password:
                body = ""
            else:
                query_values["obfs"] = obfs_mode
                query_values["obfs-password"] = obfs_password
                scheme = str(server_config.get("hysteria2_uri_scheme") or "hysteria2").strip().lower()
                if scheme not in {"hysteria2", "hy2"}:
                    scheme = "hysteria2"
                query = urlencode(query_values)
                body = f"{scheme}://{quote(auth, safe='')}@{endpoint}/?{query}#{safe_name}"
        else:
            scheme = str(server_config.get("hysteria2_uri_scheme") or "hysteria2").strip().lower()
            if scheme not in {"hysteria2", "hy2"}:
                scheme = "hysteria2"
            query = urlencode(query_values)
            body = f"{scheme}://{quote(auth, safe='')}@{endpoint}/?{query}#{safe_name}"
    else:
        body = ""

    if profile_id in {"xhttp_reality", "xhttp_tls"} and body:
        body = _rewrite_xhttp_link(body, profile_id, current_config)

    return ClientExport(filename, "text/plain; charset=utf-8", body)


def build_xray_link(client: Client, device: Device | None = None) -> ClientExport:
    """Legacy generic Xray export returns the first profile selected for access."""
    selected = _selected_xray_profiles(client, device)
    profile_id = selected[0] if selected else "xhttp_reality"
    return build_xray_profile_link(client, profile_id, device)


def build_mieru_link(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "mihomo", device)
    settings = get_connection_settings("mihomo")
    mieru = config.get("mieru") if isinstance(config.get("mieru"), dict) else {}
    username = quote(str(mieru.get("username") or ""), safe="")
    password = quote(str(mieru.get("password") or ""), safe="")
    host = _public_export_host(settings.host)
    authority_host = format_host(host)
    port = int(settings.config.get("mieru_port", settings.port or 2099))
    transport = str(settings.config.get("mieru_transport", "TCP")).upper()
    multiplexing = str(settings.config.get("mieru_multiplexing", "MULTIPLEXING_LOW"))
    handshake = str(settings.config.get("mieru_handshake", "HANDSHAKE_STANDARD"))
    query = urlencode(
        {
            "profile": "default",
            "port": port,
            "protocol": transport,
            "multiplexing": multiplexing,
            "handshake-mode": handshake,
        }
    )
    body = f"mierus://{username}:{password}@{authority_host}?{query}#{quote(_label(client, device), safe='')}"
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-mieru.txt",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def build_mieru_json(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "mihomo", device)
    settings = get_connection_settings("mihomo")
    mieru = config.get("mieru") if isinstance(config.get("mieru"), dict) else {}
    host = _public_export_host(settings.host)
    port = int(settings.config.get("mieru_port", settings.port or 2099))
    transport = str(settings.config.get("mieru_transport") or "TCP").upper()
    multiplexing = str(
        settings.config.get("mieru_multiplexing") or "MULTIPLEXING_MIDDLE"
    )
    handshake = str(
        settings.config.get("mieru_handshake") or "HANDSHAKE_STANDARD"
    )
    document = {
        "outbounds": [
            {
                "type": "mieru",
                "tag": "mieru-proxy",
                "server": host,
                "server_port": port,
                "username": str(mieru.get("username") or ""),
                "password": str(mieru.get("password") or ""),
                "multiplexing": multiplexing,
                "handshake-mode": handshake,
                "transport": transport,
            }
        ]
    }
    body = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-mieru.json",
        media_type="application/json; charset=utf-8",
        body=body,
    )


def build_mihomo_yaml(client: Client, device: Device | None = None) -> ClientExport:
    resolved = _resolve_device(client, device)
    if resolved is None:
        return ClientExport("", "application/yaml; charset=utf-8", "")
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-mihomo.yaml",
        media_type="application/yaml; charset=utf-8",
        body=build_device_yaml(resolved.id, _label(client, resolved)),
    )


def build_anytls_link(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "anytls", device)
    host = _public_export_host(config.get("host", ""))
    endpoint = format_host_port(host, int(config.get("port", 9443)))
    tls_domain = _working_tls_domain() or str(config.get("server_name") or "")
    safe_name = quote(f"{_label(client, device)} · AnyTLS", safe="")
    query = urlencode(
        {
            "security": "tls",
            "sni": tls_domain,
            "fp": config.get("fingerprint", "firefox"),
            "type": "tcp",
        }
    )
    body = (
        f"anytls://{quote(str(config.get('password') or ''), safe='')}"
        f"@{endpoint}?{query}#{safe_name}"
    )
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-anytls.txt",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def build_tuic_link(client: Client, device: Device | None = None) -> ClientExport:
    config = _deployment_config(client, "tuic", device)
    host = _public_export_host(config.get("host", ""))
    endpoint = format_host_port(host, int(config.get("port", 10443)))
    tls_domain = _working_tls_domain() or str(config.get("server_name") or "")
    safe_name = quote(f"{_label(client, device)} · TUIC v5", safe="")
    query = urlencode(
        {
            "congestion_control": config.get("congestion_control", "bbr"),
            "udp_relay_mode": config.get("udp_relay_mode", "native"),
            "alpn": config.get("alpn", "h3"),
            "sni": tls_domain,
        }
    )
    body = (
        f"tuic://{config.get('uuid', '')}:"
        f"{quote(str(config.get('password') or ''), safe='')}"
        f"@{endpoint}?{query}#{safe_name}"
    )
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-tuic-v5.txt",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def protocol_engine(kind: str) -> str:
    return {
        "amneziawg": "amneziawg",
        "amneziawg3": "amneziawg3",
        "xray": "xray",
        "xray-reality-tcp": "xray",
        "xray-xhttp-reality": "xray",
        "xray-xhttp-tls": "xray",
        "hysteria2": "xray",
        "mieru": "mihomo",
        "mieru-json": "mihomo",
        "mihomo": "mihomo",
        "anytls": "anytls",
        "tuic": "tuic",
        "subscription": "sgclient",
    }.get(kind, "")


def build_protocol_export(
    client: Client,
    kind: str,
    device: Device | None = None,
) -> ClientExport:
    builders = {
        "amneziawg": build_awg_config,
        "amneziawg3": build_awg3_config,
        "xray": build_xray_link,
        "xray-reality-tcp": lambda item, access=None: build_xray_profile_link(item, "reality_tcp", access),
        "xray-xhttp-reality": lambda item, access=None: build_xray_profile_link(item, "xhttp_reality", access),
        "xray-xhttp-tls": lambda item, access=None: build_xray_profile_link(item, "xhttp_tls", access),
        "hysteria2": lambda item, access=None: build_xray_profile_link(item, "hysteria2", access),
        "mieru": build_mieru_link,
        "mieru-json": build_mieru_json,
        "mihomo": build_mihomo_yaml,
        "anytls": build_anytls_link,
        "tuic": build_tuic_link,
        "subscription": build_subscription,
    }
    builder = builders.get(kind)
    if builder is None:
        return ClientExport("", "text/plain; charset=utf-8", "")
    return builder(client, device)


def protocol_ready(
    client: Client,
    kind: str,
    device: Device | None = None,
) -> bool:
    engine = protocol_engine(kind)
    if not engine or not is_export_ready(client, engine, device):
        return False
    if kind.startswith("xray-") or kind == "hysteria2":
        profile_id = {
            "xray-reality-tcp": "reality_tcp",
            "xray-xhttp-reality": "xhttp_reality",
            "xray-xhttp-tls": "xhttp_tls",
            "hysteria2": "hysteria2",
        }[kind]
        if profile_id not in _selected_xray_profiles(client, device):
            return False
        _, profile = _xray_profile(profile_id)
        return bool(profile and profile.enabled and profile.ready)
    if kind in {"anytls", "tuic"}:
        return bool(tls_overview().get("https_ready"))
    return True


def _subscription_token(client: Client, device: Device | None = None) -> str:
    config = _deployment_config(client, "sgclient", device)
    return str(config.get("subscription_token") or "").strip()


def _subscription_base_url() -> str:
    tls = tls_overview()
    public_url = str(tls.get("public_url") or "").strip()
    if tls.get("https_ready") and public_url:
        return public_url.rstrip("/")

    config = load_config()
    address = str(config.public_address or config.public_ipv4 or config.public_ipv6 or "").strip()
    if address:
        if address.startswith(("http://", "https://")):
            return address.rstrip("/")
        host = format_host(address)
        suffix = "" if int(config.public_port) == 80 else f":{int(config.public_port)}"
        return f"http://{host}{suffix}"

    if has_request_context():
        return request.host_url.rstrip("/")
    return ""


def build_subscription_url(client: Client, device: Device | None = None) -> str:
    token = _subscription_token(client, device)
    base = _subscription_base_url()
    if not token or not base:
        return ""
    return f"{base}/sub/{quote(token, safe='')}"


def build_subscription(
    client: Client,
    device: Device | None = None,
) -> ClientExport:
    # Default compatible v2rayN-style Base64 subscription.
    #
    # Included: VLESS Reality TCP, Hysteria2, AnyTLS and TUIC v5.
    # XHTTP, Mieru and AmneziaWG remain available through their individual
    # links, QR codes or configuration downloads.
    links: list[str] = []

    def append_link(value: str) -> None:
        clean = str(value or "").strip()
        if clean and clean not in links:
            links.append(clean)

    if is_export_ready(client, "xray", device):
        selected = _selected_xray_profiles(client, device)
        for profile_id, kind in (
            ("reality_tcp", "xray-reality-tcp"),
            ("hysteria2", "hysteria2"),
        ):
            if profile_id not in selected:
                continue
            if protocol_ready(client, kind, device):
                append_link(build_protocol_export(client, kind, device).body)

    if (
        is_export_ready(client, "anytls", device)
        and protocol_ready(client, "anytls", device)
    ):
        append_link(build_anytls_link(client, device).body)

    if (
        is_export_ready(client, "tuic", device)
        and protocol_ready(client, "tuic", device)
    ):
        append_link(build_tuic_link(client, device).body)

    decoded = "\n".join(links)
    if decoded:
        decoded += "\n"
    body = base64.b64encode(decoded.encode("utf-8")).decode("ascii")
    return ClientExport(
        filename=f"sg-gateway-{_slug(client, device)}-subscription.txt",
        media_type="text/plain; charset=utf-8",
        body=body,
    )