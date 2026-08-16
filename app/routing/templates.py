from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import load_config
from app.hostd.client import run_hostd_command
from app.maintenance.operations import log_operation
from app.routing.geofiles import GeoFilesError, overview as geofiles_overview
from app.routing.runtime import (
    RoutingRuntimeError,
    atomic_write_json,
    build_full_config,
    build_managed_outbounds,
    managed_routing_path,
    restart_xray,
    routing_capabilities,
    sanitize_managed_fragment,
    service_is_active,
    xray_config_path,
    xray_test_config,
)


class RoutingTemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuleSpec:
    title: str
    action: str
    geosite_any: tuple[str, ...] = ()
    geoip_any: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    ips: tuple[str, ...] = ()
    catch_all: bool = False
    required: bool = True


@dataclass(frozen=True)
class TemplateSpec:
    template_id: str
    title: str
    summary: str
    recommended_action: str
    rules: tuple[RuleSpec, ...]


TEMPLATES = (
    TemplateSpec(
        "private-direct",
        "Private / LAN → Через SG-Gateway",
        "Локальные сети и приватные адреса не отправляются во внешний proxy.",
        "direct",
        (
            RuleSpec(
                "Приватные домены",
                "direct",
                geosite_any=("private",),
                required=False,
            ),
            RuleSpec(
                "Приватные IP",
                "direct",
                geoip_any=("private",),
            ),
        ),
    ),
    TemplateSpec(
        "ru-tld-direct",
        "Российские доменные зоны → Через SG-Gateway",
        "Проверенный шаблон на основе geosite:tld-ru.",
        "direct",
        (
            RuleSpec(
                "Российские доменные зоны",
                "direct",
                geosite_any=("tld-ru",),
            ),
        ),
    ),
    TemplateSpec(
        "ru-sites-ip-direct",
        "Российские сайты и IP → Через SG-Gateway",
        "Проверенный шаблон geosite:category-ru + geoip:ru.",
        "direct",
        (
            RuleSpec(
                "Российские сайты",
                "direct",
                geosite_any=("category-ru",),
            ),
            RuleSpec(
                "Российские IP",
                "direct",
                geoip_any=("ru",),
            ),
        ),
    ),
    TemplateSpec(
        "ru-restricted-xray",
        "Российские ограничения → Xray",
        "Использует только реально найденную категорию блокировок текущего GeoSite.",
        "xray",
        (
            RuleSpec(
                "Ресурсы, заблокированные в РФ",
                "xray",
                geosite_any=(
                    "russia-blocked",
                    "ru-blocked",
                    "category-ru-blocked",
                    "antifilter",
                    "refilter",
                    "blocked",
                ),
            ),
        ),
    ),
    TemplateSpec(
        "ads-block",
        "Реклама и трекеры → Заблокировать",
        "Блокирует рекламу только при наличии подходящей категории в текущем комплекте.",
        "block",
        (
            RuleSpec(
                "Реклама и трекеры",
                "block",
                geosite_any=(
                    "category-ads-all",
                    "category-ads",
                    "ads",
                    "adguard",
                ),
            ),
        ),
    ),
    TemplateSpec(
        "ai-developer-xray",
        "AI & Developer → Xray",
        "Собирает только доступные категории AI и developer-сервисов.",
        "xray",
        (
            RuleSpec(
                "AI-сервисы",
                "xray",
                geosite_any=(
                    "category-ai-chat-!cn",
                    "category-ai-!cn",
                    "openai",
                    "anthropic",
                    "claude",
                    "gemini",
                ),
                required=False,
            ),
            RuleSpec(
                "Developer-сервисы",
                "xray",
                geosite_any=(
                    "github",
                    "gitlab",
                    "stackoverflow",
                    "category-dev",
                ),
                required=False,
            ),
        ),
    ),
    TemplateSpec(
        "media-social-xray",
        "Media & Social → Xray",
        "Видео, социальные сети и мессенджеры по реально доступным категориям.",
        "xray",
        (
            RuleSpec(
                "Media",
                "xray",
                geosite_any=(
                    "youtube",
                    "netflix",
                    "spotify",
                    "twitch",
                    "category-media",
                ),
                required=False,
            ),
            RuleSpec(
                "Social и Messengers",
                "xray",
                geosite_any=(
                    "telegram",
                    "discord",
                    "facebook",
                    "instagram",
                    "twitter",
                    "category-social-media-!cn",
                ),
                required=False,
            ),
        ),
    ),
    TemplateSpec(
        "maximum-xray",
        "Максимум через Xray",
        "Сначала исключает private/LAN, затем направляет остальной трафик в Xray.",
        "xray",
        (
            RuleSpec(
                "Приватные IP",
                "direct",
                geoip_any=("private",),
            ),
            RuleSpec(
                "Весь остальной трафик",
                "xray",
                catch_all=True,
            ),
        ),
    ),
)


