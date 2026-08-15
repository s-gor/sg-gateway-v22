from __future__ import annotations

import json
import os
import pwd
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Iterable


class RoutingRuntimeError(RuntimeError):
    pass


def xray_config_path() -> Path:
    return Path(os.getenv("SG_GATEWAY_XRAY_CONFIG", "/usr/local/etc/xray/config.json"))


def managed_routing_path() -> Path:
    return Path(
        os.getenv(
            "SG_GATEWAY_ROUTING_MANAGED_PATH",
            "/etc/sg-gateway/xray-routing-managed.json",
        )
    )


def xray_asset_dir() -> Path:
    return Path(os.getenv("SG_GATEWAY_XRAY_ASSET_DIR", "/usr/local/share/xray"))


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _xray_service_user() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "show", "-p", "User", "--value", "xray.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "root"
    return result.stdout.strip() or "root"


def set_xray_config_permissions(path: Path | None = None) -> None:
    # SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY
    target = path or xray_config_path()
    if not target.exists():
        return
    if os.geteuid() == 0:
        try:
            os.chown(target, 0, 0)
        except OSError:
            pass
    os.chmod(target, 0o777)
    try:
        os.chmod(target.parent, 0o777)
    except OSError:
        pass


def atomic_write_json(path: Path, payload: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if path == xray_config_path():
        set_xray_config_permissions(temporary)
    else:
        os.chmod(temporary, mode)
    os.replace(temporary, path)


def default_routing() -> dict:
    # Unmatched traffic uses the first Xray outbound (direct).  Keeping that
    # fallback implicit preserves a known-good Preview 39 runtime during a
    # panel-only update and avoids manufacturing a needless catch-all rule.
    return {"routing": {"domainStrategy": "AsIs", "rules": []}}


def sanitize_managed_fragment(fragment: dict | None) -> dict:
    if not isinstance(fragment, dict):
        return default_routing()
    routing = fragment.get("routing")
    if not isinstance(routing, dict):
        raise RoutingRuntimeError("Managed Routing не содержит объект routing")
    rules = routing.get("rules")
    if not isinstance(rules, list):
        raise RoutingRuntimeError("Managed Routing не содержит список rules")

    cleaned: list[dict] = []
    for index, raw in enumerate(rules, start=1):
        if not isinstance(raw, dict):
            raise RoutingRuntimeError(f"Routing rule {index} имеет неверный формат")
        tag = str(raw.get("outboundTag") or "").strip()
        if tag not in {"direct", "warp", "block"}:
            raise RoutingRuntimeError(
                f"Routing rule {index}: разрешены только outboundTag direct, warp и block"
            )
        item = dict(raw)
        item["type"] = "field"
        item["outboundTag"] = tag
        cleaned.append(item)

    result = {
        "routing": {
            "domainStrategy": str(
                routing.get("domainStrategy")
                or ("IPIfNonMatch" if cleaned else "AsIs")
            ),
            "rules": cleaned,
        }
    }
    try:
        from app.routing.warp import ensure_routing_supported

        ensure_routing_supported(result)
    except ImportError:
        pass
    except Exception as exc:
        raise RoutingRuntimeError(str(exc)) from exc
    return result


def load_managed_fragment() -> dict:
    value = _read_json(managed_routing_path())
    routing = value.get("routing") if isinstance(value, dict) else None
    rules = routing.get("rules") if isinstance(routing, dict) else None
    if isinstance(rules, list):
        legacy_tags = {
            str(item.get("outboundTag") or "").strip().lower()
            for item in rules
            if isinstance(item, dict)
        } & {"xray", "proxy", "vpn"}
        if legacy_tags:
            # Preview 40 could persist a decorative outbound. Migrate only
            # that known legacy defect to Direct. WARP failures must remain
            # fail-closed and must never be converted into a silent fallback.
            return default_routing()
    return sanitize_managed_fragment(value)


def extract_geo_references(payload: object) -> tuple[set[str], set[str]]:
    geoip: set[str] = set()
    geosite: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered.startswith("geoip:") and len(lowered) > 6:
                geoip.add(lowered[6:])
            elif lowered.startswith("geosite:") and len(lowered) > 8:
                geosite.add(lowered[8:])

    visit(payload)
    return geoip, geosite


def active_geo_references() -> tuple[set[str], set[str]]:
    config = _read_json(xray_config_path()) or {}
    managed = _read_json(managed_routing_path()) or {}
    ip_a, site_a = extract_geo_references(config.get("routing", {}))
    ip_b, site_b = extract_geo_references(managed)
    return ip_a | ip_b, site_a | site_b


def missing_geo_references(
    payload: object,
    *,
    geoip_categories: Iterable[str],
    geosite_categories: Iterable[str],
) -> tuple[str, ...]:
    required_ip, required_site = extract_geo_references(payload)
    available_ip = {str(item).lower() for item in geoip_categories}
    available_site = {str(item).lower() for item in geosite_categories}
    missing = [f"geoip:{item}" for item in sorted(required_ip - available_ip)]
    missing.extend(f"geosite:{item}" for item in sorted(required_site - available_site))
    return tuple(missing)


def build_full_config(
    routing_fragment: dict | None = None,
    *,
    base_config: dict | None = None,
) -> dict:
    config = dict(base_config or _read_json(xray_config_path()) or {})
    if not config:
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [],
            "outbounds": [
                {"tag": "direct", "protocol": "freedom"},
                {"tag": "block", "protocol": "blackhole"},
            ],
        }

    outbounds = config.get("outbounds")
    if not isinstance(outbounds, list):
        outbounds = []
    direct = next(
        (dict(item) for item in outbounds if isinstance(item, dict) and item.get("tag") == "direct"),
        {"tag": "direct", "protocol": "freedom"},
    )
    block = next(
        (dict(item) for item in outbounds if isinstance(item, dict) and item.get("tag") == "block"),
        {"tag": "block", "protocol": "blackhole"},
    )
    rest = [
        dict(item)
        for item in outbounds
        if isinstance(item, dict) and item.get("tag") not in {"direct", "warp", "block"}
    ]
    managed_outbounds = [direct]
    try:
        from app.routing.warp import outbound as warp_outbound

        warp = warp_outbound(require_enabled=True)
        if warp is not None:
            managed_outbounds.append(warp)
    except ImportError:
        pass
    except Exception as exc:
        raise RoutingRuntimeError(str(exc)) from exc
    managed_outbounds.append(block)
    managed_outbounds.extend(rest)
    config["outbounds"] = managed_outbounds

    fragment = sanitize_managed_fragment(
        routing_fragment if routing_fragment is not None else load_managed_fragment()
    )
    config["routing"] = fragment["routing"]
    return config


