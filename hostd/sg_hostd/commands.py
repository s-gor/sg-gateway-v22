from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from sg_hostd.operation_jobs import (
    rollback_xray_runtime,
    run_tls_maintenance,
    start_tls_issue_job,
    start_xray_apply_job,
    start_xray_update_job,
    start_panel_update_job,
    start_core_update_job,
    start_full_backup_restore_job,
)

from sg_hostd.client_runtime import (
    apply_all_clients,
    apply_split_mihomo_singbox_runtime,
    apply_xray_runtime,
    test_xray_candidate,
)

from sg_hostd.privileged_runtime import execute_privileged_action

from sg_hostd.mihomo_runtime import execute_mihomo_action
from sg_hostd.full_backup_runtime import create_full_backup_archive, restore_uploaded_full_backup


@dataclass(frozen=True)
class HostCommandResult:
    command: str
    status: str
    message: str
    payload: dict


def list_allowed_commands() -> list[str]:
    return sorted(_COMMANDS)


def execute_command(command: str) -> HostCommandResult:
    handler = _COMMANDS.get(command)
    if handler is None:
        return HostCommandResult(
            command=command,
            status="error",
            message="Command is not allowed",
            payload={},
        )

    return handler()



def _mihomo_hostd_result(
    command: str,
    action: str,
) -> HostCommandResult:
    result = execute_mihomo_action(action)
    return HostCommandResult(
        command=command,
        status=result.status,
        message=result.message,
        payload=result.payload,
    )


def _mihomo_apply() -> HostCommandResult:
    return _mihomo_hostd_result("mihomo.apply", "apply")


def _mihomo_split_apply() -> HostCommandResult:
    try:
        payload = apply_split_mihomo_singbox_runtime()
    except Exception as exc:
        return HostCommandResult(
            command="mihomo.split.apply",
            status="error",
            message=str(exc),
            payload={},
        )
    return HostCommandResult(
        command="mihomo.split.apply",
        status="ok" if payload.get("ok") else "error",
        message=str(payload.get("message") or "Mieru / AnyTLS / TUIC применены"),
        payload={key: value for key, value in payload.items() if key not in {"ok", "message"}},
    )


def _mihomo_test() -> HostCommandResult:
    return _mihomo_hostd_result("mihomo.test", "test")


def _mihomo_restart() -> HostCommandResult:
    return _mihomo_hostd_result("mihomo.restart", "restart")


def _mihomo_rollback() -> HostCommandResult:
    return _mihomo_hostd_result("mihomo.rollback", "rollback")


