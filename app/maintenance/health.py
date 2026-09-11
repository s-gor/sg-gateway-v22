from __future__ import annotations

from dataclasses import dataclass
import time

from app.config import load_config
from app.connections.settings import list_connection_settings
from app.db import get_database_path
from app.hostd.client import hostd_health, run_hostd_command
from app.maintenance.backups import get_backup_dir
from app.mihomo.service import health_status as mihomo_health_status
from app.security.tls import health_status as tls_health_status
from app.routing.geofiles import health_status as geofiles_health_status
from app.xray.salamander_diagnostics import inspect as salamander_diagnostics


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    message: str


_HEALTH_SUMMARY_TTL_SECONDS = 15.0
_HEALTH_SUMMARY_CACHE: dict[str, object] = {
    "updated_at": 0.0,
    "value": None,
}


def _summary_value(checks: list[HealthCheck]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _remember_summary(checks: list[HealthCheck]) -> str:
    value = _summary_value(checks)
    _HEALTH_SUMMARY_CACHE["updated_at"] = time.monotonic()
    _HEALTH_SUMMARY_CACHE["value"] = value
    return value


def collect_health_checks() -> list[HealthCheck]:
    config = load_config()
    database_path = get_database_path()
    backup_dir = get_backup_dir()
    checks = [
        HealthCheck(
            name="База данных",
            status="ok" if database_path.exists() else "warning",
            message=str(database_path) if database_path.exists() else "База данных будет создана при первом использовании",
        ),
        HealthCheck(
            name="Каталог резервных копий",
            status="ok" if backup_dir.exists() else "error",
            message=str(backup_dir),
        ),
        HealthCheck(
            name="Каталог данных",
            status="ok" if config.data_dir.exists() else "warning",
            message=str(config.data_dir),
        ),
        _hostd_check(),
        _mihomo_check(),
        _tls_check(),
        _geofiles_check(),
    ]

    checks.extend(_connection_checks())
    salamander = _salamander_check()
    if salamander is not None:
        checks.append(salamander)
    _remember_summary(checks)
    return checks


def cached_health_summary(default: str = "warning") -> str:
    """Return the last known health status without starting runtime diagnostics."""
    value = _HEALTH_SUMMARY_CACHE.get("value")
    if isinstance(value, str) and value in {"ok", "warning", "error"}:
        return value
    return default


def health_summary() -> str:
    now = time.monotonic()
    updated_at = float(_HEALTH_SUMMARY_CACHE.get("updated_at") or 0.0)
    value = _HEALTH_SUMMARY_CACHE.get("value")
    if (
        isinstance(value, str)
        and value in {"ok", "warning", "error"}
        and now - updated_at < _HEALTH_SUMMARY_TTL_SECONDS
    ):
        return value
    return _remember_summary(collect_health_checks())



def _geofiles_check() -> HealthCheck:
    result = geofiles_health_status()
    return HealthCheck(
        name="GeoFiles Xray",
        status=result["status"],
        message=result["message"],
    )


def _tls_check() -> HealthCheck:
    result = tls_health_status()
    return HealthCheck(
        name="Domain / HTTPS",
        status=result["status"],
        message=result["message"],
    )


def _mihomo_check() -> HealthCheck:
    result = mihomo_health_status()
    return HealthCheck(
        name="Mihomo Multi-Protocol",
        status=result["status"],
        message=result["message"],
    )


def _salamander_check() -> HealthCheck | None:
    result = salamander_diagnostics()
    if result["mode"] != "salamander":
        return None
    if result["consistent"] and result["finalmask_udp_active"]:
        return HealthCheck(
            name="Hysteria2 Salamander",
            status="ok",
            message="FinalMask UDP active; password configured; client URI parameters present",
        )
    details = "; ".join(result["safe_lines"])
    if result.get("live_config_error"):
        details += f"; {result['live_config_error']}"
    return HealthCheck(
        name="Hysteria2 Salamander",
        status="error",
        message=details,
    )


def _hostd_check() -> HealthCheck:
    result = hostd_health()
    return HealthCheck(
        name="sg-hostd",
        status=result.status,
        message=result.message,
    )


def _connection_checks() -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    settings_map = list_connection_settings(("amneziawg31", "xray"))

    awg31 = settings_map["amneziawg31"]
    awg31_key = awg31.config.get("server_public_key", "")
    awg31_host = run_hostd_command("awg31.status")
    checks.append(
        HealthCheck(
            name="Настройки AmneziaWG 3.1",
            status="warning" if "PLACEHOLDER" in awg31_key else awg31_host.status,
            message=f"{awg31.host}:{awg31.port}; hostd: {awg31_host.message}",
        )
    )

    xray = settings_map["xray"]
    xray_key = xray.config.get("public_key", "")
    xray_short_id = xray.config.get("short_id", "")
    xray_ready = "PLACEHOLDER" not in xray_key and "PLACEHOLDER" not in xray_short_id
    xray_host = run_hostd_command("xray.status")
    checks.append(
        HealthCheck(
            name="Настройки Xray Reality",
            status=xray_host.status if xray_ready else "warning",
            message=(
                f"{xray.host}:{xray.port}, "
                f"SNI {xray.config.get('server_name', 'не задано')}; "
                f"hostd: {xray_host.message}"
            ),
        )
    )

    return checks