def _find_xray() -> str | None:
    for candidate in (shutil.which("xray"), "/usr/local/bin/xray", "/usr/bin/xray"):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def xray_test_config(
    config: dict,
    *,
    asset_dir: Path | None = None,
    timeout: int = 90,
) -> tuple[str, str]:
    xray = _find_xray()
    if xray is None:
        return "warning", "Xray не установлен: выполнена только структурная проверка"

    with tempfile.TemporaryDirectory(prefix="sg-gateway-routing-runtime-") as directory:
        path = Path(directory) / "config.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["XRAY_LOCATION_ASSET"] = str(asset_dir or xray_asset_dir())
        messages: list[str] = []
        for command in (
            [xray, "run", "-test", "-config", str(path)],
            [xray, "-test", "-config", str(path)],
        ):
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
                check=False,
            )
            if result.returncode == 0:
                return "ok", (result.stdout or result.stderr or "Xray config accepted").strip()
            messages.append((result.stderr or result.stdout or "").strip())
    return "error", "; ".join(item for item in messages if item) or "Xray test failed"


def service_is_active() -> bool:
    if shutil.which("systemctl") is None:
        return False
    return (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            check=False,
        ).returncode
        == 0
    )


def restart_xray(*, required: bool) -> tuple[str, str]:
    if shutil.which("systemctl") is None:
        return ("error", "systemctl недоступен") if required else ("warning", "systemctl недоступен")
    result = subprocess.run(
        ["systemctl", "restart", "xray.service"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        return "error", (result.stderr or result.stdout or "restart failed").strip()
    if service_is_active():
        return "ok", "xray.service перезапущен и активен"
    return "error", "xray.service не активен после перезапуска"


def apply_full_config(config: dict, *, restart_if_active: bool = True) -> tuple[str, str]:
    status, message = xray_test_config(config)
    if status == "error":
        raise RoutingRuntimeError(message)
    target = xray_config_path()
    was_active = service_is_active()
    atomic_write_json(target, config, 0o600)
    if restart_if_active and was_active:
        restart_status, restart_message = restart_xray(required=True)
        if restart_status == "error":
            raise RoutingRuntimeError(restart_message)
        return restart_status, restart_message
    return status, message or "Xray config сохранён"


def build_roscom_direct_block_fragment(
    *,
    geosite_categories: Iterable[str],
    geoip_categories: Iterable[str],
    block_ads: bool = False,
    block_windows_telemetry: bool = False,
    block_torrent: bool = False,
) -> dict:
    sites = {str(item).lower() for item in geosite_categories}
    ips = {str(item).lower() for item in geoip_categories}
    direct_sites = (
        "private",
        "whitelist",
        "category-ru",
        "apple",
        "microsoft",
        "steam",
        "epicgames",
        "riot",
        "escapefromtarkov",
        "faceit",
        "pinterest",
    )
    direct_ips = ("private", "whitelist", "direct")
    requested_blocks: list[str] = []
    if block_ads:
        requested_blocks.append("category-ads")
    if block_windows_telemetry:
        requested_blocks.append("win-spy")
    if block_torrent:
        requested_blocks.append("torrent")

    missing_blocks = [item for item in requested_blocks if item not in sites]
    if missing_blocks:
        raise RoutingRuntimeError(
            "В RoscomVPN отсутствуют выбранные категории: "
            + ", ".join(f"geosite:{item}" for item in missing_blocks)
        )

    rules: list[dict] = []
    for category in direct_sites:
        if category in sites:
            rules.append(
                {
                    "type": "field",
                    "domain": [f"geosite:{category}"],
                    "outboundTag": "direct",
                }
            )
    for category in direct_ips:
        if category in ips:
            rules.append(
                {
                    "type": "field",
                    "ip": [f"geoip:{category}"],
                    "outboundTag": "direct",
                }
            )
    for category in requested_blocks:
        rules.append(
            {
                "type": "field",
                "domain": [f"geosite:{category}"],
                "outboundTag": "block",
            }
        )
    return sanitize_managed_fragment(
        {"routing": {"domainStrategy": "IPIfNonMatch", "rules": rules}}
    )
