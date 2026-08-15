from __future__ import annotations

import json
import platform
from datetime import datetime, timezone

from app.clients.repository import count_clients, list_clients
from app.config import load_config
from app.connections.service import list_connections
from app.db import get_database_path
from app.hostd.client import hostd_health
from app.maintenance.backups import list_backups
from app.maintenance.health import collect_health_checks, health_summary
from app.maintenance.operations import list_operations, log_operation
from app.mihomo.service import overview as mihomo_overview
from app.routing.templates import overview as routing_templates_overview
from app.security.tls import overview as security_tls_overview
from app.routing.geofiles import overview as geofiles_overview
from app.version import get_release_manifest, get_version
from app.xray.salamander_diagnostics import inspect as salamander_diagnostics


def build_diagnostic_report() -> dict:
    config = load_config()
    database_path = get_database_path()
    clients = list_clients()
    connections = list_connections()
    backups = list_backups()
    operations = list_operations(limit=50)
    error_operations = [item for item in operations if item.status != "ok"]
    last_error = error_operations[0] if error_operations else None
    health_checks = collect_health_checks()
    hostd = hostd_health()
    hysteria2_salamander = salamander_diagnostics()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "service": "sg-gateway-panel",
        "version": get_version(),
        "release": get_release_manifest(),
        "environment": config.environment,
        "server": {
            "name": config.server_name,
            "public_address": config.public_address,
            "country_code": config.country_code,
        },
        "health": health_summary(),
        "hostd": {
            "url": config.hostd_url,
            "status": hostd.status,
            "message": hostd.message,
            "payload": hostd.payload,
        },
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
        },
        "paths": {
            "data_dir": str(config.data_dir),
            "log_dir": str(config.log_dir),
            "database": str(database_path),
            "database_exists": database_path.exists(),
        },
        "summary": {
            "clients": count_clients(),
            "backups": len(backups),
            "operations": len(operations),
            "operation_errors": len(error_operations),
            "last_error": (
                {
                    "action": last_error.action,
                    "target": last_error.target,
                    "message": last_error.message,
                    "created_at": last_error.created_at,
                }
                if last_error
                else None
            ),
        },
        "health_checks": [
            {
                "name": item.name,
                "status": item.status,
                "message": item.message,
            }
            for item in health_checks
        ],
        "geofiles": geofiles_overview(),
        "routing_templates": routing_templates_overview(),
        "tls": security_tls_overview(),
        "mihomo": mihomo_overview(),
        "hysteria2_salamander": hysteria2_salamander,
        "connections": [
            {
                "name": item.name,
                "label": item.label,
                "status": item.status,
                "port": item.port,
                "clients": item.clients,
                "note": item.note,
            }
            for item in connections
        ],
        "clients": [
            {
                "id": item.id,
                "name": item.name,
                "enabled": item.enabled,
                "expires_at": item.expires_at,
                "amneziawg": item.awg_status,
                "xray": item.xray_status,
            }
            for item in clients
        ],
        "backups": [
            {
                "name": item.name,
                "size_bytes": item.size_bytes,
                "created_at": item.created_at,
                "kind": item.kind,
            }
            for item in backups
        ],
        "operations": [
            {
                "id": item.id,
                "action": item.action,
                "target": item.target,
                "status": item.status,
                "message": item.message,
                "created_at": item.created_at,
            }
            for item in operations
        ],
    }


def build_diagnostic_report_json() -> str:
    report = build_diagnostic_report()
    log_operation(
        action="diagnostics.download",
        target="diagnostics:report",
        message="Скачан диагностический отчёт",
    )
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