# SG-Gateway has no Cascade/Node/upstream. Never expose templates that need a
# non-existent proxy outbound.
TEMPLATES = tuple(
    template
    for template in TEMPLATES
    if all(rule.action in {"direct", "block"} for rule in template.rules)
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir() -> Path:
    override = os.getenv("SG_GATEWAY_ROUTING_STATE_DIR", "").strip()
    return Path(override) if override else load_config().data_dir / "routing"


def _candidate_path() -> Path:
    return _state_dir() / "candidate.json"


def _active_path() -> Path:
    return _state_dir() / "active-managed.json"


def _backups_dir() -> Path:
    return _state_dir() / "backups"


def _ensure_dirs() -> None:
    _state_dir().mkdir(parents=True, exist_ok=True)
    _backups_dir().mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temp, mode)
    os.replace(temp, path)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _available_categories() -> tuple[set[str], set[str]]:
    geo = geofiles_overview().get("active") or {}
    geoip = set(geo.get("geoip", {}).get("categories", []))
    geosite = set(geo.get("geosite", {}).get("categories", []))
    return geoip, geosite


def _choose(options: tuple[str, ...], available: set[str]) -> str | None:
    return next((item for item in options if item in available), None)


def _build_rule(spec: RuleSpec, geoip: set[str], geosite: set[str]) -> dict:
    selected_site = _choose(spec.geosite_any, geosite)
    selected_ip = _choose(spec.geoip_any, geoip)
    missing = []
    if spec.geosite_any and selected_site is None:
        missing.append("geosite:" + " | ".join(spec.geosite_any))
    if spec.geoip_any and selected_ip is None:
        missing.append("geoip:" + " | ".join(spec.geoip_any))

    enabled = not missing
    xray_rule: dict = {
        "type": "field",
        "outboundTag": spec.action,
    }
    if selected_site:
        xray_rule["domain"] = [f"geosite:{selected_site}"]
    if selected_ip:
        xray_rule["ip"] = [f"geoip:{selected_ip}"]
    if spec.domains:
        xray_rule.setdefault("domain", []).extend(spec.domains)
    if spec.ips:
        xray_rule.setdefault("ip", []).extend(spec.ips)
    if spec.catch_all:
        xray_rule["network"] = "tcp,udp"

    return {
        "title": spec.title,
        "action": spec.action,
        "enabled": enabled,
        "required": spec.required,
        "selected_geosite": selected_site,
        "selected_geoip": selected_ip,
        "missing": missing,
        "xray_rule": xray_rule if enabled else None,
    }


def preview_template(template_id: str, mode: str = "replace_managed") -> dict:
    spec = next((item for item in TEMPLATES if item.template_id == template_id), None)
    if spec is None:
        raise RoutingTemplateError("Неизвестный шаблон Routing")
    if mode not in {"append", "replace_managed"}:
        raise RoutingTemplateError("Неизвестный режим применения шаблона")

    geoip, geosite = _available_categories()
    rules = [_build_rule(rule, geoip, geosite) for rule in spec.rules]
    required_missing = [
        item for item in rules if item["required"] and not item["enabled"]
    ]
    enabled_rules = [
        item["xray_rule"] for item in rules if item["enabled"] and item["xray_rule"]
    ]
    if not enabled_rules:
        ready = False
        message = "В активных GeoFiles не найдено ни одной подходящей категории"
    elif required_missing:
        ready = False
        message = "Не найдены обязательные категории для шаблона"
    else:
        ready = True
        message = "Шаблон совместим с активными GeoFiles"

    return {
        "template_id": spec.template_id,
        "title": spec.title,
        "summary": spec.summary,
        "recommended_action": spec.recommended_action,
        "mode": mode,
        "checked_at": _utc_now(),
        "ready": ready,
        "message": message,
        "rules": rules,
        "managed_fragment": {
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": enabled_rules,
            }
        },
    }


