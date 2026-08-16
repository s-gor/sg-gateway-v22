from __future__ import annotations

from app.config import load_config
from app.net import clean_host, ip_version
from app.security.tls import overview as tls_overview


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
        host = clean_host(value)
        if ip_version(host) == 4:
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
        host = clean_host(value)
        if ip_version(host) == 6:
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
        # Preserve the 02112 public endpoint contract literally: this remains
        # the first IP fallback even after the dual-stack metadata was added.
        current_address = clean_host(load_config().public_address)
        config = load_config()
        current_ipv4 = clean_host(config.public_ipv4)
        current_ipv6 = clean_host(config.public_ipv6)
    except Exception:
        current_address = ""
        current_ipv4 = ""
        current_ipv6 = ""

    for value in (current_address, current_ipv4, current_ipv6, *fallbacks):
        host = clean_host(value)
        if host:
            return host
    return ""
