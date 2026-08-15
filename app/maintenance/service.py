from __future__ import annotations

from dataclasses import dataclass

from app.clients.repository import count_clients
from app.config import load_config
from app.connections.service import list_connections
from app.db import get_database_path
from app.maintenance.backups import list_backups
from app.maintenance.health import health_summary
from app.maintenance.operations import count_operations
from app.routing.warp import overview as warp_overview


@dataclass(frozen=True)
class DiagnosticItem:
    label: str
    value: str
    state: str


def collect_diagnostics() -> list[DiagnosticItem]:
    config = load_config()
    database_path = get_database_path()
    connections = list_connections()
    backups = list_backups()
    health = health_summary()
    warp = warp_overview()

    return [
        DiagnosticItem("Состояние", {"ok": "НОРМА", "warning": "ПРЕДУПРЕЖДЕНИЕ", "error": "ОШИБКА"}.get(health, health.upper()), "ok" if health == "ok" else "idle"),
        DiagnosticItem("Режим панели", config.environment, "ok"),
        DiagnosticItem("База данных", "Готова" if database_path.exists() else "Будет создана", "ok"),
        DiagnosticItem("Путь к базе данных", str(database_path), "idle"),
        DiagnosticItem("Клиенты", str(count_clients()), "idle"),
        DiagnosticItem("Клиенты AmneziaWG", str(connections[0].clients), "idle"),
        DiagnosticItem("Клиенты Xray", str(connections[1].clients), "idle"),
        DiagnosticItem("WARP", warp.get("status_label", "Не установлен"), "ok" if warp.get("enabled") else "idle"),
        DiagnosticItem("Резервные копии", str(len(backups)), "ok" if backups else "idle"),
        DiagnosticItem("Операции", str(count_operations()), "ok"),
    ]
