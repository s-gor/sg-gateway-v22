from __future__ import annotations

import os
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class RuntimeContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Requirement:
    label: str
    alternatives: tuple[str, ...]
    executable: bool = False


@dataclass(frozen=True)
class RuntimeSpec:
    engine: str
    title: str
    critical: bool
    requirements: tuple[Requirement, ...]


def _unit_paths(name: str) -> tuple[str, ...]:
    return (
        f"/etc/systemd/system/{name}",
        f"/usr/lib/systemd/system/{name}",
        f"/lib/systemd/system/{name}",
    )


DEFAULT_SPECS: dict[str, RuntimeSpec] = {
    "amneziawg": RuntimeSpec(
        "amneziawg",
        "AWG2",
        True,
        (
            Requirement("awg", ("/usr/bin/awg", "/usr/local/bin/awg"), True),
            Requirement("awg-quick", ("/usr/bin/awg-quick", "/usr/local/bin/awg-quick"), True),
            Requirement("sg-gateway-awg.service", _unit_paths("sg-gateway-awg.service")),
        ),
    ),
    "amneziawg3": RuntimeSpec(
        "amneziawg3",
        "AWG3",
        True,
        (
            Requirement("awg", ("/opt/sg-gateway/awg3/bin/awg",), True),
            Requirement("awg-quick", ("/opt/sg-gateway/awg3/bin/awg-quick",), True),
            Requirement("amneziawg-go", ("/opt/sg-gateway/awg3/bin/amneziawg-go",), True),
            Requirement(
                "AWG3 helper",
                ("/opt/sg-gateway/deploy/sg-gateway-awg3-userspace.sh",),
                True,
            ),
            Requirement("sg-gateway-awg3.service", _unit_paths("sg-gateway-awg3.service")),
        ),
    ),
    "xray": RuntimeSpec(
        "xray",
        "Xray",
        True,
        (
            Requirement("xray", ("/usr/local/bin/xray", "/usr/bin/xray"), True),
            Requirement("xray.service", _unit_paths("xray.service")),
        ),
    ),
    "mihomo": RuntimeSpec(
        "mihomo",
        "Mihomo / Mieru",
        False,
        (
            Requirement("mihomo", ("/usr/local/bin/mihomo", "/usr/bin/mihomo"), True),
            Requirement("mihomo.service", _unit_paths("mihomo.service")),
        ),
    ),
    "anytls": RuntimeSpec(
        "anytls",
        "sing-box / AnyTLS",
        False,
        (
            Requirement("sing-box", ("/usr/local/bin/sing-box", "/usr/bin/sing-box"), True),
            Requirement("sg-gateway-singbox.service", _unit_paths("sg-gateway-singbox.service")),
        ),
    ),
    "tuic": RuntimeSpec(
        "tuic",
        "sing-box / TUIC",
        False,
        (
            Requirement("sing-box", ("/usr/local/bin/sing-box", "/usr/bin/sing-box"), True),
            Requirement("sg-gateway-singbox.service", _unit_paths("sg-gateway-singbox.service")),
        ),
    ),
}

ENGINE_ALIASES = {
    "mieru": "mihomo",
}

AWG3_CONFIG_PATH = Path("/etc/amnezia/amneziawg/awg3.conf")
AWG3_SERVICE = "sg-gateway-awg3.service"


def _active_engines(database_path: Path) -> set[str]:
    if not database_path.is_file():
        raise RuntimeContractError(f"Runtime Contract: база не найдена: {database_path}")

    database = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True, timeout=15)
    try:
        try:
            rows = database.execute(
                """
                SELECT DISTINCT dc.engine
                FROM device_credentials dc
                JOIN devices d ON d.id = dc.device_id
                JOIN clients c ON c.id = d.client_id
                WHERE dc.status != 'disabled'
                  AND c.enabled = 1
                  AND d.enabled = 1
                """
            ).fetchall()
        except sqlite3.Error:
            rows = database.execute(
                "SELECT DISTINCT engine FROM device_credentials WHERE engine IS NOT NULL"
            ).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeContractError(f"Runtime Contract: не удалось прочитать список движков: {exc}") from exc
    finally:
        database.close()

    result: set[str] = set()
    for row in rows:
        raw = str(row[0] or "").strip().lower()
        if raw:
            result.add(ENGINE_ALIASES.get(raw, raw))
    return result


