import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from app.clients.access import build_access_cards
from app.clients.exports import (
    build_awg_config,
    build_awg3_config,
    build_mihomo_yaml,
    build_mieru_link,
    build_subscription,
    build_subscription_url,
    build_xray_link,
    is_export_ready,
    build_protocol_export,
    protocol_ready,
)
from app.clients.qr import ClientQrError, build_qr_svg
from app.clients.awg31_stage2 import register_awg31
from app.clients.runtime import ClientWorkflowError, apply_clients_runtime
from app.clients.repository import (
    count_clients,
    device_access_tokens,
    create_client,
    create_device,
    delete_client,
    delete_device,
    get_client,
    get_device,
    get_primary_device,
    get_subscription_access,
    list_clients,
    list_devices,
    restore_client_snapshot,
    set_client_enabled,
    set_device_enabled,
    update_client,
    update_device,
    snapshot_client,
)
from app.config import load_config
from app.cpu_activity import collect_cpu_activity
from app.system_activity import collect_system_activity
from app.connections.geoip_country import lookup_country_code
from app.connections.service import list_connections
from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db
from app.help.content import get_topic, list_topics
from app.maintenance.backups import (
    backup_cleanup_preview,
    confirm_restore_runtime,
    create_backup,
    delete_old_backups,
    get_backup,
    list_backups,
    restore_backup_transaction,
    restore_safety_backup,
)
from app.maintenance.full_backups import (
    get_data_backup,
    get_full_backup,
    get_verified_data_backup,
    get_verified_full_backup,
    list_data_backups,
    list_full_backups,
    save_verified_data_backup,
    save_verified_full_backup,
    stage_uploaded_data_backup_for_verification,
    stage_uploaded_full_backup_for_verification,
    stage_verified_data_backup_for_restore,
    stage_verified_full_backup_for_restore,
)
from app.maintenance.diagnostics import build_diagnostic_report, build_diagnostic_report_json
from app.maintenance.health import collect_health_checks, health_summary
from app.maintenance.operations import list_operations, log_operation
from app.maintenance.service import collect_diagnostics
from app.maintenance.xray_updates import overview as xray_update_overview
from app.maintenance.panel_updates import overview as panel_update_overview
from app.maintenance.core_updates import overview as core_update_overview
from app.routing.geofiles import (
    GeoFilesError,
    apply_candidate,
    overview as geofiles_overview,
    rollback_latest,
    stage_pair,
)
from app.security.tls import overview as tls_overview
from app.security.auth import (
    is_authenticated,
    login_user,
    logout_user,
    password_is_default,
    set_password,
    should_skip_auth,
    verify_password,
)
from app.routing.warp import overview as warp_overview
from app.routing.templates import (
    RoutingTemplateError,
    apply_candidate as apply_routing_template,
    overview as routing_templates_overview,
    rollback_latest as rollback_routing_template,
    stage_template,
    stage_smart_routing,
)
from app.security.tls import (
    TlsError,
    issue_certificate,
    overview as security_tls_overview,
    renew_certificate,
    rollback_latest as rollback_tls,
    stage_request as stage_tls_request,
)
from app.mihomo.service import (
    MihomoError,
    apply_candidate as apply_mihomo_candidate,
    disable_client_deployment,
    ensure_client_deployment,
    overview as mihomo_overview,
    restart_service as restart_mihomo_service,
    rollback_latest as rollback_mihomo,
    rotate_client_credentials,
    save_settings as save_mihomo_settings,
    test_candidate as test_mihomo_candidate,
)
from app.xray.profiles import (
    XrayProfilesError,
    new_salamander_password,
    overview as xray_profiles_overview,
    rollback_transaction as rollback_xray_settings_transaction,
    salamander_secret,
    save as save_xray_profiles,
)
from app.hostd.client import run_hostd_command
from app.security.operation_jobs import read_job as read_operation_job
from app.version import get_release_manifest, get_version


COUNTRY_OPTIONS = [
    ("nl", "Нидерланды"),
    ("de", "Германия"),
    ("fi", "Финляндия"),
    ("fr", "Франция"),
    ("gb", "Великобритания"),
    ("pl", "Польша"),
    ("us", "США"),
    ("ca", "Канада"),
    ("sg", "Сингапур"),
    ("tr", "Турция"),
    ("il", "Израиль"),
    ("unknown", "Страна не выбрана"),
]
COUNTRY_NAMES = dict(COUNTRY_OPTIONS)


# SG_GATEWAY_02206_AWG_ONLY_PROTOCOLS_V3
_CLIENT_SUBSCRIPTION_SOURCES = {"mihomo", "anytls", "tuic"}


def _prepare_client_protocols(values) -> list[str]:
    # Add SG Client only when at least one subscription source is selected.
    protocols: list[str] = []
    for value in values:
        token = str(value or "").strip().lower()
        if not token or token == "sgclient" or token in protocols:
            continue
        protocols.append(token)

    has_subscription_source = any(
        token in _CLIENT_SUBSCRIPTION_SOURCES
        or token == "xray"
        or token.startswith("xray_")
        for token in protocols
    )
    if has_subscription_source:
        protocols.append("sgclient")
    return protocols


def normalize_country_code(value: str | None) -> str:
    code = (value or "unknown").strip().lower()
    if not re.fullmatch(r"[a-z]{2}|unknown", code):
        return "unknown"
    return code if code in COUNTRY_NAMES else "unknown"


def country_name(code: str | None) -> str:
    return COUNTRY_NAMES.get(normalize_country_code(code), COUNTRY_NAMES["unknown"])


def _safe_login_next(value: str | None) -> str:
    target = str(value or "/").strip() or "/"
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return "/"

    stale_client = re.fullmatch(r"/clients/(\d+)", parsed.path)
    if stale_client and get_client(int(stale_client.group(1))) is None:
        return "/clients"
    return target


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(max(0, int(value or 0)))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(value)} B"


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.split()[0]) * 1024
    except OSError:
        return values
    return values


def _process_rss(names: tuple[str, ...]) -> int:
    total = 0
    proc = Path("/proc")
    if not proc.exists():
        return total
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            comm = (item / "comm").read_text(encoding="utf-8").strip().lower()
            if not any(name in comm for name in names):
                continue
            status = (item / "status").read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"VmRSS:\s+(\d+)\s+kB", status)
        if match:
            total += int(match.group(1)) * 1024
    return total


def _resource_state(percent: int) -> tuple[str, str]:
    if percent >= 95:
        return "critical", "Критично"
    if percent >= 85:
        return "high", "Мало свободных ресурсов"
    if percent >= 70:
        return "warning", "Предупреждение"
    return "normal", "Норма"


_DISK_BREAKDOWN_CACHE: dict[str, object] = {
    "updated_at": 0.0,
    "device": None,
    "rows": [],
}


def _allocated_size(path: Path, device: int) -> int:
    try:
        root_stat = path.stat(follow_symlinks=False)
    except OSError:
        return 0

    if root_stat.st_dev != device:
        return 0

    if path.is_file():
        return max(0, int(getattr(root_stat, "st_blocks", 0))) * 512

    if not path.is_dir():
        return 0

    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.st_dev != device or entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += max(0, int(getattr(stat, "st_blocks", 0))) * 512
        except OSError:
            continue
    return total