def stage_template(template_id: str, mode: str = "replace_managed") -> dict:
    _ensure_dirs()
    preview = preview_template(template_id, mode)
    if not preview["ready"]:
        raise RoutingTemplateError(preview["message"])
    _write_json(_candidate_path(), preview)
    log_operation(
        "routing.template.check",
        f"routing-template:{template_id}",
        f"Шаблон подготовлен: {preview['title']}",
    )
    return preview


def _helper_path() -> Path:
    return Path(
        os.getenv(
            "SG_GATEWAY_ROUTING_HELPER",
            "/usr/local/lib/sg-gateway/routing-helper",
        )
    )


def _run_helper(action: str) -> dict:
    command = f"routing.{action}"
    result = run_hostd_command(command, timeout=180)
    if result.status != "ok":
        raise RoutingTemplateError(result.message or f"{command} failed")

    payload = dict(result.payload)
    payload.setdefault("ok", True)
    payload.setdefault("message", result.message)
    return payload


def apply_candidate() -> dict:
    candidate = _read_json(_candidate_path())
    if not candidate or not candidate.get("ready"):
        raise RoutingTemplateError("Сначала подготовьте совместимый candidate")
    payload = _run_helper("apply")
    log_operation(
        "routing.template.apply",
        f"routing-template:{candidate.get('template_id', 'unknown')}",
        str(payload.get("message", "Routing template applied")),
    )
    return payload


def rollback_latest() -> dict:
    payload = _run_helper("rollback")
    log_operation(
        "routing.template.rollback",
        "routing-template:active",
        str(payload.get("message", "Routing template restored")),
    )
    return payload


def overview() -> dict:
    _ensure_dirs()
    geoip, geosite = _available_categories()
    templates = []
    for spec in TEMPLATES:
        preview = preview_template(spec.template_id)
        templates.append(
            {
                "template_id": spec.template_id,
                "title": spec.title,
                "summary": spec.summary,
                "recommended_action": spec.recommended_action,
                "ready": preview["ready"],
                "message": preview["message"],
                "rule_count": len(
                    [
                        item
                        for item in preview["rules"]
                        if item["enabled"] and item["xray_rule"]
                    ]
                ),
            }
        )
    return {
        "templates": templates,
        "candidate": _read_json(_candidate_path()),
        "active": _read_json(_active_path()),
        "backups": [
            item.name
            for item in sorted(_backups_dir().glob("*.json"), reverse=True)[:10]
        ],
        "geoip_count": len(geoip),
        "geosite_count": len(geosite),
        "managed_path": "/etc/sg-gateway/xray-routing-managed.json",
        "capabilities": routing_capabilities(),
        "engine_connected": True,
        "engine_message": (
            "Managed Routing подключён к рабочему config.json Xray. "
            "Выходы разделены по семейству: SG-Gateway IPv4/IPv6, WARP IPv4/IPv6 и Block."
        ),
    }


def _minimal_xray_test(fragment: dict) -> tuple[str, str]:
    xray = shutil.which("xray") or (
        "/usr/local/bin/xray" if Path("/usr/local/bin/xray").is_file() else None
    )
    if not xray:
        return "warning", "Xray не установлен: выполнена JSON- и GeoFiles-проверка"
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [],
        "outbounds": build_managed_outbounds([]),
        **fragment,
    }
    with tempfile.TemporaryDirectory(prefix="sg-gateway-routing-") as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        env = dict(os.environ)
        env["XRAY_LOCATION_ASSET"] = str(
            Path(os.getenv("SG_GATEWAY_XRAY_ASSET_DIR", "/usr/local/share/xray"))
        )
        for command in (
            [xray, "run", "-test", "-config", str(path)],
            [xray, "-test", "-config", str(path)],
        ):
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
                check=False,
            )
            if result.returncode == 0:
                return "ok", "Xray принял управляемый Routing fragment"
    return "error", (result.stderr or result.stdout).strip() or "Xray test failed"


