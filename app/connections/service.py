from __future__ import annotations

from dataclasses import dataclass

from app.connections.geoip_country import lookup_country_code
from app.connections.public_endpoint import public_host
from app.connections.settings import get_connection_settings
from app.db import connect

COUNTRY_NAMES = {
    "nl": "Нидерланды",
    "de": "Германия",
    "fi": "Финляндия",
    "fr": "Франция",
    "gb": "Великобритания",
    "pl": "Польша",
    "us": "США",
    "ca": "Канада",
    "sg": "Сингапур",
    "tr": "Турция",
    "il": "Израиль",
    "unknown": "Страна не выбрана",
}


def normalize_country_code(value: str | None) -> str:
    code = (value or "unknown").strip().lower()
    return code if code in COUNTRY_NAMES else "unknown"


def country_name(code: str | None) -> str:
    return COUNTRY_NAMES.get(normalize_country_code(code), COUNTRY_NAMES["unknown"])


@dataclass(frozen=True)
class ConnectionSummary:
    name: str
    label: str
    status: str
    port: str
    clients: int
    note: str
    country_code: str
    country_name: str
    public_host: str


def _country_for(settings) -> str:
    configured = normalize_country_code(str(settings.config.get("country_code") or "unknown"))
    if configured != "unknown":
        return configured
    detected = lookup_country_code(settings.host)
    return detected if detected != "unknown" else "unknown"


def _summary(name: str, label: str, counts: dict[str, int], *, note: str = "") -> ConnectionSummary:
    settings = get_connection_settings(name)
    host = public_host(settings.host)
    country = _country_for(settings)
    return ConnectionSummary(
        name=name,
        label=label,
        status="Configured" if settings.enabled else "Disabled",
        port=f"UDP {settings.port}" if name == "amneziawg31" else f"TCP {settings.port}",
        clients=counts.get(name, 0),
        note=note or f"Адрес: {host}:{settings.port}",
        country_code=country,
        country_name=country_name(country),
        public_host=host,
    )


def list_connections() -> list[ConnectionSummary]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT engine, COUNT(*) AS total
            FROM device_credentials
            WHERE engine NOT IN ('amneziawg', 'amneziawg3')
            GROUP BY engine
            """
        ).fetchall()

    counts = {str(row["engine"]): int(row["total"]) for row in rows}

    xray = _summary("xray", "Xray Reality", counts)

    mihomo_settings = get_connection_settings("mihomo")
    mihomo_host = public_host(mihomo_settings.host)
    mihomo_country = _country_for(mihomo_settings)
    mihomo = ConnectionSummary(
        name="mihomo",
        label="Mihomo Multi-Protocol",
        status="Configured" if mihomo_settings.enabled else "Disabled",
        port=(
            f"TCP {mihomo_settings.config.get('mieru_port', mihomo_settings.port)} / "
            f"{mihomo_settings.config.get('anytls_port', 8443)} · "
            f"UDP {mihomo_settings.config.get('tuic_port', 10443)}"
        ),
        clients=counts.get("mihomo", 0),
        note=f"Адрес: {mihomo_host}; Mieru / AnyTLS / TUIC v5",
        country_code=mihomo_country,
        country_name=country_name(mihomo_country),
        public_host=mihomo_host,
    )

    awg31 = _summary("amneziawg31", "AmneziaWG 3.1", counts)

    # AWG2/AWG3 are retired. Their legacy settings/credentials may remain in
    # old backups, but they are deliberately absent from the Connections UI.
    return [awg31, xray, mihomo]
