from __future__ import annotations

from app.config import load_config
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


def public_host(*fallbacks: object) -> str:
    """One public endpoint policy for every SG-Gateway connection.

    A working HTTPS domain always wins.  Without it, the current destination
    public address is preferred so a portable restore cannot leak an old host.
    Callers may provide legacy/settings fallbacks for development and tests.
    """
    domain = working_tls_domain()
    if domain:
        return domain

    try:
        current_address = str(load_config().public_address or "").strip().rstrip(".")
    except Exception:
        current_address = ""
    if current_address:
        return current_address

    for value in fallbacks:
        host = str(value or "").strip().rstrip(".")
        if host:
            return host
    return ""