def root_apply_candidate() -> dict:
    _ensure_dirs()
    candidate = _read_json(_candidate_path())
    if not candidate or not candidate.get("ready"):
        raise RoutingTemplateError("Routing candidate отсутствует или не готов")
    try:
        fragment = sanitize_managed_fragment(candidate.get("managed_fragment"))
    except RoutingRuntimeError as exc:
        raise RoutingTemplateError(str(exc)) from exc

    config_path = xray_config_path()
    managed_path = managed_routing_path()
    old_config = _read_json(config_path)
    old_managed = _read_json(managed_path)
    full_candidate = build_full_config(fragment, base_config=old_config)
    status, message = xray_test_config(full_candidate)
    if status == "error":
        raise RoutingTemplateError(message)

    backup = _backups_dir() / (
        datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".json"
    )
    _write_json(
        backup,
        {"managed": old_managed, "config": old_config, "created_at": _utc_now()},
    )
    was_active = service_is_active()
    try:
        atomic_write_json(managed_path, fragment, 0o640)
        if old_config is not None:
            atomic_write_json(config_path, full_candidate, 0o600)
            if was_active:
                restart_status, restart_message = restart_xray(required=True)
                if restart_status == "error":
                    raise RoutingTemplateError(restart_message)
                message = restart_message
    except Exception as exc:
        if old_managed is None:
            managed_path.unlink(missing_ok=True)
        else:
            atomic_write_json(managed_path, old_managed, 0o640)
        if old_config is None:
            config_path.unlink(missing_ok=True)
        else:
            atomic_write_json(config_path, old_config, 0o600)
        if was_active and old_config is not None:
            restart_xray(required=False)
        if isinstance(exc, RoutingTemplateError):
            raise
        raise RoutingTemplateError(str(exc)) from exc

    active = {
        **candidate,
        "managed_fragment": fragment,
        "applied_at": _utc_now(),
        "validation": status,
        "validation_message": message,
        "engine_connected": True,
    }
    _write_json(_active_path(), active, mode=0o644)
    return {
        "ok": True,
        "message": "Routing применён к рабочему Xray config.json. " + message,
        "backup": backup.name,
    }


def root_rollback_latest() -> dict:
    backups = sorted(_backups_dir().glob("*.json"), reverse=True)
    if not backups:
        raise RoutingTemplateError("Нет резервной копии Routing")
    source = backups[0]
    payload = _read_json(source)
    if payload is None:
        raise RoutingTemplateError("Последняя резервная копия Routing повреждена")

    # Preview 40 stored only the managed fragment. Preview 41 stores both files.
    if "managed" in payload or "config" in payload:
        managed = payload.get("managed")
        config = payload.get("config")
    else:
        managed = payload
        config = None

    managed_path = managed_routing_path()
    config_path = xray_config_path()
    current_managed = _read_json(managed_path)
    current_config = _read_json(config_path)
    was_active = service_is_active()
    try:
        if managed is None:
            managed_path.unlink(missing_ok=True)
        else:
            managed = sanitize_managed_fragment(managed)
            atomic_write_json(managed_path, managed, 0o640)
        if config is not None:
            status, message = xray_test_config(config)
            if status == "error":
                raise RoutingTemplateError(message)
            atomic_write_json(config_path, config, 0o600)
            if was_active:
                restart_status, restart_message = restart_xray(required=True)
                if restart_status == "error":
                    raise RoutingTemplateError(restart_message)
    except Exception as exc:
        if current_managed is None:
            managed_path.unlink(missing_ok=True)
        else:
            atomic_write_json(managed_path, current_managed, 0o640)
        if current_config is None:
            config_path.unlink(missing_ok=True)
        else:
            atomic_write_json(config_path, current_config, 0o600)
        if was_active and current_config is not None:
            restart_xray(required=False)
        if isinstance(exc, RoutingTemplateError):
            raise
        raise RoutingTemplateError(str(exc)) from exc

    return {
        "ok": True,
        "message": f"Routing и рабочий Xray config восстановлены из {source.name}",
    }


