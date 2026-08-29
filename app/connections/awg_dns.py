from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass

from app.db import connect, init_db
from app.maintenance.operations import log_operation


AWG_ENGINES = ("amneziawg", "amneziawg3", "amneziawg31")
DEFAULT_DNS = "1.1.1.1"


class SharedAwgDnsError(ValueError):
    pass


@dataclass(frozen=True)
class SharedAwgDns:
    dns: str
    consistent: bool
    values: dict[str, str]


def normalize_dns(value: object) -> str:
    raw = str(value or "").strip()
    tokens = [item.strip() for item in raw.split(",") if item.strip()]
    if not tokens or len(tokens) > 4:
        raise SharedAwgDnsError("Укажите от одного до четырёх DNS-адресов")
    try:
        normalized = [str(ipaddress.ip_address(item)) for item in tokens]
    except ValueError as exc:
        raise SharedAwgDnsError("DNS должен быть IPv4- или IPv6-адресом") from exc
    return ", ".join(normalized)


def _json_object(raw: object) -> dict:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def get_shared_awg_dns() -> SharedAwgDns:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT engine, config_json FROM connection_settings "
            "WHERE engine IN ('amneziawg', 'amneziawg3', 'amneziawg31')"
        ).fetchall()
    values = {
        str(row["engine"]): str(_json_object(row["config_json"]).get("dns") or DEFAULT_DNS)
        for row in rows
    }
    for engine in AWG_ENGINES:
        values.setdefault(engine, DEFAULT_DNS)
    dns = values["amneziawg"]
    return SharedAwgDns(
        dns=dns,
        consistent=len(set(values.values())) == 1,
        values=values,
    )


def set_shared_awg_dns(value: object) -> SharedAwgDns:
    dns = normalize_dns(value)
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT engine, config_json FROM connection_settings "
            "WHERE engine IN ('amneziawg', 'amneziawg3', 'amneziawg31')"
        ).fetchall()
        settings = {str(row["engine"]): row["config_json"] for row in rows}
        missing = [engine for engine in AWG_ENGINES if engine not in settings]
        if missing:
            raise SharedAwgDnsError("Отсутствуют настройки: " + ", ".join(missing))

        for engine in AWG_ENGINES:
            config = _json_object(settings[engine])
            config["dns"] = dns
            connection.execute(
                """
                UPDATE connection_settings
                SET config_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE engine = ?
                """,
                (json.dumps(config, ensure_ascii=False, sort_keys=True), engine),
            )

        credentials = connection.execute(
            "SELECT id, config_json FROM device_credentials "
            "WHERE engine IN ('amneziawg', 'amneziawg3', 'amneziawg31')"
        ).fetchall()
        for row in credentials:
            config = _json_object(row["config_json"])
            config["dns"] = dns
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (json.dumps(config, ensure_ascii=False, sort_keys=True), int(row["id"])),
            )

    log_operation(
        action="connection.awg_dns.update",
        target="connection:awg",
        message=f"DNS клиентских профилей AWG обновлён: {dns}",
    )
    return get_shared_awg_dns()