def _dashboard_disk_breakdown(data_dir: Path, disk_used: int) -> list[dict]:
    now = time.monotonic()
    try:
        device = data_dir.stat().st_dev
    except OSError:
        return []

    force_refresh = False
    try:
        from flask import has_request_context, request
        force_refresh = (
            has_request_context()
            and request.args.get("disk_refresh") == "1"
        )
    except Exception:
        force_refresh = False

    cached_at = float(_DISK_BREAKDOWN_CACHE.get("updated_at") or 0.0)
    cached_device = _DISK_BREAKDOWN_CACHE.get("device")
    cached_rows = _DISK_BREAKDOWN_CACHE.get("rows")
    if (
        not force_refresh
        and cached_device == device
        and isinstance(cached_rows, list)
        and now - cached_at < 60.0
    ):
        return cached_rows

    app_root = Path(__file__).resolve().parents[1]
    backup_dir = data_dir / "backups"
    database_file = data_dir / "sg-gateway.sqlite"
    log_dir = Path("/var/log/sg-gateway")
    geofiles_dir = Path("/usr/local/share/xray")

    data_total = _allocated_size(data_dir, device)
    backup_size = _allocated_size(backup_dir, device)
    database_size = _allocated_size(database_file, device)
    data_misc = max(0, data_total - backup_size - database_size)

    parts = [
        {"key": "gateway", "label": "SG-Gateway", "note": "/opt/sg-gateway",
         "bytes": _allocated_size(app_root, device), "color": "#4f9bff"},
        {"key": "data", "label": "Данные", "note": str(data_dir),
         "bytes": data_misc, "color": "#38c6c2"},
        {"key": "backups", "label": "Резервные копии", "note": str(backup_dir),
         "bytes": backup_size, "color": "#9b7bff"},
        {"key": "database", "label": "База данных", "note": database_file.name,
         "bytes": database_size, "color": "#4ecb86"},
        {"key": "logs", "label": "Логи", "note": str(log_dir),
         "bytes": _allocated_size(log_dir, device), "color": "#e7c45b"},
        {"key": "geofiles", "label": "GeoFiles Xray", "note": str(geofiles_dir),
         "bytes": _allocated_size(geofiles_dir, device), "color": "#f28a5b"},
    ]

    known = sum(max(0, int(item["bytes"])) for item in parts)
    parts.append({
        "key": "other",
        "label": "Система и прочее",
        "note": "Остальное занятое место на разделе",
        "bytes": max(0, int(disk_used) - known),
        "color": "#7890a8",
    })

    parts = [item for item in parts if int(item["bytes"]) > 0]
    parts.sort(key=lambda item: int(item["bytes"]), reverse=True)

    denominator = max(1, int(disk_used))
    rows: list[dict] = []
    for item in parts:
        amount = max(0, int(item["bytes"]))
        percent_value = min(100.0, amount * 100.0 / denominator)
        rows.append({
            "key": item["key"],
            "label": item["label"],
            "note": item["note"],
            "value": _format_bytes(amount),
            "percent": f"{percent_value:.1f}%",
            "percent_value": round(percent_value, 1),
            "bar_width": round(max(2.0, percent_value), 1) if amount else 0,
            "color": item["color"],
        })

    _DISK_BREAKDOWN_CACHE["updated_at"] = now
    _DISK_BREAKDOWN_CACHE["device"] = device
    _DISK_BREAKDOWN_CACHE["rows"] = rows
    return rows

def _disk_filesystem_info(path: Path) -> dict[str, str]:
    resolved = str(path.resolve())
    best_mount = "/"
    best_fstype = "—"

    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"filesystem": best_fstype, "mount_point": best_mount}

    for line in lines:
        fields = line.split()
        if "-" not in fields or len(fields) < 7:
            continue
        sep = fields.index("-")
        if sep + 1 >= len(fields):
            continue

        mount = fields[4]
        mount = (
            mount.replace(r"\040", " ")
                 .replace(r"\011", "\t")
                 .replace(r"\134", "\\")
        )
        candidate = str(Path(mount).resolve())
        inside = (
            resolved == candidate
            or candidate == "/"
            or resolved.startswith(candidate.rstrip("/") + "/")
        )
        if not inside:
            continue

        if len(candidate) >= len(best_mount):
            best_mount = candidate
            best_fstype = fields[sep + 1]

    return {
        "filesystem": best_fstype,
        "mount_point": best_mount,
    }


def _dashboard_resources() -> dict:
    mem = _read_meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    free = mem.get("MemFree", 0)
    used = max(0, total - available)
    used_percent = round(used * 100 / total) if total else 0
    memory_state, memory_label = _resource_state(used_percent)

    panel_rss = _process_rss(("python", "waitress"))
    web_rss = _process_rss(("nginx",))

    # Build one non-overlapping partition of total RAM for the detail rows.
    # Linux MemAvailable already includes reclaimable cache, therefore cache
    # must not be added on top of used memory.
    panel = min(max(0, panel_rss), used)
    web = min(max(0, web_rss), max(0, used - panel))
    other = max(0, used - panel - web)
    cache = max(0, available - free)
    free_partition = max(0, total - used - cache)

    memory_parts = [
        ("panel", "SG-Gateway", "Панель и дочерние процессы", panel, "#8279B8"),
        ("web", "Веб-сервер", "Процессы Nginx и reverse proxy, если используются", web, "#B9839A"),
        ("system", "Системные службы", "Остальные процессы операционной системы", other, "#7897A8"),
        ("cache", "Файловый кэш", "Доступная память, занятая файловым кэшем", cache, "#C9A15B"),
        ("free", "Доступно", f"Доступно с учётом кэша: {_format_bytes(available)}", free_partition, "var(--sg-simple-dial-empty)"),
    ]

    memory_rows: list[dict] = []
    for key, label, note, amount, color in memory_parts:
        percent = round(amount * 100 / total, 1) if total else 0
        memory_rows.append(
            {
                "key": key,
                "label": label,
                "note": note,
                "value": _format_bytes(amount),
                "percent": f"{percent:.1f}%",
                "color": color,
            }
        )

    data_dir = load_config().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(str(data_dir))
    disk_fs = _disk_filesystem_info(data_dir)
    disk_percent = round(disk.used * 100 / disk.total) if disk.total else 0
    disk_state, disk_label = _resource_state(disk_percent)
    disk_rows = _dashboard_disk_breakdown(data_dir, disk.used)

    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    cpu_count = os.cpu_count() or 1
    cpu_activity = collect_cpu_activity(cpu_count, load)
    cpu_state, cpu_label = _resource_state(cpu_activity["percent"])

    return {
        "memory": {
            "used": _format_bytes(used),
            "total": _format_bytes(total),
            "available": _format_bytes(available),
            "percent": used_percent,
            "percent_text": f"{used_percent}%",
            "state": memory_state,
            "state_label": memory_label,
            "gradient": (
                "conic-gradient(var(--sg-simple-dial-used) 0 "
                f"{used_percent}%, var(--sg-simple-dial-empty) {used_percent}% 100%)"
            ),
            "rows": memory_rows,
            "swap_used": _format_bytes(mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)),
        },
        "disk": {
            "used": _format_bytes(disk.used),
            "free": _format_bytes(disk.free),
            "total": _format_bytes(disk.total),
            "filesystem": disk_fs["filesystem"],
            "mount_point": disk_fs["mount_point"],
            "percent": disk_percent,
            "percent_text": f"{disk_percent}%",
            "free_percent": max(0, 100 - disk_percent),
            "rows": disk_rows,
            "state": disk_state,
            "state_label": disk_label,
            "gradient": (
                "conic-gradient(var(--sg-simple-dial-used) 0 "
                f"{disk_percent}%, var(--sg-simple-dial-empty) {disk_percent}% 100%)"
            ),
        },
        "cpu": {
            "count": cpu_count,
            "load": f"{load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}",
            "percent": cpu_activity["percent"],
            "percent_value": cpu_activity["percent_value"],
            "state": cpu_state,
            "state_label": cpu_label,
            "rows": cpu_activity["rows"],
            "uptime": cpu_activity["uptime"],
            "processes": cpu_activity["processes"],
            "running": cpu_activity["running"],
        },
    }




def _sg_gateway_status_label(status: str) -> str:
    return {"Configured": "Настроено", "Disabled": "Не настроено"}.get(status, status)


def _sg_gateway_server_identity(config) -> dict:
    address = config.public_address or config.host
    configured_code = normalize_country_code(getattr(config, "country_code", "unknown"))
    code = configured_code
    try:
        connections = list_connections()
        selected = connections[0] if connections else None
        if selected is not None:
            settings = get_connection_settings(selected.name)
            address = settings.host or address
        if code == "unknown":
            code = lookup_country_code(address)
    except Exception:
        pass
    return {
        "name": getattr(config, "server_name", "SG-Gateway") or "SG-Gateway",
        "address": address,
        "country_code": normalize_country_code(code),
        "country_name": country_name(code),
    }

def _sg_gateway_system_context() -> dict:
    connections = list_connections()
    return {
        "report": build_diagnostic_report(),
        "health_checks": collect_health_checks(),
        "resources": _dashboard_resources(),
        "connections": connections,
        "client_total": count_clients(),
        "backup_total": len(list_backups()),
        "release": get_release_manifest(),
    }