# SG Client 096 layout retained, but Fix30 makes every public egress action
# family-explicit. Legacy direct/warp values are still parsed for old saved
# candidates and are treated by runtime as strict IPv4 aliases.
SMART_PRESET_TITLES = {
    "direct": "Обычный доступ · SG-Gateway · IPv4",
    "ads_block": "Блокировка рекламы и трекеров · SG-Gateway · IPv4",
    "blocked_warp": "Ресурсы, заблокированные в РФ через WARP · IPv4",
    "all_warp": "Весь интернет через WARP · IPv4",
    "custom": "Пользовательская схема",
}
SMART_ACTIONS = {"direct", "warp", "direct4", "direct6", "warp4", "warp6", "block"}
SMART_RUSSIA_SCOPES = {"none", "tld", "sites_ip"}
SMART_BLOCKED_CATEGORIES = (
    "russia-blocked",
    "ru-blocked",
    "category-ru-blocked",
    "antifilter",
    "refilter",
    "blocked",
)
SMART_ADS_CATEGORIES = ("category-ads-all", "category-ads", "ads", "adguard")
SMART_PRIVATE_IPS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
)


def _smart_default() -> dict:
    # Legacy direct defaults are intentional for loading old forms/tests.  The
    # current UI posts direct4/direct6 explicitly for every visible selector.
    return {
        "preset": "direct",
        "local_action": "direct",
        "russia_scope": "none",
        "russia_action": "direct",
        "blocked_action": "direct",
        "ads_action": "direct",
        "default_action": "direct",
        "custom_direct4_domains": [],
        "custom_direct6_domains": [],
        "custom_warp4_domains": [],
        "custom_warp6_domains": [],
        "custom_block_domains": [],
        "custom_direct4_ips": [],
        "custom_direct6_ips": [],
        "custom_warp4_ips": [],
        "custom_warp6_ips": [],
        "custom_block_ips": [],
        # Old field names remain input-only compatibility buckets.
        "custom_direct_domains": [],
        "custom_warp_domains": [],
        "custom_direct_ips": [],
        "custom_warp_ips": [],
    }


def _smart_lines(value: object) -> list[str]:
    raw = str(value or "").replace("\r", "\n").replace(",", "\n").replace(";", "\n")
    result: list[str] = []
    for item in raw.split("\n"):
        item = item.strip()
        if item and not item.startswith("#") and item not in result:
            result.append(item)
    return result


def _smart_domain(value: str) -> str:
    item = value.strip()
    if not item:
        return ""
    prefixes = ("domain:", "full:", "regexp:", "keyword:", "geosite:")
    if item.lower().startswith(prefixes):
        return item.lower() if item.lower().startswith("geosite:") else item
    item = item.split("://", 1)[-1].split("/", 1)[0].strip().strip(".").lower()
    return f"domain:{item}" if item else ""


def _smart_ip(value: str) -> str:
    import ipaddress

    item = value.strip()
    if not item:
        return ""
    if item.lower().startswith("geoip:"):
        return item.lower()
    try:
        if "/" in item:
            return str(ipaddress.ip_network(item, strict=False))
        address = ipaddress.ip_address(item)
        return f"{address}/{32 if address.version == 4 else 128}"
    except ValueError:
        return ""


def _smart_action(value: object, fallback: str = "direct") -> str:
    action = str(value or "").strip().lower()
    return action if action in SMART_ACTIONS else fallback


def _canonical_family_action(action: str) -> str:
    return {"direct": "direct4", "warp": "warp4"}.get(action, action)


def _actions_equivalent(left: str, right: str) -> bool:
    return _canonical_family_action(left) == _canonical_family_action(right)


def _smart_apply_preset(state: dict) -> dict:
    preset = str(state.get("preset") or "direct").strip().lower()
    if preset not in SMART_PRESET_TITLES:
        preset = "direct"
    state["preset"] = preset
    state["local_action"] = "direct4"
    state.update(
        russia_scope="none",
        russia_action="direct4",
        blocked_action="direct4",
        ads_action="direct4",
        default_action="direct4",
    )
    if preset == "ads_block":
        state["ads_action"] = "block"
    elif preset == "blocked_warp":
        state["blocked_action"] = "warp4"
    elif preset == "all_warp":
        state["blocked_action"] = "warp4"
        state["ads_action"] = "warp4"
        state["default_action"] = "warp4"
    return state


def _parse_custom_values(form, state: dict, key: str, parser) -> None:
    value = form.get(key)
    if value is None:
        return
    state[key] = [item for item in (parser(v) for v in _smart_lines(value)) if item]


