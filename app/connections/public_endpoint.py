from __future__ import annotations

import ipaddress

from app.config import load_config
from app.security.tls import overview as tls_overview


def _clean_host(value: object) -> str:
    host = str(value or "").strip().rstrip(".")
    if len(host) >= 2 and host.startswith("[") and host.endswith("]"):
        host = host[1:-1].strip()
    return host


def _ip_version(value: object) -> int | None:
    host = _clean_host(value)
    if not host:
        return None
    try:
        return ipaddress.ip_address(host).version
    except ValueError:
        return None


def format_host(host: object) -> str:
    """Format a host for URI/endpoint authority use.

    IPv6 literals are enclosed in brackets. DNS names and IPv4 addresses are
    returned unchanged. Already-bracketed IPv6 literals are normalised.
    """
    value = _clean_host(host)
    if not value:
        return ""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if address.version == 6:
        return f"[{address.compressed}]"
    return str(address)


def format_host_port(host: object, port: int) -> str:
    value = format_host(host)
    return f"{value}:{int(port)}" if value else ""


# SG_GATEWAY_02112_ALL_CONNECTIONS_DOMAIN_FIX3
def working_tls_domain() -> str:
    """Return the live HTTPS domain only when SG-Gateway considers TLS ready."""
    try:
        state = tls_overview()
    except Exception:
        return ""
    domain = str(state.get("domain") or "").strip().lower().rstrip(".")
    return domain if state.get("https_ready") and domain else ""


def public_ipv4(*fallbacks: object) -> str:
    """Return the current public IPv4 when available."""
    try:
        config = load_config()
        candidates = (config.public_ipv4, config.public_address, *fallbacks)
    except Exception:
        candidates = fallbacks
    for value in candidates:
        host = _clean_host(value)
        if _ip_version(host) == 4:
            return host
    return ""


def public_ipv6(*fallbacks: object) -> str:
    """Return the current public IPv6 when available."""
    try:
        config = load_config()
        candidates = (config.public_ipv6, config.public_address, *fallbacks)
    except Exception:
        candidates = fallbacks
    for value in candidates:
        host = _clean_host(value)
        if _ip_version(host) == 6:
            return host
    return ""


def public_host(*fallbacks: object) -> str:
    """One public endpoint policy for every SG-Gateway connection.

    A working HTTPS domain always wins. Without it, the legacy public address
    remains preferred so existing IPv4 installations do not change behaviour.
    If no legacy address exists, explicit IPv4/IPv6 runtime values are used.
    Callers may provide legacy/settings fallbacks for development and tests.
    """
    domain = working_tls_domain()
    if domain:
        return domain

    try:
        config = load_config()
        current_address = _clean_host(config.public_address)
        current_ipv4 = _clean_host(config.public_ipv4)
        current_ipv6 = _clean_host(config.public_ipv6)
    except Exception:
        current_address = ""
        current_ipv4 = ""
        current_ipv6 = ""

    for value in (current_address, current_ipv4, current_ipv6, *fallbacks):
        host = _clean_host(value)
        if host:
            return host
    return ""
