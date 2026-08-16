from __future__ import annotations

import ipaddress


def clean_host(value: object) -> str:
    host = str(value or "").strip().rstrip(".")
    if len(host) >= 2 and host.startswith("[") and host.endswith("]"):
        host = host[1:-1].strip()
    return host


def ip_version(value: object) -> int | None:
    host = clean_host(value)
    if not host:
        return None
    try:
        return ipaddress.ip_address(host).version
    except ValueError:
        return None


def format_host(host: object) -> str:
    """Format a host for URI/endpoint authority use."""
    value = clean_host(host)
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