def _smart_state_from_form(form) -> dict:
    state = _smart_default()
    state["preset"] = str(form.get("preset", "direct")).strip().lower()
    for key in (
        "local_action",
        "russia_action",
        "blocked_action",
        "ads_action",
        "default_action",
    ):
        state[key] = _smart_action(form.get(key), state[key])
    scope = str(form.get("russia_scope", "none")).strip().lower()
    state["russia_scope"] = scope if scope in SMART_RUSSIA_SCOPES else "none"

    for action in ("direct4", "direct6", "warp4", "warp6", "block", "direct", "warp"):
        _parse_custom_values(form, state, f"custom_{action}_domains", _smart_domain)
        _parse_custom_values(form, state, f"custom_{action}_ips", _smart_ip)

    if state["preset"] != "custom":
        state = _smart_apply_preset(state)
    return state


def _smart_outbound(action: str) -> str:
    return action if action in SMART_ACTIONS else "direct"


def _smart_rule(title: str, action: str, *, domains=None, ips=None, missing=None) -> dict:
    domains = list(domains or [])
    ips = list(ips or [])
    missing = list(missing or [])
    rule: dict = {"type": "field", "outboundTag": _smart_outbound(action)}
    if domains:
        rule["domain"] = domains
    if ips:
        rule["ip"] = ips
    enabled = not missing and bool(domains or ips)
    return {
        "title": title,
        "action": action,
        "enabled": enabled,
        "required": True,
        "selected_geosite": next((v[8:] for v in domains if v.startswith("geosite:")), None),
        "selected_geoip": next((v[6:] for v in ips if v.startswith("geoip:")), None),
        "missing": missing,
        "xray_rule": rule if enabled else None,
    }


