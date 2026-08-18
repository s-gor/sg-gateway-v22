from __future__ import annotations

import ipaddress
import re
import subprocess


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


def global_ip(value: object, version: int) -> str:
    host = clean_host(value)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return ""
    if address.version != int(version) or not address.is_global:
        return ""
    return address.compressed


def detect_global_ipv6() -> str:
    """Return the host's routable IPv6 address without external HTTP calls."""
    commands = (
        ["ip", "-6", "route", "get", "2606:4700:4700::1111"],
        ["ip", "-6", "-o", "address", "show", "scope", "global"],
    )
    for index, command in enumerate(commands):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        candidates: list[str] = []
        if index == 0:
            candidates.extend(re.findall(r"\bsrc\s+([^\s]+)", result.stdout))
        else:
            candidates.extend(re.findall(r"\binet6\s+([^\s/]+)(?:/\d+)?", result.stdout))
        for candidate in candidates:
            value = global_ip(candidate, 6)
            if value:
                return value
    return ""


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