def _service_is_active(unit: str) -> bool:
    return (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _listener_rows() -> list[list[str]]:
    result = subprocess.run(
        ["ss", "-H", "-lntup"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if result.returncode != 0:
        return []
    return [line.split() for line in result.stdout.splitlines() if line.strip()]


def _listener_is_bound(
    rows: list[list[str]],
    network: str,
    port: int,
    process_name: str,
) -> bool:
    expected_net = network.strip().lower()
    expected_port = str(port)
    expected_process = process_name.strip().lower()
    for parts in rows:
        if len(parts) < 5 or parts[0].lower() != expected_net:
            continue
        local = parts[4]
        actual_port = local.rsplit(":", 1)[-1].rstrip("]")
        if actual_port != expected_port:
            continue
        line = " ".join(parts).lower()
        if expected_process in line:
            return True
    return False


def _mihomo_safe_runtime_status() -> HostCommandResult:
    """Return listener truth without exposing passwords or TLS key material."""

    protocols: dict[str, dict] = {
        "mieru": {"active": False, "port": None, "transport": "TCP", "engine": "mihomo"},
        "anytls": {"active": False, "port": None, "transport": "TCP", "engine": "sing-box"},
        "tuic": {"active": False, "port": None, "transport": "UDP", "engine": "sing-box"},
    }
    rows = _listener_rows()
    mihomo_active = _service_is_active("mihomo.service")
    singbox_active = _service_is_active("sg-gateway-singbox.service")

    mihomo_config = Path("/etc/mihomo/config.yaml")
    if mihomo_active and mihomo_config.is_file():
        try:
            current = ""
            for raw in mihomo_config.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line in {"- name: mieru-in", "name: mieru-in"}:
                    current = "mieru"
                    protocols[current]["engine"] = "mihomo"
                    continue
                if line in {"- name: anytls-in", "name: anytls-in"}:
                    current = "anytls"
                    protocols[current]["engine"] = "mihomo"
                    continue
                if line in {"- name: tuicv5-in", "name: tuicv5-in"}:
                    current = "tuic"
                    protocols[current]["engine"] = "mihomo"
                    continue
                if current and line.startswith("port:"):
                    try:
                        protocols[current]["port"] = int(line.partition(":")[2].strip())
                    except ValueError:
                        pass
                if current == "mieru" and line.startswith("transport:"):
                    value = line.partition(":")[2].strip().upper()
                    protocols[current]["transport"] = "UDP" if value == "UDP" else "TCP"
        except OSError:
            pass

    singbox_config = Path("/etc/sing-box/config.json")
    if singbox_active and singbox_config.is_file():
        try:
            payload = json.loads(singbox_config.read_text(encoding="utf-8"))
            inbounds = payload.get("inbounds") if isinstance(payload, dict) else None
            if isinstance(inbounds, list):
                for inbound in inbounds:
                    if not isinstance(inbound, dict):
                        continue
                    kind = str(inbound.get("type") or "").strip().lower()
                    tag = str(inbound.get("tag") or "").strip().lower()
                    protocol = ""
                    if kind == "anytls" or tag == "sg-anytls-in":
                        protocol = "anytls"
                    elif kind == "tuic" or tag == "sg-tuic-in":
                        protocol = "tuic"
                    if not protocol:
                        continue
                    try:
                        protocols[protocol]["port"] = int(inbound.get("listen_port"))
                    except (TypeError, ValueError):
                        continue
                    protocols[protocol]["engine"] = "sing-box"
                    protocols[protocol]["transport"] = "UDP" if protocol == "tuic" else "TCP"
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    for protocol, item in protocols.items():
        port = item.get("port")
        if not isinstance(port, int) or not (1 <= port <= 65535):
            continue
        engine = str(item.get("engine") or "")
        network = str(item.get("transport") or "TCP").lower()
        process = "sing-box" if engine == "sing-box" else "mihomo"
        service_ok = singbox_active if engine == "sing-box" else mihomo_active
        item["active"] = bool(
            service_ok and _listener_is_bound(rows, network, port, process)
        )

    active_engines = {
        str(item.get("engine"))
        for item in protocols.values()
        if item.get("active")
    }
    if active_engines == {"mihomo", "sing-box"}:
        source = "mihomo+singbox"
    elif active_engines == {"sing-box"}:
        source = "singbox"
    elif active_engines == {"mihomo"}:
        source = "mihomo"
    else:
        source = "none"

    active_count = sum(1 for item in protocols.values() if item.get("active"))
    return HostCommandResult(
        command="mihomo.status",
        status="ok",
        message=f"Mihomo/sing-box runtime: {active_count}/3 listeners active",
        payload={
            "runtime_source": source,
            "listener_active": active_count,
            "listener_total": 3,
            "protocols": protocols,
        },
    )


def _mihomo_status() -> HostCommandResult:
    return _mihomo_safe_runtime_status()


def _sg_gateway_privileged_result(command: str) -> HostCommandResult:
    result = execute_privileged_action(command)
    return HostCommandResult(
        command=command,
        status=result.status,
        message=result.message,
        payload=result.payload,
    )


def _geofiles_check() -> HostCommandResult:
    return _sg_gateway_privileged_result("geofiles.check")


def _geofiles_apply() -> HostCommandResult:
    return _sg_gateway_privileged_result("geofiles.apply")


def _geofiles_rollback() -> HostCommandResult:
    return _sg_gateway_privileged_result("geofiles.rollback")


def _routing_apply() -> HostCommandResult:
    return _sg_gateway_privileged_result("routing.apply")


def _routing_rollback() -> HostCommandResult:
    return _sg_gateway_privileged_result("routing.rollback")


def _warp_install() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.install")


def _warp_recreate() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.recreate")


def _warp_enable() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.enable")


def _warp_disable() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.disable")


def _warp_remove() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.remove")


def _warp_test() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.test")


def _warp_export_json() -> HostCommandResult:
    return _sg_gateway_privileged_result("warp.export_json")


def _tls_renew() -> HostCommandResult:
    try:
        payload = run_tls_maintenance("renew")
        return HostCommandResult(
            command="tls.renew",
            status="ok",
            message=str(payload.get("message") or "Сертификат проверен"),
            payload={
                key: value
                for key, value in payload.items()
                if key not in {"ok", "message"}
            },
        )
    except Exception as exc:
        return HostCommandResult(
            command="tls.renew",
            status="error",
            message=str(exc),
            payload={},
        )


def _tls_rollback() -> HostCommandResult:
    try:
        payload = run_tls_maintenance("rollback")
        return HostCommandResult(
            command="tls.rollback",
            status="ok",
            message=str(payload.get("message") or "HTTPS-конфигурация восстановлена"),
            payload={
                key: value
                for key, value in payload.items()
                if key not in {"ok", "message"}
            },
        )
    except Exception as exc:
        return HostCommandResult(
            command="tls.rollback",
            status="error",
            message=str(exc),
            payload={},
        )


def _clients_apply() -> HostCommandResult:
    try:
        payload = apply_all_clients()
    except Exception as exc:
        return HostCommandResult(
            command="clients.apply",
            status="error",
            message=str(exc),
            payload={},
        )

    return HostCommandResult(
        command="clients.apply",
        status="ok" if payload.get("ok") else "error",
        message=str(payload.get("message") or "Client runtime applied"),
        payload={
            key: value
            for key, value in payload.items()
            if key not in {"ok", "message"}
        },
    )


def _tls_issue_start() -> HostCommandResult:
    try:
        payload = start_tls_issue_job()
        return HostCommandResult(
            command="tls.issue.start",
            status="ok",
            message=str(payload.get("message") or "HTTPS job started"),
            payload=payload,
        )
    except Exception as exc:
        return HostCommandResult(
            command="tls.issue.start",
            status="error",
            message=str(exc),
            payload={},
        )


def _xray_apply() -> HostCommandResult:
    try:
        payload = apply_xray_runtime()
    except Exception as exc:
        return HostCommandResult(
            command="xray.apply",
            status="error",
            message=str(exc),
            payload={},
        )
    return HostCommandResult(
        command="xray.apply",
        status="ok" if payload.get("ok") else "error",
        message=str(payload.get("message") or "Xray runtime applied"),
        payload={
            key: value
            for key, value in payload.items()
            if key not in {"ok", "message"}
        },
    )


def _xray_restore_apply() -> HostCommandResult:
    try:
        payload = apply_xray_runtime(force_profiles=True)
    except Exception as exc:
        return HostCommandResult(
            command="xray.restore.apply",
            status="error",
            message=str(exc),
            payload={},
        )
    return HostCommandResult(
        command="xray.restore.apply",
        status="ok" if payload.get("ok") else "error",
        message=str(payload.get("message") or "Restored Xray runtime applied"),
        payload={key: value for key, value in payload.items() if key not in {"ok", "message"}},
    )


def _xray_apply_start() -> HostCommandResult:
    try:
        payload = start_xray_apply_job()
        return HostCommandResult(command="xray.apply.start", status="ok", message=str(payload.get("message") or "Xray job started"), payload=payload)
    except Exception as exc:
        return HostCommandResult(command="xray.apply.start", status="error", message=str(exc), payload={})


def _xray_update_start(channel: str) -> HostCommandResult:
    command = f"xray.update.{channel}.start"
    try:
        payload = start_xray_update_job(channel)
        return HostCommandResult(
            command=command,
            status="ok",
            message=str(payload.get("message") or "Xray update job started"),
            payload=payload,
        )
    except Exception as exc:
        return HostCommandResult(command=command, status="error", message=str(exc), payload={})


def _xray_update_stable_start() -> HostCommandResult:
    return _xray_update_start("stable")


def _xray_update_prerelease_start() -> HostCommandResult:
    return _xray_update_start("prerelease")




def _panel_update_start() -> HostCommandResult:
    try:
        payload = start_panel_update_job()
        return HostCommandResult(command="panel.update.start", status="ok", message=str(payload.get("message") or "Panel update job started"), payload=payload)
    except Exception as exc:
        return HostCommandResult(command="panel.update.start", status="error", message=str(exc), payload={})


def _core_update_start(engine: str) -> HostCommandResult:
    command = f"core.update.{engine}.start"
    try:
        payload = start_core_update_job(engine)
        return HostCommandResult(command=command, status="ok", message=str(payload.get("message") or "Core update job started"), payload=payload)
    except Exception as exc:
        return HostCommandResult(command=command, status="error", message=str(exc), payload={})


def _core_update_mihomo_start() -> HostCommandResult:
    return _core_update_start("mihomo")


def _core_update_sing_box_start() -> HostCommandResult:
    return _core_update_start("sing-box")


def _core_update_wgcf_start() -> HostCommandResult:
    return _core_update_start("wgcf")

def _xray_runtime_test() -> HostCommandResult:
    payload = test_xray_candidate()
    return HostCommandResult(command="xray.test", status="ok" if payload.get("ok") else "error", message=str(payload.get("message") or "Xray test"), payload=payload)


def _xray_runtime_rollback() -> HostCommandResult:
    try:
        payload = rollback_xray_runtime()
        return HostCommandResult(command="xray.rollback", status="ok", message=str(payload.get("message") or "Xray rollback complete"), payload=payload)
    except Exception as exc:
        return HostCommandResult(command="xray.rollback", status="error", message=str(exc), payload={})

def _probe(command: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _awg_status() -> HostCommandResult:
    awg = shutil.which("awg")
    if not awg:
        return HostCommandResult(
            command="awg.status",
            status="error",
            message="AmneziaWG runtime не установлен: команда awg не найдена",
            payload={"interface": "awg0", "ready": False, "connected": False},
        )

    module_ready = _probe(["modinfo", "amneziawg"]).returncode == 0
    if not module_ready:
        return HostCommandResult(
            command="awg.status",
            status="error",
            message="AmneziaWG runtime не готов: kernel module amneziawg не найден",
            payload={"interface": "awg0", "ready": False, "connected": False},
        )

    service_active = _probe(["systemctl", "is-active", "--quiet", "sg-gateway-awg.service"]).returncode == 0
    interface_active = _probe(["ip", "link", "show", "awg0"]).returncode == 0
    if service_active != interface_active:
        return HostCommandResult(
            command="awg.status",
            status="warning",
            message="AmneziaWG runtime установлен, но состояние sg-gateway-awg.service и awg0 не совпадает",
            payload={"interface": "awg0", "ready": True, "connected": interface_active},
        )

    message = (
        "AmneziaWG runtime готов; интерфейс awg0 активен"
        if interface_active
        else "AmneziaWG runtime готов; активных AmneziaWG-клиентов сейчас нет"
    )
    return HostCommandResult(
        command="awg.status",
        status="ok",
        message=message,
        payload={"interface": "awg0", "ready": True, "connected": interface_active},
    )


def _xray_status() -> HostCommandResult:
    xray = shutil.which("xray") or ("/usr/local/bin/xray" if Path("/usr/local/bin/xray").is_file() else "")
    if not xray:
        return HostCommandResult(
            command="xray.status",
            status="error",
            message="Xray runtime не установлен",
            payload={"ready": False, "connected": False},
        )

    version = _probe([xray, "version"])
    if version.returncode != 0:
        return HostCommandResult(
            command="xray.status",
            status="error",
            message="Xray binary найден, но не проходит проверку version",
            payload={"ready": False, "connected": False},
        )

    service_active = _probe(["systemctl", "is-active", "--quiet", "xray.service"]).returncode == 0
    first_line = (version.stdout or version.stderr or "Xray").splitlines()[0].strip()
    message = (
        f"{first_line}; xray.service активен"
        if service_active
        else f"{first_line}; runtime готов, служба сейчас не используется"
    )
    return HostCommandResult(
        command="xray.status",
        status="ok",
        message=message,
        payload={"ready": True, "connected": service_active},
    )


def _xray_salamander_status() -> HostCommandResult:
    """Inspect root-only Xray config and return no secret material."""
    from app.connections.settings import get_connection_settings

    path = Path("/usr/local/etc/xray/config.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HostCommandResult(
            command="xray.salamander.status", status="error",
            message="Xray config not found", payload={"readable": False},
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return HostCommandResult(
            command="xray.salamander.status", status="error",
            message=f"Xray config is unreadable: {exc}", payload={"readable": False},
        )

    inbound = None
    for item in payload.get("inbounds", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict) and str(item.get("tag") or "") == "sg-hysteria2":
            inbound = item
            break

    live_active = False
    live_password = ""
    if isinstance(inbound, dict):
        stream = inbound.get("streamSettings")
        finalmask = stream.get("finalmask") if isinstance(stream, dict) else None
        udp = finalmask.get("udp") if isinstance(finalmask, dict) else None
        if isinstance(udp, list):
            for item in udp:
                if not isinstance(item, dict) or str(item.get("type") or "").strip().lower() != "salamander":
                    continue
                live_active = True
                settings = item.get("settings")
                if isinstance(settings, dict):
                    live_password = str(settings.get("password") or "")
                break

    db = get_connection_settings("xray")
    db_config = dict(db.config)
    db_mode = str(db_config.get("hysteria2_obfs_mode") or "none").strip().lower()
    db_password = str(db_config.get("hysteria2_obfs_password") or "")
    database_enabled = db_mode == "salamander"
    password_matches = bool(database_enabled and live_active and db_password and live_password and db_password == live_password)

    return HostCommandResult(
        command="xray.salamander.status", status="ok",
        message="Hysteria2 Salamander runtime inspected",
        payload={
            "readable": True,
            "inbound_present": inbound is not None,
            "finalmask_udp_active": live_active,
            "live_password_configured": bool(live_password),
            "password_matches_database": password_matches,
        },
    )


def _nftables_status() -> HostCommandResult:
    return HostCommandResult(
        command="nftables.status",
        status="warning",
        message="nftables integration is not connected yet",
        payload={"connected": False},
    )


def _system_diagnostics() -> HostCommandResult:
    return HostCommandResult(
        command="system.diagnostics",
        status="ok",
        message="Host helper mock diagnostics are available",
        payload={
            "mode": "mock",
            "shell": "disabled",
            "arbitrary_commands": False,
        },
    )


def _full_backup_create() -> HostCommandResult:
    try:
        payload = create_full_backup_archive()
    except Exception as exc:
        return HostCommandResult(
            command="backup.full.create", status="error",
            message=f"Не удалось создать полный backup: {exc}", payload={},
        )
    return HostCommandResult(
        command="backup.full.create", status="ok",
        message=f"Полный backup создан: {payload.get('name', '')}", payload=payload,
    )


def _full_backup_restore_start() -> HostCommandResult:
    try:
        payload = start_full_backup_restore_job()
    except Exception as exc:
        return HostCommandResult(
            command="backup.full.restore.start", status="error",
            message=f"Не удалось запустить Full Restore: {exc}", payload={},
        )
    return HostCommandResult(
        command="backup.full.restore.start", status="ok",
        message="Full Restore запущен в фоновом терминале", payload=payload,
    )


def _full_backup_restore() -> HostCommandResult:
    try:
        payload = restore_uploaded_full_backup()
    except Exception as exc:
        return HostCommandResult(
            command="backup.full.restore", status="error",
            message=f"Полный restore отменён: {exc}", payload={},
        )
    return HostCommandResult(
        command="backup.full.restore", status="ok",
        message="Полный backup восстановлен; службы будут перезапущены", payload=payload,
    )


_COMMANDS: dict[str, Callable[[], HostCommandResult]] = {
    "tls.issue.start": _tls_issue_start,
    "xray.apply": _xray_apply,
    "xray.restore.apply": _xray_restore_apply,
    "xray.apply.start": _xray_apply_start,
    "xray.update.stable.start": _xray_update_stable_start,
    "xray.update.prerelease.start": _xray_update_prerelease_start,
    "panel.update.start": _panel_update_start,
    "core.update.mihomo.start": _core_update_mihomo_start,
    "core.update.sing-box.start": _core_update_sing_box_start,
    "core.update.wgcf.start": _core_update_wgcf_start,
    "xray.test": _xray_runtime_test,
    "xray.rollback": _xray_runtime_rollback,
    "clients.apply": _clients_apply,
    "geofiles.check": _geofiles_check,
    "geofiles.apply": _geofiles_apply,
    "geofiles.rollback": _geofiles_rollback,
    "routing.apply": _routing_apply,
    "routing.rollback": _routing_rollback,
    "warp.install": _warp_install,
    "warp.recreate": _warp_recreate,
    "warp.enable": _warp_enable,
    "warp.disable": _warp_disable,
    "warp.remove": _warp_remove,
    "warp.test": _warp_test,
    "warp.export_json": _warp_export_json,
    "tls.renew": _tls_renew,
    "tls.rollback": _tls_rollback,
    "mihomo.apply": _mihomo_apply,
    "mihomo.split.apply": _mihomo_split_apply,
    "mihomo.test": _mihomo_test,
    "mihomo.restart": _mihomo_restart,
    "mihomo.rollback": _mihomo_rollback,
    "mihomo.status": _mihomo_status,
    "awg.status": _awg_status,
    "xray.status": _xray_status,
    "xray.salamander.status": _xray_salamander_status,
    "nftables.status": _nftables_status,
    "system.diagnostics": _system_diagnostics,
    "backup.full.create": _full_backup_create,
    "backup.full.restore.start": _full_backup_restore_start,
    "backup.full.restore": _full_backup_restore,
}