def create_app() -> Flask:
    config = load_config()
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.secret_key = config.secret_key

    init_db()
    register_awg31(app)

    @app.before_request
    def protect_panel():
        if should_skip_auth(request.endpoint):
            return None
        if is_authenticated():
            return None
        return redirect(url_for("login", next=request.path))

    @app.context_processor
    def inject_globals():
        try:
            panel_health = health_summary()
        except Exception:
            panel_health = "warning"
        return {
            "app_version": get_version(),
            "is_authenticated": is_authenticated(),
            "country_options": COUNTRY_OPTIONS,
            "country_name": country_name,
            "country_flag_url": lambda code: url_for(
                "static", filename=f"flags/{normalize_country_code(code)}.svg"
            ),
            "server_identity": _sg_gateway_server_identity(config),
            "panel_health": panel_health,
            "connection_status_label": _sg_gateway_status_label,
        }

    @app.get("/login")
    def login():
        return render_template(
            "login.html",
            error=False,
            next_url=request.args.get("next", "/"),
        )

    @app.post("/login")
    def login_post():
        next_url = _safe_login_next(request.form.get("next"))
        if verify_password(request.form.get("password", "")):
            login_user()
            return redirect(next_url)
        return render_template("login.html", error=True, next_url=next_url), 401

    @app.post("/logout")
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.get("/")
    def dashboard():
        return render_template(
            "system.html",
            active_page="system",
            **_sg_gateway_system_context(),
        )

    @app.get("/recovery")
    def recovery():
        return render_template(
            "recovery.html",
            health=health_summary(),
            health_checks=collect_health_checks(),
            backups=list_backups()[:5],
            requested_restore=request.args.get("restore", ""),
        )

    @app.get("/system")
    def system():
        return render_template(
            "system.html",
            active_page="system",
            **_sg_gateway_system_context(),
        )

    @app.get("/outbounds")
    def outbounds():
        return render_template(
            "outbounds.html",
            active_page="outbounds",
            warp=warp_overview(),
            custom_outbounds=[],
        )

    @app.get("/routing")
    def routing():
        return render_template(
            "routing.html",
            active_page="routing",
            connections=list_connections(),
            awg_settings=get_connection_settings("amneziawg"),
            xray_settings=get_connection_settings("xray"),
            xray_profiles=xray_profiles_overview(),
            geofiles=geofiles_overview(),
            routing_templates=routing_templates_overview(),
            warp=warp_overview(),
            mihomo=mihomo_overview(),
            client_total=count_clients(),
        )

    def _warp_action(command: str, success_default: str):
        result = run_hostd_command(
            f"warp.{command}",
            timeout=650 if command in {"install", "recreate"} else 260,
        )
        if result.status == "ok":
            flash(result.message or success_default, "success")
        else:
            flash(f"WARP: {result.message or 'операция не выполнена'}", "error")
        return redirect(url_for("outbounds") + "#warp")

    @app.post("/outbounds/warp/create")
    @app.post("/routing/warp/install")
    def outbounds_warp_create():
        return _warp_action("install", "WARP создан и зарегистрирован.")

    @app.post("/outbounds/warp/enable")
    @app.post("/routing/warp/enable")
    def outbounds_warp_enable():
        return _warp_action("enable", "WARP включён.")

    @app.post("/outbounds/warp/disable")
    @app.post("/routing/warp/disable")
    def outbounds_warp_disable():
        return _warp_action("disable", "WARP выключен.")

    @app.post("/outbounds/warp/recreate")
    @app.post("/routing/warp/recreate")
    def outbounds_warp_recreate():
        return _warp_action("recreate", "Реквизиты WARP пересозданы.")

    @app.post("/outbounds/warp/remove")
    @app.post("/routing/warp/remove")
    def outbounds_warp_remove():
        return _warp_action("remove", "WARP удалён.")

    @app.post("/outbounds/warp/test")
    @app.post("/routing/warp/test")
    def outbounds_warp_test():
        return _warp_action("test", "WARP успешно проверен.")

    @app.get("/outbounds/warp/json")
    def outbounds_warp_json():
        result = run_hostd_command("warp.export_json", timeout=70)
        document = result.payload.get("document") if result.status == "ok" else ""
        if not isinstance(document, str) or not document.strip():
            flash(f"WARP: {result.message or 'JSON недоступен'}", "error")
            return redirect(url_for("outbounds") + "#warp")
        return Response(
            document,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=sg-gateway-warp.json"},
        )


    @app.post("/routing/geofiles/check")
    def geofiles_check():
        source_id = request.form.get("source_id", "loyalsoldier")
        geoip_file = request.files.get("geoip_file")
        geosite_file = request.files.get("geosite_file")
        try:
            report = stage_pair(
                source_id,
                geoip_url=request.form.get("geoip_url", ""),
                geosite_url=request.form.get("geosite_url", ""),
                geoip_upload=geoip_file.stream if geoip_file and geoip_file.filename else None,
                geosite_upload=(
                    geosite_file.stream
                    if geosite_file and geosite_file.filename
                    else None
                ),
                geoip_upload_name=geoip_file.filename if geoip_file and geoip_file.filename else "",
                geosite_upload_name=geosite_file.filename if geosite_file and geosite_file.filename else "",
                local_geoip=request.form.get("local_geoip", ""),
                local_geosite=request.form.get("local_geosite", ""),
                block_ads=bool(request.form.get("roscom_block_ads")),
                block_windows_telemetry=bool(request.form.get("roscom_block_windows")),
                block_torrent=bool(request.form.get("roscom_block_torrent")),
            )
            if report.ready:
                flash(
                    (
                        "GeoFiles проверены и готовы к применению: "
                        f"GeoIP {len(report.geoip.categories)} категорий, "
                        f"GeoSite {len(report.geosite.categories)} категорий."
                    ),
                    "success",
                )
            else:
                flash(
                    "GeoFiles проверены, но применять их нельзя: "
                    + (report.xray_message or report.message),
                    "error",
                )
        except GeoFilesError as exc:
            flash(f"GeoFiles не прошли проверку: {exc}", "error")
        return redirect(url_for("routing") + "#geofiles")

    @app.post("/routing/geofiles/apply")
    def geofiles_apply():
        try:
            result = apply_candidate()
            flash(str(result.get("message", "GeoFiles применены.")), "success")
        except GeoFilesError as exc:
            flash(f"GeoFiles не применены: {exc}", "error")
        return redirect(url_for("routing") + "#geofiles")

    @app.post("/routing/geofiles/rollback")
    def geofiles_rollback():
        try:
            result = rollback_latest()
            flash(str(result.get("message", "GeoFiles восстановлены.")), "success")
        except GeoFilesError as exc:
            flash(f"Откат GeoFiles не выполнен: {exc}", "error")
        return redirect(url_for("routing") + "#geofiles")


    @app.post("/routing/smart/preview")
    def routing_smart_preview():
        try:
            preview = stage_smart_routing(request.form)
            category = "success" if preview.get("ready") else "error"
            flash(
                f"Маршрутизация проверена: {preview['title']}. {preview['message']}",
                category,
            )
        except (RoutingTemplateError, GeoFilesError, ValueError) as exc:
            flash(f"Маршрутизация не подготовлена: {exc}", "error")
        return redirect(url_for("routing") + "#routing")

    @app.post("/routing/templates/preview")
    def routing_template_preview():
        try:
            preview = stage_template(
                request.form.get("template_id", ""),
                request.form.get("mode", "replace_managed"),
            )
            flash(
                f"Routing candidate подготовлен: {preview['title']}.",
                "success",
            )
        except (RoutingTemplateError, GeoFilesError) as exc:
            flash(f"Routing template не подготовлен: {exc}", "error")
        return redirect(url_for("routing") + "#routing-templates")

    @app.post("/routing/templates/apply")
    def routing_template_apply():
        try:
            result = apply_routing_template()
            flash(str(result.get("message", "Routing fragment применён.")), "success")
        except RoutingTemplateError as exc:
            flash(f"Routing fragment не применён: {exc}", "error")
        return redirect(url_for("routing") + "#routing-templates")

    @app.post("/routing/templates/rollback")
    def routing_template_rollback():
        try:
            result = rollback_routing_template()
            flash(str(result.get("message", "Routing fragment восстановлен.")), "success")
        except RoutingTemplateError as exc:
            flash(f"Откат Routing fragment не выполнен: {exc}", "error")
        return redirect(url_for("routing") + "#routing-templates")

    @app.get("/security")
    def security():
        network_accessible = bool(config.public_address) or config.host not in {"127.0.0.1", "localhost", "::1"}
        default_password = password_is_default()
        return render_template(
            "security.html",
            active_page="security",
            security={
                "host": config.public_address or config.host,
                "port": config.public_port,
                "environment": config.environment,
                "network_accessible": network_accessible,
                "default_password": default_password,
                "exposure": (
                    "Панель привязана к сетевому интерфейсу и доступна по сети."
                    if network_accessible
                    else "Панель привязана только к локальному интерфейсу."
                ),
                "password_message": (
                    "Стандартный пароль для разработки всё ещё активен."
                    if default_password
                    else "Настроен пользовательский пароль администратора."
                ),
            },
        tls=security_tls_overview(),
        )


    @app.post("/security/password")
    def security_password_change():
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        target = url_for("security") + "#password-change"

        if not verify_password(current_password):
            flash("Текущий пароль указан неверно.", "error")
            return redirect(target)
        if len(new_password) < 8:
            flash("Новый пароль должен содержать не менее 8 символов.", "error")
            return redirect(target)
        if new_password != confirm_password:
            flash("Новый пароль и подтверждение не совпадают.", "error")
            return redirect(target)
        if new_password == current_password:
            flash("Новый пароль совпадает с текущим.", "error")
            return redirect(target)
        try:
            set_password(new_password)
        except OSError as exc:
            flash(f"Пароль не изменён: {exc}", "error")
            return redirect(target)

        flash("Пароль администратора изменён. Новый пароль уже используется для следующих входов.", "success")
        return redirect(target)

    @app.post("/security/tls/check")
    def security_tls_check():
        try:
            result = stage_tls_request(
                request.form.get("domain", ""),
                request.form.get("email", ""),
            )
            flash(result["dns"]["message"], "success" if result["dns"]["ok"] else "error")
        except TlsError as exc:
            flash(f"Проверка домена не выполнена: {exc}", "error")
        return redirect(url_for("security"))

    @app.post("/security/tls/issue")
    def security_tls_issue():
        result = run_hostd_command("tls.issue.start", timeout=20)
        if result.status != "ok":
            flash(f"HTTPS-задача не запущена: {result.message}", "error")
            return redirect(url_for("security"))
        return redirect(url_for("operation_job", job_id=str(result.payload.get("job_id") or "")))

    @app.get("/operations/<job_id>")
    def operation_job(job_id: str):
        try:
            job = read_operation_job(job_id)
        except FileNotFoundError:
            abort(404)
        kind = str(job.get("kind") or "")
        if kind == "tls_issue":
            active = "security"
        elif kind == "full_backup_restore":
            active = "maintenance"
        elif (
            kind in {"awg3_runtime_repair", "panel_update_channel"}
            or kind.startswith("xray_update_")
            or kind.startswith("core_update_")
        ):
            active = "maintenance"
        else:
            active = "connections"
        return render_template("operation_job.html", active_page=active, job=job)

    @app.get("/operations/<job_id>/status")
    def operation_job_status(job_id: str):
        try:
            job = read_operation_job(job_id)
        except FileNotFoundError:
            abort(404)
        return jsonify(job)

    @app.post("/connections/xray/apply")
    def xray_apply_start():
        result = run_hostd_command("xray.apply.start", timeout=20)
        if result.status != "ok":
            flash(f"Xray-задача не запущена: {result.message}", "error")
            return redirect(url_for("connections") + "#xray-profiles")
        return redirect(url_for("operation_job", job_id=str(result.payload.get("job_id") or "")))

    @app.post("/connections/xray/test")
    def xray_runtime_test():
        result = run_hostd_command("xray.test", timeout=120)
        flash(result.message or "Xray test завершён", "success" if result.status == "ok" else "error")
        return redirect(url_for("connections") + "#xray-profiles")

    @app.post("/connections/xray/rollback")
    def xray_runtime_rollback():
        result = run_hostd_command("xray.rollback", timeout=120)
        flash(result.message or "Xray rollback завершён", "success" if result.status == "ok" else "error")
        return redirect(url_for("connections") + "#xray-profiles")

    @app.post("/security/tls/renew")
    def security_tls_renew():
        try:
            result = renew_certificate()
            flash(str(result.get("message", "Сертификат проверен.")), "success")
        except TlsError as exc:
            flash(f"Сертификат не обновлён: {exc}", "error")
        return redirect(url_for("security"))

    @app.post("/security/tls/rollback")
    def security_tls_rollback():
        try:
            result = rollback_tls()
            flash(str(result.get("message", "HTTPS-конфигурация восстановлена.")), "success")
        except TlsError as exc:
            flash(f"Откат HTTPS не выполнен: {exc}", "error")
        return redirect(url_for("security"))

    @app.get("/sub/<token>")
    def subscription_feed(token: str):
        access = get_subscription_access(token)
        if access is None:
            abort(404)
        client, device = access
        if not protocol_ready(client, "subscription", device):
            abort(404)
        export = build_subscription(client, device)
        if not export.body:
            abort(404)
        response = Response(export.body, mimetype=export.media_type)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # SG_GATEWAY_SUBSCRIPTION_PATCH_V1
        import base64 as _subscription_base64
        from urllib.parse import quote as _subscription_quote

        device_title = "Основное устройство" if device.is_primary else device.name
        profile_title = f"SG-Gateway · {client.name} · {device_title}"
        encoded_title = _subscription_base64.b64encode(
            profile_title.encode("utf-8")
        ).decode("ascii")

        ascii_client = "".join(
            char
            if char.isascii() and (char.isalnum() or char in "-_")
            else "-"
            for char in client.name
        ).strip("-") or f"client-{client.id}"
        ascii_device = "main" if device.is_primary else (
            "".join(
                char
                if char.isascii() and (char.isalnum() or char in "-_")
                else "-"
                for char in device.name
            ).strip("-")
            or f"device-{device.id}"
        )
        fallback_name = f"SG-Gateway-{ascii_client}-{ascii_device}"
        utf8_name = _subscription_quote(profile_title, safe="")

        response.headers["Profile-Title"] = f"base64:{encoded_title}"
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{fallback_name}"; '
            f"filename*=UTF-8''{utf8_name}"
        )
        return response

    @app.get("/clients")
    def clients():
        return render_template(
            "clients.html",
            active_page="clients",
            clients=list_clients(),
            xray_profiles=xray_profiles_overview(),
            tls=security_tls_overview(),
        )

    @app.post("/clients")
    def add_client():
        protocols = _prepare_client_protocols(request.form.getlist("protocols"))
        access = ",".join(protocols)
        try:
            client_id = create_client(
                name=request.form.get("name", ""),
                access=access,
                expires_at=request.form.get("expires_at") or None,
            )
        except Exception as exc:
            flash(f"Клиент не создан: не удалось подготовить реквизиты доступа. {exc}", "error")
            return redirect(url_for("clients"))
        if not client_id:
            flash(
                "Клиент не создан. Имя должно быть уникальным, "
                "а минимум один протокол должен быть выбран.",
                "error",
            )
            return redirect(url_for("clients"))

        try:
            result = apply_clients_runtime()
            flash(
                str(result.get("message") or "Клиент создан и применён."),
                "success",
            )
        except ClientWorkflowError as exc:
            # Creation is atomic from the user's point of view. A client whose
            # candidate runtime failed must not remain as a misleading active
            # database record. Remove it and re-apply the previous catalogue.
            delete_client(client_id)
            restore_note = ""
            try:
                apply_clients_runtime()
                restore_note = " Предыдущий runtime восстановлен."
            except ClientWorkflowError as restore_exc:
                restore_note = f" Восстановление runtime: {restore_exc}"
            flash(
                f"Клиент не создан: конфигурация не прошла проверку. {exc}."
                f" Запись клиента удалена.{restore_note}",
                "error",
            )
            return redirect(url_for("clients"))
        return redirect(url_for("client_detail", client_id=client_id))

    @app.get("/clients/<int:client_id>")
    def client_detail(client_id: int):
        client = get_client(client_id)
        if client is None:
            abort(404)
        devices = list_devices(client_id)
        device_views = [
            {
                "device": device,
                "access_cards": build_access_cards(client, device),
                "protocol_tokens": device_access_tokens(device.id),
            }
            for device in devices
        ]
        primary_view = next(
            (view for view in device_views if view["device"].is_primary),
            None,
        )
        return render_template(
            "client_detail.html",
            active_page="clients",
            client=client,
            devices=devices,
            device_views=device_views,
            primary_view=primary_view,
            xray_profiles=xray_profiles_overview(),
            tls=security_tls_overview(),
        )

    @app.post("/clients/<int:client_id>/edit")
    def edit_client(client_id: int):
        snapshot = snapshot_client(client_id)
        if snapshot is None:
            abort(404)
        protocols = _prepare_client_protocols(request.form.getlist("protocols"))
        try:
            updated = update_client(
                client_id,
                request.form.get("name", ""),
                request.form.get("expires_at") or None,
                ",".join(protocols),
            )
        except (ValueError, RuntimeError) as exc:
            flash(f"Клиент не изменён: {exc}", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        if not updated:
            abort(404)
        try:
            result = apply_clients_runtime()
            flash(
                str(result.get("message") or "Клиент изменён и применён."),
                "success",
            )
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/devices/<int:device_id>/edit")
    def edit_device(client_id: int, device_id: int):
        if get_device(device_id, client_id) is None:
            abort(404)
        snapshot = snapshot_client(client_id)
        if snapshot is None:
            abort(404)
        protocols = _prepare_client_protocols(request.form.getlist("protocols"))
        try:
            updated = update_device(
                client_id,
                device_id,
                request.form.get("name", ""),
                request.form.get("expires_at") or None,
                ",".join(protocols),
            )
        except (ValueError, RuntimeError) as exc:
            flash(f"Устройство не изменено: {exc}", "error")
            return redirect(
                url_for("client_detail", client_id=client_id)
                + f"#device-{device_id}"
            )
        if not updated:
            abort(404)
        try:
            result = apply_clients_runtime()
            flash(
                str(result.get("message") or "Устройство изменено и применено."),
                "success",
            )
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(
            url_for("client_detail", client_id=client_id)
            + f"#device-{device_id}"
        )

    def _build_export(client_id: int, kind: str):
        client = get_client(client_id)
        if client is None:
            abort(404)

        builders = {
            "amneziawg": build_awg_config,
        "amneziawg3": build_awg3_config,
            "xray": build_xray_link,
            "mihomo": build_mihomo_yaml,
            "mieru": build_mieru_link,
            "subscription": build_subscription,
        }
        builder = builders.get(kind)
        if builder is None:
            abort(404)

        return builder(client)

    @app.get("/clients/<int:client_id>/exports/<kind>")
    def export_client_access(client_id: int, kind: str):
        export = _build_export(client_id, kind)
        return Response(
            export.body,
            mimetype=export.media_type,
            headers={"Content-Disposition": f"attachment; filename={export.filename}"},
        )

    @app.get("/clients/<int:client_id>/qr/<kind>")
    def client_access_qr(client_id: int, kind: str):
        client = get_client(client_id)
        if client is None:
            abort(404)
        export = _build_export(client_id, kind)
        qr_value = build_subscription_url(client) if kind == "subscription" else export.body
        if not qr_value:
            abort(409)
        try:
            svg = build_qr_svg(qr_value)
        except ClientQrError as exc:
            return Response(str(exc), status=409, mimetype="text/plain")
        return Response(svg, mimetype="image/svg+xml")

    @app.post("/clients/apply")
    def apply_clients():
        return_client_id = request.form.get("return_client_id", type=int)
        try:
            result = apply_clients_runtime()
            flash(
                str(result.get("message") or "Конфигурации применены."),
                "success",
            )
        except ClientWorkflowError as exc:
            flash(f"Применение конфигураций: {exc}", "error")

        if return_client_id:
            return redirect(
                url_for("client_detail", client_id=return_client_id)
            )
        return redirect(url_for("clients"))

    def _rollback_client_change(snapshot, reason: Exception) -> str:
        if snapshot is None:
            return f"Откат невозможен: исходное состояние не найдено. {reason}"
        try:
            restore_client_snapshot(snapshot)
        except Exception as restore_exc:
            return f"Ошибка runtime: {reason}. База не восстановлена: {restore_exc}"
        try:
            apply_clients_runtime()
        except ClientWorkflowError as runtime_exc:
            return (
                f"Ошибка runtime: {reason}. Состояние клиента возвращено, "
                f"но повторное применение прежнего runtime не прошло: {runtime_exc}"
            )
        return f"Ошибка runtime: {reason}. Изменение отменено, прежний доступ восстановлен."

    @app.post("/clients/<int:client_id>/enable")
    def enable_client(client_id: int):
        snapshot = snapshot_client(client_id)
        if snapshot is None or not set_client_enabled(client_id, True):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Клиент включён и применён на сервере.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(request.referrer or url_for("clients"))

    @app.post("/clients/<int:client_id>/disable")
    def disable_client(client_id: int):
        snapshot = snapshot_client(client_id)
        if snapshot is None or not set_client_enabled(client_id, False):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Клиент отключён и удалён из runtime.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(request.referrer or url_for("clients"))

    @app.post("/clients/<int:client_id>/delete")
    def remove_client(client_id: int):
        snapshot = snapshot_client(client_id)
        if snapshot is None or not delete_client(client_id):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Клиент удалён; runtime обновлён.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("clients"))


    @app.get("/clients/<int:client_id>/protocols/<kind>")
    def protocol_export(client_id: int, kind: str):
        client = get_client(client_id)
        if client is None:
            abort(404)
        if not protocol_ready(client, kind):
            abort(409)
        export = build_protocol_export(client, kind)
        if not export.body:
            abort(409)
        return Response(
            export.body,
            mimetype=export.media_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{export.filename}"'
                )
            },
        )

    @app.get("/clients/<int:client_id>/protocols/<kind>/qr")
    def protocol_qr(client_id: int, kind: str):
        client = get_client(client_id)
        if client is None:
            abort(404)
        if not protocol_ready(client, kind):
            abort(409)
        export = build_protocol_export(client, kind)
        qr_value = build_subscription_url(client) if kind == "subscription" else export.body
        if not qr_value:
            abort(409)
        try:
            svg = build_qr_svg(qr_value)
        except ClientQrError as exc:
            return Response(str(exc), status=409, mimetype="text/plain")
        return Response(svg, mimetype="image/svg+xml")

    @app.post("/clients/<int:client_id>/devices")
    def add_device(client_id: int):
        client = get_client(client_id)
        if client is None:
            abort(404)
        snapshot = snapshot_client(client_id)
        protocols = _prepare_client_protocols(request.form.getlist("protocols"))
        access = ",".join(protocols)
        try:
            device_id = create_device(
                client_id,
                request.form.get("name", ""),
                access,
                request.form.get("expires_at") or None,
            )
        except Exception as exc:
            flash(f"Доступ не создан: не удалось подготовить отдельные реквизиты. {exc}", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        if not device_id:
            flash(
                "Доступ не создан. Укажите уникальное имя устройства и выберите хотя бы один канал.",
                "error",
            )
            return redirect(url_for("client_detail", client_id=client_id))
        try:
            result = apply_clients_runtime()
            flash(
                str(result.get("message") or "Новый доступ создан и применён."),
                "success",
            )
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("client_detail", client_id=client_id) + f"#device-{device_id}")

    @app.post("/clients/<int:client_id>/devices/<int:device_id>/enable")
    def enable_device(client_id: int, device_id: int):
        if get_device(device_id, client_id) is None:
            abort(404)
        snapshot = snapshot_client(client_id)
        if snapshot is None or not set_device_enabled(device_id, True):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Доступ включён независимо от остальных устройств.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("client_detail", client_id=client_id) + f"#device-{device_id}")

    @app.post("/clients/<int:client_id>/devices/<int:device_id>/disable")
    def disable_device(client_id: int, device_id: int):
        if get_device(device_id, client_id) is None:
            abort(404)
        snapshot = snapshot_client(client_id)
        if snapshot is None or not set_device_enabled(device_id, False):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Отключён только выбранный доступ. Остальные устройства продолжают работать.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("client_detail", client_id=client_id) + f"#device-{device_id}")

    @app.post("/clients/<int:client_id>/devices/<int:device_id>/delete")
    def remove_device(client_id: int, device_id: int):
        device = get_device(device_id, client_id)
        if device is None:
            abort(404)
        if device.is_primary:
            flash("Основной доступ нельзя удалить отдельно. Можно отключить его или удалить клиента.", "error")
            return redirect(url_for("client_detail", client_id=client_id))
        snapshot = snapshot_client(client_id)
        if snapshot is None or not delete_device(device_id):
            abort(404)
        try:
            apply_clients_runtime()
            flash("Дополнительный доступ удалён; остальные устройства не изменены.", "success")
        except ClientWorkflowError as exc:
            flash(_rollback_client_change(snapshot, exc), "error")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.get("/clients/<int:client_id>/devices/<int:device_id>/protocols/<kind>")
    def device_protocol_export(client_id: int, device_id: int, kind: str):
        client = get_client(client_id)
        device = get_device(device_id, client_id)
        if client is None or device is None:
            abort(404)
        if not protocol_ready(client, kind, device):
            abort(409)
        export = build_protocol_export(client, kind, device)
        if not export.body:
            abort(409)
        return Response(
            export.body,
            mimetype=export.media_type,
            headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
        )

    @app.get("/clients/<int:client_id>/devices/<int:device_id>/protocols/<kind>/qr")
    def device_protocol_qr(client_id: int, device_id: int, kind: str):
        client = get_client(client_id)
        device = get_device(device_id, client_id)
        if client is None or device is None:
            abort(404)
        if not protocol_ready(client, kind, device):
            abort(409)
        export = build_protocol_export(client, kind, device)
        qr_value = build_subscription_url(client, device) if kind == "subscription" else export.body
        if not qr_value:
            abort(409)
        try:
            svg = build_qr_svg(qr_value)
        except ClientQrError as exc:
            return Response(str(exc), status=409, mimetype="text/plain")
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/connections")
    def connections():
        return render_template(
            "connections.html",
            active_page="connections",
            connections=list_connections(),
            awg_settings=get_connection_settings("amneziawg"),
            awg3_settings=get_connection_settings("amneziawg3"),
            xray_settings=get_connection_settings("xray"),
            xray_profiles=xray_profiles_overview(),
            mihomo=mihomo_overview(),
            client_total=count_clients(),
        )

    @app.post("/connections/amneziawg")
    def update_amneziawg():
        current = get_connection_settings("amneziawg")
        config = dict(current.config)
        config["dns"] = request.form.get("dns", config.get("dns", "1.1.1.1"))
        config["server_public_key"] = request.form.get(
            "server_public_key",
            config.get("server_public_key", "PLACEHOLDER_SERVER_PUBLIC_KEY"),
        )
        config["country_code"] = normalize_country_code(
            request.form.get("country_code", config.get("country_code", "unknown"))
        )
        updated = update_connection_settings(
            "amneziawg",
            request.form.get("host", current.host),
            request.form.get("port", str(current.port)),
            config,
        )
        flash("Настройки AmneziaWG сохранены." if updated else "Настройки AmneziaWG не применены. Проверьте адрес и порт.", "success" if updated else "error")
        return redirect(url_for("connections"))

    @app.post("/connections/amneziawg3")
    def update_amneziawg3():
        current = get_connection_settings("amneziawg3")
        config = dict(current.config)
        config["dns"] = request.form.get("dns", config.get("dns", "1.1.1.1"))
        config["server_public_key"] = request.form.get(
            "server_public_key", config.get("server_public_key", "")
        )
        config["generation"] = 3
        updated = update_connection_settings(
            "amneziawg3",
            request.form.get("host", current.host),
            request.form.get("port", str(current.port)),
            config,
        )
        flash(
            "Настройки AmneziaWG 3 сохранены."
            if updated
            else "Настройки AmneziaWG 3 не применены. Проверьте адрес.",
            "success" if updated else "error",
        )
        return redirect(url_for("connections"))

    @app.post("/connections/xray")
    def update_xray():
        current = get_connection_settings("xray")
        config = dict(current.config)
        config["server_name"] = request.form.get(
            "server_name",
            config.get("server_name", "www.cloudflare.com"),
        )
        config["public_key"] = request.form.get(
            "public_key",
            config.get("public_key", "PLACEHOLDER_REALITY_PUBLIC_KEY"),
        )
        config["short_id"] = request.form.get(
            "short_id",
            config.get("short_id", "PLACEHOLDER_SHORT_ID"),
        )
        config["country_code"] = normalize_country_code(
            request.form.get("country_code", config.get("country_code", "unknown"))
        )
        updated = update_connection_settings(
            "xray",
            request.form.get("host", current.host),
            request.form.get("port", str(current.port)),
            config,
        )
        flash("Настройки Xray сохранены." if updated else "Настройки Xray не применены. Проверьте адрес и порт.", "success" if updated else "error")
        return redirect(url_for("connections"))



    @app.post("/connections/xray/profiles")
    def update_xray_profiles():
        action = request.form.get("action", "save")
        transaction_id: int | None = None
        try:
            result = save_xray_profiles(request.form, transactional=True)
            transaction_id = int(result.get("transaction_id") or 0) or None
        except XrayProfilesError as exc:
            flash(f"Xray-профили не сохранены: {exc}", "error")
            return redirect(url_for("connections") + "#xray-profiles")

        if action == "test":
            runtime = run_hostd_command("xray.test", timeout=120)
            if transaction_id is not None:
                rollback_xray_settings_transaction(
                    transaction_id, status="rolled_back_after_candidate_test"
                )
            flash(
                (runtime.message or "Xray candidate проверен.")
                + " Изменения не применялись.",
                "success" if runtime.status == "ok" else "error",
            )
            return redirect(url_for("connections") + "#xray-profiles")

        if action == "apply":
            runtime = run_hostd_command("xray.apply.start", timeout=20)
            if runtime.status != "ok":
                if transaction_id is not None:
                    rollback_xray_settings_transaction(
                        transaction_id, status="rolled_back_job_start_error"
                    )
                flash(f"Xray-задача не запущена: {runtime.message}", "error")
                return redirect(url_for("connections") + "#xray-profiles")
            return redirect(
                url_for(
                    "operation_job",
                    job_id=str(runtime.payload.get("job_id") or ""),
                )
            )

        if transaction_id is not None:
            rollback_xray_settings_transaction(
                transaction_id, status="rolled_back_without_apply"
            )
        flash("Для изменения Xray используйте «Сохранить и применить».", "warning")
        return redirect(url_for("connections") + "#xray-profiles")

    @app.post("/connections/xray/hysteria2/salamander/generate")
    def generate_hysteria2_salamander_password():
        return jsonify({"ok": True, "password": new_salamander_password()})

    @app.post("/connections/xray/hysteria2/salamander/secret")
    def reveal_hysteria2_salamander_password():
        try:
            secret = salamander_secret()
        except XrayProfilesError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 404
        return jsonify({"ok": True, "password": secret})

    @app.post("/connections/mihomo")
    def update_mihomo():
        if not save_mihomo_settings(request.form):
            flash("Настройки Mihomo не сохранены.", "error")
            return redirect(url_for("connections") + "#mihomo")
        action = request.form.get("action", "save")
        try:
            if action == "test":
                result = test_mihomo_candidate()
                flash(str(result.get("message", "Candidate проверен.")), "success")
            elif action == "apply":
                result = apply_mihomo_candidate()
                flash(str(result.get("message", "Mihomo применён.")), "success")
            elif action == "restart":
                result = restart_mihomo_service()
                flash(str(result.get("message", "Mihomo перезапущен.")), "success")
            elif action == "rollback":
                result = rollback_mihomo()
                flash(str(result.get("message", "Mihomo восстановлен.")), "success")
            else:
                flash("Настройки Mihomo сохранены.", "success")
        except MihomoError as exc:
            flash(f"Mihomo: {exc}", "error")
        return redirect(url_for("connections") + "#mihomo")

    @app.post("/clients/<int:client_id>/mihomo/enable")
    def enable_client_mihomo(client_id: int):
        if not ensure_client_deployment(client_id):
            abort(404)
        try:
            result = apply_mihomo_candidate()
            flash(str(result.get("message", "Mihomo-доступ включён.")), "success")
        except MihomoError as exc:
            flash(f"Credentials созданы, runtime пока не применён: {exc}", "error")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/mihomo/disable")
    def disable_client_mihomo(client_id: int):
        if not disable_client_deployment(client_id):
            abort(404)
        try:
            result = apply_mihomo_candidate()
            flash(str(result.get("message", "Mihomo-доступ отключён.")), "success")
        except MihomoError as exc:
            flash(f"Доступ отключён в базе, runtime: {exc}", "error")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.post("/clients/<int:client_id>/mihomo/rotate")
    def rotate_client_mihomo(client_id: int):
        if not rotate_client_credentials(client_id):
            abort(404)
        try:
            result = apply_mihomo_candidate()
            flash(str(result.get("message", "Credentials перевыпущены.")), "success")
        except MihomoError as exc:
            flash(f"Credentials перевыпущены, runtime: {exc}", "error")
        return redirect(url_for("client_detail", client_id=client_id))

    @app.get("/maintenance")
    def maintenance():
        tab = request.args.get("tab", "backups").strip().lower()
        if tab not in {"backups", "updates"}:
            tab = "backups"
        updates = None
        panel_updates = None
        core_updates = None
        geofiles_updates = None
        runtime_contract = None
        if tab == "updates":
            refresh_updates = request.args.get("refresh") == "1"
            updates = xray_update_overview(refresh=refresh_updates)
            panel_updates = panel_update_overview(refresh=refresh_updates)
            core_updates = core_update_overview(refresh=refresh_updates)
            geofiles_updates = geofiles_overview()
            runtime_result = run_hostd_command("runtime.contract", timeout=20)
            runtime_contract = dict(runtime_result.payload or {})
            if not runtime_contract:
                runtime_contract = {
                    "ok": False,
                    "checks": [],
                    "message": runtime_result.message or "Runtime Contract недоступен",
                }
        backups = list_backups()
        return render_template(
            "maintenance.html",
            active_page="maintenance",
            active_tab=tab,
            xray_updates=updates,
            panel_updates=panel_updates,
            core_updates=core_updates,
            geofiles_updates=geofiles_updates,
            runtime_contract=runtime_contract,
            diagnostics=collect_diagnostics(),
            health_checks=collect_health_checks(),
            backups=backups,
            backup_cleanup=backup_cleanup_preview(backups),
            data_backups=list_data_backups(),
            verified_data_backup=get_verified_data_backup(),
            full_backups=list_full_backups(),
            verified_full_backup=get_verified_full_backup(),
            operations=list_operations(),
            release=get_release_manifest(),
        )

    @app.post("/maintenance/panel/update")
    def panel_update_start():
        result = run_hostd_command("panel.update.start", timeout=20)
        if result.status != "ok":
            flash(f"Обновление SG-Gateway не запущено: {result.message}", "error")
            return redirect(url_for("maintenance", tab="updates"))
        return redirect(url_for("operation_job", job_id=str(result.payload.get("job_id") or "")))

    # SG_GATEWAY_02206_AWG3_REPAIR_ROUTE_V2
    @app.post("/maintenance/runtime/awg3/repair")
    def awg3_runtime_repair_start():
        result = run_hostd_command("runtime.awg3.repair.start", timeout=20)
        if result.status != "ok":
            flash(result.message or "Восстановление AWG3 runtime не запущено", "error")
            return redirect(url_for("maintenance", tab="updates", refresh="1"))
        return redirect(
            url_for(
                "operation_job",
                job_id=str(result.payload.get("job_id") or ""),
            )
        )

    @app.post("/maintenance/core/update/<engine>")
    def core_update_start(engine: str):
        if engine not in {"mihomo", "sing-box", "wgcf"}:
            abort(404)
        result = run_hostd_command(f"core.update.{engine}.start", timeout=20)
        if result.status != "ok":
            flash(f"Core Update не запущен: {result.message}", "error")
            return redirect(url_for("maintenance", tab="updates"))
        return redirect(url_for("operation_job", job_id=str(result.payload.get("job_id") or "")))

    @app.post("/maintenance/xray/update/<channel>")
    def xray_update_start(channel: str):
        if channel not in {"stable", "prerelease"}:
            abort(404)
        result = run_hostd_command(f"xray.update.{channel}.start", timeout=20)
        if result.status != "ok":
            flash(f"Обновление Xray не запущено: {result.message}", "error")
            return redirect(url_for("maintenance", tab="updates"))
        return redirect(url_for("operation_job", job_id=str(result.payload.get("job_id") or "")))

    # SG_GATEWAY_02206_DATA_BACKUP_ROUTES_V1
    @app.post("/maintenance/data-backups")
    def create_data_backup_route():
        result = run_hostd_command("backup.data.create", timeout=180)
        if result.status != "ok":
            flash(result.message or "Не удалось создать backup клиентов и настроек", "error")
            return redirect(url_for("maintenance", tab="backups"))
        name = str(result.payload.get("name") or "")
        flash(f"Backup клиентов и настроек создан: {name}", "success")
        return redirect(url_for("maintenance", tab="backups"))

    @app.get("/maintenance/data-backups/<name>/download")
    def download_data_backup_route(name: str):
        backup = get_data_backup(name)
        if backup is None:
            abort(404)
        return send_file(
            backup.path, as_attachment=True, download_name=backup.name,
            mimetype="application/octet-stream",
        )

    @app.post("/maintenance/data-backups/restore")
    def restore_data_backup_route():
        backup_action = request.form.get("backup_action", "").strip().lower()
        if backup_action == "restore_verified":
            try:
                stage_verified_data_backup_for_restore()
            except (OSError, RuntimeError, ValueError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("maintenance", tab="backups"))

            promoted = run_hostd_command("backup.data.promote", timeout=180)
            if promoted.status != "ok":
                flash(promoted.message or "DATA restore не подготовлен", "error")
                return redirect(url_for("maintenance", tab="backups"))

            result = run_hostd_command("backup.full.restore.start", timeout=20)
            if result.status != "ok":
                flash(result.message or "DATA restore не запущен", "error")
                return redirect(url_for("maintenance", tab="backups"))
            return redirect(
                url_for(
                    "operation_job",
                    job_id=str(result.payload.get("job_id") or ""),
                )
            )

        if backup_action != "verify":
            flash("Сначала выберите и проверьте DATA .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        upload = request.files.get("backup")
        original_name = str(getattr(upload, "filename", "") or "").strip() if upload is not None else ""
        if upload is None or not original_name:
            flash("Выберите DATA .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            stage_uploaded_data_backup_for_verification(upload)
        except ValueError as exc:
            log_operation("backup.data.verify", f"backup:{original_name}", str(exc), status="error")
            flash(str(exc), "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            result = run_hostd_command("backup.data.verify", timeout=180)
        except Exception as exc:
            message = f"Проверка DATA backup не выполнена: {exc}"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        if result.status != "ok":
            message = result.message or "DATA backup не прошёл проверку"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(f"DATA backup НЕ прошёл проверку: {message}", "error")
            return redirect(url_for("maintenance", tab="backups"))

        payload = result.payload or {}
        try:
            save_verified_data_backup(original_name, payload)
        except (OSError, RuntimeError, ValueError) as exc:
            message = f"DATA backup проверен, но не подготовлен к восстановлению: {exc}"
            log_operation("backup.data.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        source_version = str(payload.get("source_version") or "unknown")
        tables = int(payload.get("database_tables") or 0)
        database_size = _format_bytes(payload.get("database_size_bytes") or 0)
        certificates = "есть" if payload.get("contains_letsencrypt_certificates") else "нет"
        message = (
            f"DATA backup исправен: {original_name}. SG-Gateway {source_version}; "
            f"SQLite: OK, таблиц {tables}, {database_size}; сертификаты: {certificates}. "
            "Перед восстановлением будет проверен Runtime Contract целевого сервера."
        )
        log_operation("backup.data.verify", f"backup:{original_name}", message)
        flash(message, "success")
        return redirect(url_for("maintenance", tab="backups"))

    @app.post("/maintenance/full-backups")
    def create_full_backup_route():
        result = run_hostd_command("backup.full.create", timeout=180)
        if result.status != "ok":
            flash(result.message or "Не удалось создать полный backup", "error")
            return redirect(url_for("maintenance", tab="backups"))
        name = str(result.payload.get("name") or "")
        flash(f"Полный backup сервера создан: {name}", "success")
        return redirect(url_for("maintenance", tab="backups"))

    @app.get("/maintenance/full-backups/<name>/download")
    def download_full_backup_route(name: str):
        backup = get_full_backup(name)
        if backup is None:
            abort(404)
        return send_file(
            backup.path, as_attachment=True, download_name=backup.name,
            mimetype="application/octet-stream",
        )

    @app.post("/maintenance/full-backups/restore")
    def restore_full_backup_route():
        backup_action = request.form.get("backup_action", "").strip().lower()
        if backup_action == "restore_verified":
            try:
                stage_verified_full_backup_for_restore()
            except (OSError, RuntimeError, ValueError) as exc:
                flash(str(exc), "error")
                return redirect(url_for("maintenance", tab="backups"))

            result = run_hostd_command("backup.full.restore.start", timeout=20)
            if result.status != "ok":
                flash(result.message or "Полный restore не запущен", "error")
                return redirect(url_for("maintenance", tab="backups"))
            return redirect(
                url_for(
                    "operation_job",
                    job_id=str(result.payload.get("job_id") or ""),
                )
            )

        if backup_action != "verify":
            flash("Сначала выберите и проверьте файл .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        upload = request.files.get("backup")
        original_name = str(getattr(upload, "filename", "") or "").strip() if upload is not None else ""
        if upload is None or not original_name:
            flash("Выберите файл .sgbackup", "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            stage_uploaded_full_backup_for_verification(upload)
        except ValueError as exc:
            log_operation("backup.full.verify", f"backup:{original_name}", str(exc), status="error")
            flash(str(exc), "error")
            return redirect(url_for("maintenance", tab="backups"))

        try:
            result = run_hostd_command("backup.full.verify", timeout=180)
        except Exception as exc:
            message = f"Проверка backup не выполнена: {exc}"
            log_operation("backup.full.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        if result.status != "ok":
            message = result.message or "Backup не прошёл проверку"
            log_operation("backup.full.verify", f"backup:{original_name}", message, status="error")
            flash(f"Backup НЕ прошёл проверку: {message}", "error")
            return redirect(url_for("maintenance", tab="backups"))

        payload = result.payload or {}
        try:
            save_verified_full_backup(original_name, payload)
        except (OSError, RuntimeError, ValueError) as exc:
            message = f"Backup проверен, но не подготовлен к восстановлению: {exc}"
            log_operation("backup.full.verify", f"backup:{original_name}", message, status="error")
            flash(message, "error")
            return redirect(url_for("maintenance", tab="backups"))

        sha256 = str(payload.get("sha256") or "")
        source_version = str(payload.get("source_version") or "unknown")
        created_at = str(payload.get("created_at") or "не указано")
        tables = int(payload.get("database_tables") or 0)
        database_size = _format_bytes(payload.get("database_size_bytes") or 0)
        certificates = "есть" if payload.get("contains_letsencrypt_certificates") else "нет"
        message = (
            f"Backup исправен и готов к восстановлению: {original_name}. "
            f"SG-Gateway {source_version}; создан {created_at}; "
            f"SQLite: OK, таблиц {tables}, {database_size}; "
            f"сертификаты: {certificates}; SHA-256: {sha256}."
        )
        log_operation("backup.full.verify", f"backup:{original_name}", message)
        flash(message, "success")
        return redirect(url_for("maintenance", tab="backups"))

    @app.post("/maintenance/backups")
    def create_backup_route():
        backup = create_backup()
        flash(f"Резервная копия создана: {backup.name}", "success")
        return redirect(url_for("maintenance"))

    @app.post("/maintenance/backups/delete-old")
    def delete_old_backups_route():
        result = delete_old_backups()
        freed = _format_bytes(result.freed_bytes)
        if result.failed_names:
            flash(
                f"Удалены {result.deleted_count} старые копии, освобождено {freed}. "
                f"Не удалось удалить: {', '.join(result.failed_names)}",
                "error",
            )
        elif result.deleted_count:
            flash(
                f"Удалены {result.deleted_count} старые копии, освобождено {freed}. "
                f"Сохранены {result.kept_count} последние копии.",
                "success",
            )
        else:
            flash("Старых резервных копий для удаления нет.", "success")
        return redirect(url_for("maintenance", tab="backups"))

    def _restore_backup_response(name: str, destination_endpoint: str):
        restored = restore_backup_transaction(name)
        if not restored.ok or restored.backup is None:
            flash(restored.message, "error")
            return redirect(url_for(destination_endpoint))

        runtime = run_hostd_command("xray.restore.apply", timeout=180)
        if runtime.status != "ok":
            rollback_ok = restore_safety_backup(restored.safety_backup)
            recovery = (
                run_hostd_command("xray.restore.apply", timeout=180)
                if rollback_ok
                else None
            )
            recovery_note = (
                " Прежняя база и Xray восстановлены."
                if recovery is not None and recovery.status == "ok"
                else " Автоматическое восстановление прежнего runtime требует проверки."
            )
            flash(
                "Restore отменён: восстановленный Xray candidate не применился. "
                + runtime.message
                + recovery_note,
                "error",
            )
            return redirect(url_for(destination_endpoint))

        confirm_restore_runtime(restored.backup.name)
        flash(
            f"Резервная копия восстановлена и Xray проверен: {restored.backup.name}",
            "success",
        )
        return redirect(url_for(destination_endpoint))

    @app.post("/maintenance/backups/<name>/restore")
    def restore_backup_route(name: str):
        return _restore_backup_response(name, "maintenance")

    @app.post("/recovery/backups/<name>/restore")
    def recovery_restore_backup_route(name: str):
        if not is_authenticated():
            return redirect(url_for("login", next=url_for("recovery", restore=name)))
        return _restore_backup_response(name, "recovery")

    @app.get("/maintenance/backups/<name>/download")
    def download_backup_route(name: str):
        backup = get_backup(name)
        if backup is None:
            abort(404)
        return send_file(backup.path, as_attachment=True, download_name=backup.name)

    @app.get("/maintenance/diagnostics.json")
    def download_diagnostics():
        return Response(
            build_diagnostic_report_json(),
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=sg-gateway-diagnostics.json"},
        )

    @app.get("/help")
    def help_index():
        return render_template("help.html", active_page="help", topics=list_topics(), topic=None)

    @app.get("/help/<slug>")
    def help_topic(slug: str):
        topic = get_topic(slug)
        if topic is None:
            abort(404)
        return render_template("help.html", active_page="help", topics=list_topics(), topic=topic)

    @app.get("/api/system/activity")
    def system_activity_api():
        activity = collect_system_activity()
        clients = list_clients()
        activity["clients"] = {
            "total": len(clients),
            "enabled": sum(1 for client in clients if bool(getattr(client, "enabled", False))),
            "devices_total": sum(int(getattr(client, "device_count", 0) or 0) for client in clients),
            "devices_enabled": sum(int(getattr(client, "active_device_count", 0) or 0) for client in clients),
        }
        return jsonify(activity)

    @app.get("/api/status")
    def api_status():
        report = build_diagnostic_report()
        return jsonify(
            {
                "service": report["service"],
                "version": report["version"],
                "status": report["health"],
                "environment": report["environment"],
                "clients": report["summary"]["clients"],
                "backups": report["summary"]["backups"],
                "connections": report["connections"],
                "health_checks": report["health_checks"],
            }
        )

    @app.get("/api/version")
    def api_version():
        return jsonify(get_release_manifest())

    @app.get("/health")
    def health():
        # Liveness endpoint used by systemd/Nginx and the installer.
        # Optional engines (Mihomo, AWG, TLS, GeoFiles) are intentionally not
        # part of liveness: a panel can be healthy while those features are
        # unconfigured or stopped. Full diagnostics remain available through
        # /api/status and Maintenance.
        return jsonify(
            {
                "service": "sg-gateway-panel",
                "version": get_version(),
                "status": "ok",
            }
        ), 200

    return app


app = create_app()