def _requirement_ready(requirement: Requirement) -> tuple[bool, str]:
    for raw in requirement.alternatives:
        path = Path(raw)
        if not path.is_file():
            continue
        if requirement.executable and not os.access(path, os.X_OK):
            continue
        return True, str(path)
    return False, requirement.alternatives[0]


def _service_active(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _awg3_deployment_state(*, active: bool) -> dict:
    """Operational AWG3 state that never blocks the prerequisite contract.

    Runtime files/unit are prerequisites for Client Apply. Generated awg3.conf
    and an active service are outputs of Client Apply, so folding them into the
    base `ready` flag would create a circular recovery dependency.
    """

    if not active:
        return {
            "required": False,
            "ready": True,
            "missing": [],
            "config_ready": False,
            "service_active": False,
        }

    config_ready = False
    try:
        config_ready = AWG3_CONFIG_PATH.is_file() and AWG3_CONFIG_PATH.stat().st_size > 0
    except OSError:
        config_ready = False
    service_active = _service_active(AWG3_SERVICE)

    missing: list[str] = []
    if not config_ready:
        missing.append(f"generated config: {AWG3_CONFIG_PATH}")
    if not service_active:
        missing.append(f"active service: {AWG3_SERVICE}")
    return {
        "required": True,
        "ready": not missing,
        "missing": missing,
        "config_ready": config_ready,
        "service_active": service_active,
    }


def inspect_runtime_contract(
    *,
    database_path: Path | str = "/var/lib/sg-gateway/sg-gateway.sqlite",
    strict_optional: bool = False,
    include_all_critical: bool = False,
    specs: Mapping[str, RuntimeSpec] | None = None,
) -> dict:
    selected_specs = dict(specs or DEFAULT_SPECS)
    active = _active_engines(Path(database_path))
    target_engines = {engine for engine in active if engine in selected_specs}
    if include_all_critical:
        target_engines.update(
            engine for engine, spec in selected_specs.items() if spec.critical
        )

    checks: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []
    for engine in sorted(target_engines):
        spec = selected_specs[engine]
        missing: list[str] = []
        resolved: dict[str, str] = {}
        for requirement in spec.requirements:
            ready, detail = _requirement_ready(requirement)
            if ready:
                resolved[requirement.label] = detail
            else:
                missing.append(f"{requirement.label}: {detail}")

        item = {
            "engine": engine,
            "title": spec.title,
            "critical": spec.critical,
            "active": engine in active,
            "ready": not missing,
            "missing": missing,
            "resolved": resolved,
        }
        if engine == "amneziawg3":
            item["deployment"] = _awg3_deployment_state(active=engine in active)
        checks.append(item)
        if missing:
            if spec.critical or strict_optional:
                failures.append(item)
            else:
                warnings.append(item)

    if failures:
        parts: list[str] = []
        for item in failures:
            missing = ", ".join(item["missing"])
            if item["engine"] == "amneziawg3":
                parts.append(f"AWG3 требует восстановления — отсутствует {missing}")
            else:
                parts.append(f"{item['title']} не готов — отсутствует {missing}")
        message = (
            "Runtime Contract не пройден. Настройки и клиенты не изменены. "
            + "; ".join(parts)
        )
    else:
        message = "Runtime Contract: обязательные runtime-компоненты готовы"

    return {
        "ok": not failures,
        "message": message,
        "active_engines": sorted(active),
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "strict_optional": strict_optional,
        "include_all_critical": include_all_critical,
    }


def assert_runtime_contract(**kwargs) -> dict:
    result = inspect_runtime_contract(**kwargs)
    if not result.get("ok"):
        raise RuntimeContractError(str(result.get("message") or "Runtime Contract не пройден"))
    return result