def _smart_build(state: dict) -> dict:
    geoip, geosite = _available_categories()
    rules: list[dict] = []

    custom_groups = (
        ("Пользовательские правила: Заблокировать", "block", state["custom_block_domains"], state["custom_block_ips"]),
        ("Пользовательские правила: SG-Gateway · IPv4", "direct4", state["custom_direct4_domains"], state["custom_direct4_ips"]),
        ("Пользовательские правила: SG-Gateway · IPv6", "direct6", state["custom_direct6_domains"], state["custom_direct6_ips"]),
        ("Пользовательские правила: WARP · IPv4", "warp4", state["custom_warp4_domains"], state["custom_warp4_ips"]),
        ("Пользовательские правила: WARP · IPv6", "warp6", state["custom_warp6_domains"], state["custom_warp6_ips"]),
        # Compatibility for a saved Preview 40/49 candidate.
        ("Пользовательские правила: SG-Gateway · IPv4", "direct", state["custom_direct_domains"], state["custom_direct_ips"]),
        ("Пользовательские правила: WARP · IPv4", "warp", state["custom_warp_domains"], state["custom_warp_ips"]),
    )
    for title, action, domains, ips in custom_groups:
        if domains or ips:
            rules.append(_smart_rule(title, action, domains=domains, ips=ips))

    local_domains = ["geosite:private"] if "private" in geosite else []
    local_ips = ["geoip:private"] if "private" in geoip else list(SMART_PRIVATE_IPS)
    rules.append(
        _smart_rule(
            "Локальная сеть",
            state["local_action"],
            domains=local_domains,
            ips=local_ips,
        )
    )

    scope = state["russia_scope"]
    if scope != "none":
        domains: list[str] = []
        ips: list[str] = []
        missing: list[str] = []
        if scope == "tld":
            if "tld-ru" in geosite:
                domains.append("geosite:tld-ru")
            else:
                missing.append("geosite:tld-ru")
        else:
            if "category-ru" in geosite:
                domains.append("geosite:category-ru")
            else:
                missing.append("geosite:category-ru")
            if "ru" in geoip:
                ips.append("geoip:ru")
            else:
                missing.append("geoip:ru")
        rules.append(
            _smart_rule(
                "Российская маршрутизация",
                state["russia_action"],
                domains=domains,
                ips=ips,
                missing=missing,
            )
        )

    if not _actions_equivalent(state["blocked_action"], state["default_action"]):
        category = _choose(SMART_BLOCKED_CATEGORIES, geosite)
        rules.append(
            _smart_rule(
                "Ресурсы, заблокированные в РФ",
                state["blocked_action"],
                domains=[f"geosite:{category}"] if category else [],
                missing=[] if category else ["geosite:ru-blocked"],
            )
        )

    if not _actions_equivalent(state["ads_action"], state["default_action"]):
        category = _choose(SMART_ADS_CATEGORIES, geosite)
        rules.append(
            _smart_rule(
                "Реклама и трекеры",
                state["ads_action"],
                domains=[f"geosite:{category}"] if category else [],
                missing=[] if category else ["geosite:category-ads"],
            )
        )

    default_action = state["default_action"]
    # Only an old saved `direct` candidate keeps the implicit first-outbound
    # behaviour. Every new Fix30 family action gets an explicit catch-all, so
    # the selected IP family is never inferred from outbound order.
    default_rule = None
    if default_action != "direct":
        default_rule = {
            "type": "field",
            "network": "tcp,udp",
            "outboundTag": default_action,
        }
    rules.append(
        {
            "title": "Остальной трафик",
            "action": default_action,
            "enabled": True,
            "required": True,
            "selected_geosite": None,
            "selected_geoip": None,
            "missing": [],
            "xray_rule": default_rule,
            "implicit_default": default_rule is None,
        }
    )

    caps = routing_capabilities()
    requested_actions = {
        _canonical_family_action(str(item.get("action") or ""))
        for item in rules
        if item.get("enabled")
    }
    for action, label in (
        ("direct6", "SG-Gateway · IPv6"),
        ("warp4", "WARP · IPv4"),
        ("warp6", "WARP · IPv6"),
    ):
        if action in requested_actions and not caps.get(action):
            rules.append(
                {
                    "title": label,
                    "action": action,
                    "enabled": False,
                    "required": True,
                    "selected_geosite": None,
                    "selected_geoip": None,
                    "missing": [f"{label} сейчас недоступен"],
                    "xray_rule": None,
                }
            )

    missing = [item for item in rules if item["missing"]]
    ready = not missing
    enabled_rules = [
        item["xray_rule"]
        for item in rules
        if item["enabled"] and item["xray_rule"]
    ]
    note = (
        "Схема готова: семейство IP зафиксировано отдельно для каждого выбранного выхода"
        if ready
        else "Выбранный выход или категория сейчас недоступны"
    )
    return {
        "template_id": "smart-fix30-ip-family",
        "title": SMART_PRESET_TITLES[state["preset"]],
        "summary": "Family-explicit Routing без автоматического fallback IPv4/IPv6",
        "recommended_action": "direct4",
        "mode": "replace_managed",
        "checked_at": _utc_now(),
        "ready": ready,
        "message": note,
        "smart": state,
        "rules": rules,
        "managed_fragment": {
            "routing": {"domainStrategy": "IPIfNonMatch", "rules": enabled_rules}
        },
    }


def build_roscom_compatible_candidate(
    *,
    geosite_categories: set[str],
    geoip_categories: set[str],
    block_ads: bool = False,
    block_windows_telemetry: bool = False,
    block_torrent: bool = False,
) -> dict:
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
    block_sites: list[str] = []
    if block_ads:
        block_sites.append("category-ads")
    if block_windows_telemetry:
        block_sites.append("win-spy")
    if block_torrent:
        block_sites.append("torrent")

    rules: list[dict] = []
    for category in direct_sites:
        if category in geosite_categories:
            rules.append(
                {
                    "type": "field",
                    "domain": [f"geosite:{category}"],
                    "outboundTag": "direct",
                }
            )
    for category in direct_ips:
        if category in geoip_categories:
            rules.append(
                {
                    "type": "field",
                    "ip": [f"geoip:{category}"],
                    "outboundTag": "direct",
                }
            )
    for category in block_sites:
        if category not in geosite_categories:
            raise RoutingTemplateError(
                f"В RoscomVPN отсутствует выбранная категория geosite:{category}"
            )
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


def stage_smart_routing(form) -> dict:
    _ensure_dirs()
    preview = _smart_build(_smart_state_from_form(form))
    _write_json(_candidate_path(), preview)
    log_operation(
        "routing.smart.check",
        "routing-smart:fix30-ip-family",
        f"Схема подготовлена: {preview['title']}",
    )
    return preview
