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


# Public Routing actions are the five family-explicit tags below.  The legacy
# direct/warp tags remain accepted only so an existing server upgrades to the
# privacy-conservative IPv4 behaviour instead of breaking or silently changing
# address family.
PUBLIC_ROUTING_TAGS = {"direct4", "direct6", "warp4", "warp6", "block"}
LEGACY_ROUTING_TAGS = {"direct", "warp"}
ALLOWED_ROUTING_TAGS = PUBLIC_ROUTING_TAGS | LEGACY_ROUTING_TAGS
MANAGED_OUTBOUND_TAGS = ALLOWED_ROUTING_TAGS | {"warp-core"}


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


def family_gate_outbound(tag: str, family: int, *, proxy_tag: str | None = None) -> dict:
    """Build a fail-closed Xray Freedom family gate.

    ForceIPv4/ForceIPv6 makes a domain fail when the selected DNS family is
    absent.  finalRules additionally rejects a literal destination of the
    opposite family, so an explicit IPv4/IPv6 rule can never fall through to
    the other family.
    """
    if family not in {4, 6}:
        raise RoutingRuntimeError("Поддерживаются только семейства IPv4 и IPv6")
    strategy = "ForceIPv4" if family == 4 else "ForceIPv6"
    opposite_network = "::/0" if family == 4 else "0.0.0.0/0"
    result: dict = {
        "tag": tag,
        "protocol": "freedom",
        "settings": {
            "domainStrategy": strategy,
            # Block only the opposite address family. Traffic in the
            # selected family still passes through Xray's native
            # Freedom final policy, including private-address guards.
            "finalRules": [
                {"action": "block", "ip": [opposite_network], "blockDelay": 0},
            ],
        },
    }
    if proxy_tag:
        result["proxySettings"] = {"tag": proxy_tag}
    return result


def routing_capabilities() -> dict[str, bool]:
    """Return action availability without changing routing state."""
    try:
        from app.config import load_config

        native_ipv6 = bool(load_config().public_ipv6)
    except Exception:
        native_ipv6 = False

    warp_enabled = False
    warp_ipv4 = False
    warp_ipv6 = False
    try:
        from app.routing.warp import enabled as warp_is_enabled, routing_family_capabilities

        warp_enabled = bool(warp_is_enabled())
        families = routing_family_capabilities() if warp_enabled else {"ipv4": False, "ipv6": False}
        warp_ipv4 = warp_enabled and bool(families.get("ipv4"))
        warp_ipv6 = warp_enabled and bool(families.get("ipv6"))
    except Exception:
        pass

    return {
        # IPv4 is SG-Gateway's compatibility baseline.  A server that cannot
        # use it will fail at the actual outbound rather than exposing another
        # family behind the user's back.
        "direct4": True,
        "direct6": native_ipv6,
        "warp4": warp_ipv4,
        "warp6": warp_ipv6,
        "block": True,
        "warp_enabled": warp_enabled,
    }


def validate_outbound_tag(tag: str) -> None:
    tag = str(tag or "").strip().lower()
    if tag not in ALLOWED_ROUTING_TAGS:
        raise RoutingRuntimeError(
            "Разрешены только SG-Gateway IPv4/IPv6, WARP IPv4/IPv6 и Block"
        )
    caps = routing_capabilities()
    if tag == "direct6" and not caps["direct6"]:
        raise RoutingRuntimeError(
            "Выбран SG-Gateway · IPv6, но у сервера нет доступного публичного IPv6"
        )
    if tag in {"warp", "warp4"} and not caps["warp4"]:
        raise RoutingRuntimeError(
            "Выбран WARP · IPv4, но WARP IPv4 не готов или WARP выключен"
        )
    if tag == "warp6" and not caps["warp6"]:
        raise RoutingRuntimeError(
            "Выбран WARP · IPv6, но WARP IPv6 не готов или WARP выключен"
        )


def default_routing() -> dict:
    # Unmatched traffic uses the first managed outbound.  It is the hidden
    # legacy `direct` alias, implemented below as a strict IPv4 gate.  This
    # keeps old installations working without ever auto-falling back to IPv6.
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
        tag = str(raw.get("outboundTag") or "").strip().lower()
        if tag not in ALLOWED_ROUTING_TAGS:
            raise RoutingRuntimeError(
                f"Routing rule {index}: разрешены только direct4, direct6, warp4, warp6 и block"
            )
        try:
            validate_outbound_tag(tag)
        except RoutingRuntimeError as exc:
            raise RoutingRuntimeError(f"Routing rule {index}: {exc}") from exc
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
            # that known legacy defect to the strict IPv4 default. WARP
            # failures remain fail-closed and are never silently bypassed.
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


def build_managed_outbounds(existing_outbounds: list | None = None) -> list[dict]:
    """Build deterministic family-explicit outbounds used by every Xray path."""
    source = existing_outbounds if isinstance(existing_outbounds, list) else []
    block = next(
        (
            dict(item)
            for item in source
            if isinstance(item, dict) and item.get("tag") == "block"
        ),
        {"tag": "block", "protocol": "blackhole"},
    )
    rest = [
        dict(item)
        for item in source
        if isinstance(item, dict)
        and str(item.get("tag") or "") not in MANAGED_OUTBOUND_TAGS
    ]

    # Keep legacy aliases first for backward compatibility with an old managed
    # fragment and with Xray's implicit-first-outbound default.  Both aliases
    # are strict IPv4, never dual-stack fallbacks.
    direct_legacy = family_gate_outbound("direct", 4)
    direct4 = family_gate_outbound("direct4", 4)
    direct6 = family_gate_outbound("direct6", 6)

    managed: list[dict] = [direct_legacy]
    warp_bundle: list[dict] = []
    try:
        from app.routing.warp import outbound as warp_outbound, routing_family_capabilities

        warp = warp_outbound(require_enabled=True)
        if warp is not None:
            core = json.loads(json.dumps(warp))
            core["tag"] = "warp-core"
            families = routing_family_capabilities()
            if families.get("ipv4"):
                # Hidden old `warp` tag is an IPv4-only compatibility alias.
                managed.append(family_gate_outbound("warp", 4, proxy_tag="warp-core"))
                warp_bundle.append(family_gate_outbound("warp4", 4, proxy_tag="warp-core"))
            if families.get("ipv6"):
                warp_bundle.append(family_gate_outbound("warp6", 6, proxy_tag="warp-core"))
            warp_bundle.append(core)
    except ImportError:
        pass
    except Exception as exc:
        raise RoutingRuntimeError(str(exc)) from exc

    # Preserve the historical first-three order when WARP exists so old code
    # reading tags direct/warp/block remains compatible.  New family tags are
    # explicit and are never exposed through those aliases.
    managed.append(block)
    managed.extend((direct4, direct6))
    managed.extend(warp_bundle)
    managed.extend(rest)
    return managed


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
            "outbounds": [],
        }

    outbounds = config.get("outbounds")
    config["outbounds"] = build_managed_outbounds(
        outbounds if isinstance(outbounds, list) else []
    )

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
                    # Keep the legacy tag for RoscomVPN restore compatibility;
                    # it is now a strict IPv4 family gate.
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
