from __future__ import annotations

import json
import sqlite3
from types import ModuleType


# Final Clients & Keys contract for 22.06.
# The archive keeps client identity only. Any value copied from the source
# server is stripped before packaging and rebound from the destination server
# before the established transactional restore starts.
CLIENT_TABLES = (
    "clients",
    "devices",
    "device_credentials",
    "sg_subscription_tokens",
    "router_subscription_tokens",
)
REQUIRED_CLIENT_TABLES = ("clients", "devices", "device_credentials")

# Legacy client_deployments can contain stale server endpoints/keys. It is
# removed together with the current client catalogue on restore, but is never
# copied into a Clients & Keys archive. device_credentials is canonical in 22.06.
DELETE_ORDER = (
    "sg_subscription_tokens",
    "router_subscription_tokens",
    "device_credentials",
    "client_deployments",
    "devices",
    "clients",
)
INSERT_ORDER = (
    "clients",
    "devices",
    "device_credentials",
    "sg_subscription_tokens",
    "router_subscription_tokens",
)

SERVER_FIELDS = {
    "amneziawg": {
        "dns",
        "server_public_key",
        "endpoint",
        "allowed_ips",
        "persistent_keepalive",
        "dual_stack",
        "ipv6_network",
        "jc",
        "jmin",
        "jmax",
        "s1",
        "s2",
        "h1",
        "h2",
        "h3",
        "h4",
    },
    "amneziawg3": {
        "dns",
        "server_public_key",
        "endpoint",
        "port",
        "allowed_ips",
        "persistent_keepalive",
        "dual_stack",
        "ipv6_network",
        "jc",
        "jmin",
        "jmax",
        "s1",
        "s2",
        "s3",
        "s4",
        "h1",
        "h2",
        "h3",
        "h4",
        "header_protection_key",
        "content_padding_addition",
        "rekey_after_time",
        "rekey_timeout",
        "reject_after_time",
        "keepalive_timeout",
        "max_handshake_attempts",
    },
    "xray": {
        "host",
        "port",
        "security",
        "type",
        "flow",
        "fingerprint",
        "server_name",
        "public_key",
        "short_id",
        "vless_encryption",
    },
    "anytls": {"host", "port", "server_name"},
    "tuic": {
        "host",
        "port",
        "server_name",
        "congestion_control",
        "udp_relay_mode",
        "alpn",
    },
}


def _safe_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if 1 <= parsed <= 65535 else fallback


def _rebind_client_credentials(data: ModuleType, database: sqlite3.Connection) -> None:
    awg_host, awg_port, awg = data._connection_setting(database, "amneziawg")
    awg3_host, awg3_port, awg3 = data._connection_setting(database, "amneziawg3")
    xray_host, xray_port, xray = data._connection_setting(database, "xray")
    _, _, mihomo = data._connection_setting(database, "mihomo")

    public_host = str(
        data.full._destination_public_address() or xray_host or awg_host or awg3_host or ""
    ).strip()
    tls_state = data.full._restored_tls_state()
    tls_domain = str(tls_state.get("domain") or "").strip()
    tls_host = tls_domain or public_host
    anytls_port = _safe_int(mihomo.get("anytls_port"), 9443)
    tuic_port = _safe_int(mihomo.get("tuic_port"), 10443)

    rows = database.execute(
        "SELECT id, engine, config_json FROM device_credentials ORDER BY id"
    ).fetchall()
    for row_id, engine_raw, raw in rows:
        engine = str(engine_raw)
        try:
            payload = json.loads(raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        if engine == "amneziawg":
            payload.update(
                {
                    "dns": awg.get("dns", "1.1.1.1"),
                    "server_public_key": awg.get("server_public_key", ""),
                    "endpoint": data._endpoint(awg_host or public_host, awg_port),
                    "allowed_ips": awg.get("allowed_ips", "0.0.0.0/0, ::/0"),
                    "persistent_keepalive": awg.get("persistent_keepalive", 25),
                }
            )
        elif engine == "amneziawg3":
            payload.update(
                {
                    "dns": awg3.get("dns", "1.1.1.1"),
                    "server_public_key": awg3.get("server_public_key", ""),
                    "endpoint": data._endpoint(awg3_host or public_host, awg3_port),
                    "port": awg3_port,
                    "allowed_ips": awg3.get("allowed_ips", "0.0.0.0/0, ::/0"),
                    "persistent_keepalive": awg3.get("persistent_keepalive", "25-35"),
                    "generation": 3,
                }
            )
        elif engine == "xray":
            payload["host"] = xray_host or public_host
            payload["port"] = xray_port
            for key in (
                "security",
                "type",
                "flow",
                "fingerprint",
                "server_name",
                "public_key",
                "short_id",
                "vless_encryption",
            ):
                if key in xray:
                    payload[key] = xray[key]
        elif engine == "anytls":
            payload["host"] = tls_host
            payload["port"] = anytls_port
            payload["server_name"] = tls_domain
        elif engine == "tuic":
            payload["host"] = tls_host
            payload["port"] = tuic_port
            payload["server_name"] = tls_domain
            payload["congestion_control"] = str(
                mihomo.get("tuic_congestion_controller") or "bbr"
            )
            payload["udp_relay_mode"] = str(
                mihomo.get("tuic_udp_relay_mode") or "native"
            )
            payload["alpn"] = str(mihomo.get("tuic_alpn") or "h3")

        database.execute(
            "UPDATE device_credentials SET config_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False, sort_keys=True), int(row_id)),
        )


def install(data: ModuleType) -> None:
    data.CLIENT_TABLES = CLIENT_TABLES
    data.REQUIRED_CLIENT_TABLES = REQUIRED_CLIENT_TABLES
    data.DELETE_ORDER = DELETE_ORDER
    data.INSERT_ORDER = INSERT_ORDER
    data._SERVER_FIELDS = SERVER_FIELDS

    def rebound(database: sqlite3.Connection) -> None:
        _rebind_client_credentials(data, database)

    data._rebind_client_credentials = rebound
