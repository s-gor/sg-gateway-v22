from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
from functools import lru_cache
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable

from app.config import load_config
from app.hostd.client import run_hostd_command
from app.maintenance.operations import log_operation
from app.routing.runtime import (
    RoutingRuntimeError,
    active_geo_references,
    atomic_write_json,
    build_full_config,
    build_roscom_direct_block_fragment,
    load_managed_fragment,
    managed_routing_path,
    restart_xray,
    service_is_active,
    xray_config_path,
    xray_test_config,
)


MIN_GEOIP_SIZE = 1024
MIN_GEOSITE_SIZE = 1024
MAX_DOWNLOAD_SIZE = 160 * 1024 * 1024
GEOFILES_DISK_RESERVE = 64 * 1024 * 1024
CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_!@.+-]{0,95}$")
GEOFILES_LOCK_PATH = Path("/run/sg-gateway/geofiles.lock")

SOURCE_PRESETS = (
    {
        "id": "loyalsoldier",
        "label": "Loyalsoldier",
        "note": "Расширенный универсальный набор для Xray/V2Ray.",
        "geoip_url": (
            "https://github.com/Loyalsoldier/v2ray-rules-dat/"
            "releases/latest/download/geoip.dat"
        ),
        "geosite_url": (
            "https://github.com/Loyalsoldier/v2ray-rules-dat/"
            "releases/latest/download/geosite.dat"
        ),
    },
    {
        "id": "runetfreedom",
        "label": "RunetFreedom",
        "note": "Российские блокировки и белые списки.",
        "geoip_url": (
            "https://raw.githubusercontent.com/runetfreedom/"
            "russia-v2ray-rules-dat/release/geoip.dat"
        ),
        "geosite_url": (
            "https://raw.githubusercontent.com/runetfreedom/"
            "russia-v2ray-rules-dat/release/geosite.dat"
        ),
    },
    {
        "id": "roscomvpn",
        "label": "RoscomVPN",
        "note": "Связанный российский комплект из официальных GitHub Releases.",
        "geoip_url": (
            "https://github.com/hydraponique/roscomvpn-geoip/"
            "releases/latest/download/geoip.dat"
        ),
        "geosite_url": (
            "https://github.com/hydraponique/roscomvpn-geosite/"
            "releases/latest/download/geosite.dat"
        ),
    },
    {
        "id": "sg_client",
        "label": "Встроенная пара SG Client",
        "note": "Используется, если пара добавлена в assets/geofiles SG-Gateway.",
        "geoip_url": "",
        "geosite_url": "",
    },
    {
        "id": "custom_url",
        "label": "Свои HTTPS-адреса",
        "note": "Обе ссылки проверяются как связанная пара.",
        "geoip_url": "",
        "geosite_url": "",
    },
    {
        "id": "upload",
        "label": "Загрузить два файла",
        "note": "geoip.dat и geosite.dat выбираются одновременно.",
        "geoip_url": "",
        "geosite_url": "",
    },
    {
        "id": "local",
        "label": "Локальные пути сервера",
        "note": "Копирование и проверка существующей пары.",
        "geoip_url": "",
        "geosite_url": "",
    },
)


class GeoFilesError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeoFileReport:
    kind: str
    path: str
    size_bytes: int
    sha256: str
    categories: tuple[str, ...]
    valid: bool
    message: str


@dataclass(frozen=True)
class GeoPairReport:
    source_id: str
    source_label: str
    checked_at: str
    valid: bool
    message: str
    geoip: GeoFileReport
    geosite: GeoFileReport
    family: str = "custom"
    missing_active_categories: tuple[str, ...] = ()
    routing_blockers: tuple[str, ...] = ()
    compatibility_mode: str = "preserve-active-routing"
    managed_by: str = "sg-gateway"
    preset: str = ""
    policy_source: str = ""
    routing_user_rule_count: int = 0
    routing_system_rule_count: int = 0
    ready: bool = False
    xray_validation: str = "not-run"
    xray_message: str = "Проверка Xray ещё не выполнялась"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _state_root() -> Path:
    override = os.getenv("SG_GATEWAY_GEOFILES_STATE_DIR", "").strip()
    return Path(override) if override else load_config().data_dir / "geofiles"


def _asset_dir() -> Path:
    return Path(os.getenv("SG_GATEWAY_XRAY_ASSET_DIR", "/usr/local/share/xray"))


def _candidate_dir() -> Path:
    return _state_root() / "candidate"


def _backups_dir() -> Path:
    return _state_root() / "backups"


def _active_manifest_path() -> Path:
    return _state_root() / "active-manifest.json"


def _candidate_manifest_path() -> Path:
    return _candidate_dir() / "manifest.json"


def _candidate_routing_path() -> Path:
    return _candidate_dir() / "routing.json"


def _candidate_request_path() -> Path:
    return _candidate_dir() / "request.json"


def _form_state_path() -> Path:
    return _state_root() / "form-state.json"


def _ensure_state_dirs() -> None:
    for path in (_state_root(), _candidate_dir(), _backups_dir()):
        path.mkdir(parents=True, exist_ok=True)


def _source(source_id: str) -> dict:
    for item in SOURCE_PRESETS:
        if item["id"] == source_id:
            return dict(item)
    raise GeoFilesError("Неизвестный источник GeoFiles")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise GeoFilesError("Повреждённый protobuf varint")


def _iter_fields(data: bytes) -> Iterable[tuple[int, int, bytes | int]]:
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        field = key >> 3
        wire = key & 0x07
        if field <= 0:
            raise GeoFilesError("Некорректный номер protobuf-поля")
        if wire == 0:
            value, offset = _read_varint(data, offset)
            yield field, wire, value
        elif wire == 1:
            end = offset + 8
            if end > len(data):
                raise GeoFilesError("Обрезанное protobuf fixed64")
            yield field, wire, data[offset:end]
            offset = end
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise GeoFilesError("Обрезанное protobuf length-delimited поле")
            yield field, wire, data[offset:end]
            offset = end
        elif wire == 5:
            end = offset + 4
            if end > len(data):
                raise GeoFilesError("Обрезанное protobuf fixed32")
            yield field, wire, data[offset:end]
            offset = end
        else:
            raise GeoFilesError(f"Неподдерживаемый protobuf wire type: {wire}")


def _decode_category(payload: bytes) -> str | None:
    try:
        value = payload.decode("utf-8").strip().lower()
    except UnicodeDecodeError:
        return None
    return value if CATEGORY_RE.fullmatch(value) else None


def extract_categories(path: Path) -> tuple[str, ...]:
    data = path.read_bytes()
    categories: set[str] = set()
    for _outer_field, wire, payload in _iter_fields(data):
        if wire != 2 or not isinstance(payload, bytes):
            continue
        try:
            for inner_field, inner_wire, inner_payload in _iter_fields(payload):
                if inner_field == 1 and inner_wire == 2 and isinstance(inner_payload, bytes):
                    category = _decode_category(inner_payload)
                    if category:
                        categories.add(category)
                        break
        except GeoFilesError:
            continue
    return tuple(sorted(categories))


def _validate_file(path: Path, kind: str) -> GeoFileReport:
    minimum = MIN_GEOIP_SIZE if kind == "geoip" else MIN_GEOSITE_SIZE
    if not path.is_file():
        return GeoFileReport(kind, str(path), 0, "", (), False, "Файл не найден")
    size = path.stat().st_size
    digest = _sha256(path)
    if size < minimum:
        return GeoFileReport(
            kind, str(path), size, digest, (), False, f"Файл слишком мал: {size} байт"
        )
    try:
        categories = extract_categories(path)
    except (OSError, GeoFilesError) as exc:
        return GeoFileReport(
            kind, str(path), size, digest, (), False, f"Ошибка protobuf: {exc}"
        )
    if not categories:
        return GeoFileReport(
            kind,
            str(path),
            size,
            digest,
            (),
            False,
            "В protobuf не найдены реальные категории",
        )
    return GeoFileReport(
        kind,
        str(path),
        size,
        digest,
        categories,
        True,
        f"Структура корректна, категорий: {len(categories)}",
    )


def _detect_family(geoip_categories: tuple[str, ...], geosite_categories: tuple[str, ...]) -> str:
    ip = set(geoip_categories)
    site = set(geosite_categories)
    if ip.issuperset({"direct", "private", "whitelist"}) and site.issuperset(
        {"category-ru", "category-ads", "private", "whitelist"}
    ):
        return "roscomvpn"
    if "private" in ip and ("ru" in ip or "cn" in ip) and "category-ads-all" in site:
        return "standard"
    return "custom"


def _missing_active_categories(
    geoip_categories: tuple[str, ...],
    geosite_categories: tuple[str, ...],
) -> tuple[str, ...]:
    active_ip, active_site = active_geo_references()
    available_ip = set(geoip_categories)
    available_site = set(geosite_categories)
    values = [f"geoip:{item}" for item in sorted(active_ip - available_ip)]
    values.extend(f"geosite:{item}" for item in sorted(active_site - available_site))
    return tuple(values)


def validate_pair(
    geoip_path: Path,
    geosite_path: Path,
    source_id: str = "unknown",
    source_label: str = "Неизвестный источник",
) -> GeoPairReport:
    geoip = _validate_file(geoip_path, "geoip")
    geosite = _validate_file(geosite_path, "geosite")
    valid = geoip.valid and geosite.valid
    family = _detect_family(geoip.categories, geosite.categories) if valid else "unknown"
    missing = _missing_active_categories(geoip.categories, geosite.categories) if valid else ()
    return GeoPairReport(
        source_id=source_id,
        source_label=source_label,
        checked_at=_utc_now(),
        valid=valid,
        message=(
            "Связанная пара структурно корректна"
            if valid
            else "Связанная пара не прошла структурную проверку"
        ),
        geoip=geoip,
        geosite=geosite,
        family=family,
        missing_active_categories=missing,
        ready=valid and not missing,
    )


def _safe_url(url: str) -> str:
    value = (url or "").strip()
    if not value.startswith("https://"):
        raise GeoFilesError("Разрешены только HTTPS-адреса")
    if len(value) > 2048:
        raise GeoFilesError("Слишком длинный URL")
    return value


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        _safe_url(url),
        headers={"User-Agent": "SG-Gateway-GeoFiles/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_DOWNLOAD_SIZE:
                raise GeoFilesError("Удалённый файл превышает допустимый размер")
            total = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_SIZE:
                        raise GeoFilesError("Удалённый файл превышает допустимый размер")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GeoFilesError(f"Не удалось скачать {url}: {exc}") from exc


def _copy_stream(stream: BinaryIO, destination: Path) -> None:
    total = 0
    with destination.open("wb") as output:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_SIZE:
                raise GeoFilesError("Загруженный файл превышает допустимый размер")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())


def _copy_local(source: str, destination: Path) -> None:
    path = Path((source or "").strip())
    if not path.is_absolute():
        raise GeoFilesError("Локальный путь должен быть абсолютным")
    if not path.is_file():
        raise GeoFilesError(f"Локальный файл не найден: {path}")
    if path.stat().st_size > MAX_DOWNLOAD_SIZE:
        raise GeoFilesError("Локальный файл превышает допустимый размер")
    shutil.copy2(path, destination)


def _bundled_pair() -> tuple[Path, Path]:
    base = Path(__file__).resolve().parents[2] / "assets" / "geofiles"
    return base / "geoip.dat", base / "geosite.dat"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    # These files contain only GeoFiles metadata/state, never WARP or TLS
    # secrets.  Make the mode explicit because sg-hostd writes the validated
    # candidate as root while the panel must be able to read it after the
    # POST/redirect cycle.
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def _load_json_dict(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
SMART_BLOCKED_CATEGORIES = (
    "russia-blocked",
    "ru-blocked",
    "category-ru-blocked",
    "antifilter",
    "refilter",
    "blocked",
)
SMART_ADS_CATEGORIES = ("category-ads-all", "category-ads", "ads", "adguard")


def _routing_active_state_path() -> Path:
    return load_config().data_dir / "routing" / "active-managed.json"


def _active_family() -> str:
    report = _load_report(_active_manifest_path())
    return report.family if report else ""


def _routing_state() -> dict:
    return _load_json_dict(_routing_active_state_path())


def _category_blockers(
    title: str,
    domains: Iterable[str],
    ips: Iterable[str],
    *,
    geoip_categories: set[str],
    geosite_categories: set[str],
) -> list[str]:
    blockers: list[str] = []
    for value in domains:
        item = str(value).strip()
        lowered = item.lower()
        if lowered.startswith("geosite:"):
            category = lowered[8:]
            if category and category not in geosite_categories:
                blockers.append(f"{title} → geosite:{category}")
    for value in ips:
        item = str(value).strip()
        lowered = item.lower()
        if lowered.startswith("geoip:"):
            category = lowered[6:]
            if category and category not in geoip_categories:
                blockers.append(f"{title} → geoip:{category}")
    return blockers


def _rule(action: str, *, domains: Iterable[str] = (), ips: Iterable[str] = (), network: str = "") -> dict | None:
    domain_values = [str(item) for item in domains if str(item).strip()]
    ip_values = [str(item) for item in ips if str(item).strip()]
    item: dict = {"type": "field", "outboundTag": action}
    if domain_values:
        item["domain"] = domain_values
    if ip_values:
        item["ip"] = ip_values
    if network:
        item["network"] = network
    return item if domain_values or ip_values or network else None


def _user_rules_from_routing_state(
    state: dict,
    *,
    geoip_categories: set[str],
    geosite_categories: set[str],
) -> tuple[list[dict], list[str]]:
    """Return only user-owned Smart Routing rules, unchanged.

    The current SG-Gateway UI stores custom user rules explicitly in the Smart
    Routing state.  System-managed family rules must never be inferred from the
    old live fragment when that explicit policy exists.
    """
    smart = state.get("smart") if isinstance(state, dict) else None
    if not isinstance(smart, dict):
        return [], []
    groups = (
        ("Пользовательские правила Block", "block", "custom_block_domains", "custom_block_ips"),
        ("Пользовательские правила Direct", "direct", "custom_direct_domains", "custom_direct_ips"),
        ("Пользовательские правила WARP", "warp", "custom_warp_domains", "custom_warp_ips"),
    )
    rules: list[dict] = []
    blockers: list[str] = []
    for title, action, domain_key, ip_key in groups:
        domains = list(smart.get(domain_key) or [])
        ips = list(smart.get(ip_key) or [])
        if not domains and not ips:
            continue
        blockers.extend(
            _category_blockers(
                title,
                domains,
                ips,
                geoip_categories=geoip_categories,
                geosite_categories=geosite_categories,
            )
        )
        built = _rule(action, domains=domains, ips=ips)
        if built:
            rules.append(built)
    return rules, blockers


def _choose_category(options: Iterable[str], available: set[str]) -> str | None:
    return next((item for item in options if item in available), None)


def _smart_system_rules(
    smart: dict,
    *,
    geoip_categories: set[str],
    geosite_categories: set[str],
) -> tuple[list[dict], list[str], str]:
    rules: list[dict] = []
    blockers: list[str] = []
    preset = str(smart.get("preset") or "custom").strip().lower() or "custom"

    local_domains = ["geosite:private"] if "private" in geosite_categories else []
    local_ips = ["geoip:private"] if "private" in geoip_categories else list(SMART_PRIVATE_IPS)
    local = _rule("direct", domains=local_domains, ips=local_ips)
    if local:
        rules.append(local)

    scope = str(smart.get("russia_scope") or "none").strip().lower()
    russia_action = str(smart.get("russia_action") or "direct").strip().lower()
    if russia_action not in {"direct", "warp", "block"}:
        russia_action = "direct"
    if scope == "tld":
        if "tld-ru" in geosite_categories:
            rules.append(_rule(russia_action, domains=["geosite:tld-ru"]))
        else:
            blockers.append("Российская маршрутизация → geosite:tld-ru")
    elif scope == "sites_ip":
        missing: list[str] = []
        domains: list[str] = []
        ips: list[str] = []
        if "category-ru" in geosite_categories:
            domains.append("geosite:category-ru")
        else:
            missing.append("geosite:category-ru")
        if "ru" in geoip_categories:
            ips.append("geoip:ru")
        else:
            missing.append("geoip:ru")
        if missing:
            blockers.extend(f"Российская маршрутизация → {item}" for item in missing)
        else:
            rules.append(_rule(russia_action, domains=domains, ips=ips))

    blocked_action = str(smart.get("blocked_action") or "direct").strip().lower()
    if blocked_action in {"warp", "block"}:
        category = _choose_category(SMART_BLOCKED_CATEGORIES, geosite_categories)
        if category:
            rules.append(_rule(blocked_action, domains=[f"geosite:{category}"]))
        else:
            blockers.append("Заблокированные ресурсы → geosite:ru-blocked")

    ads_action = str(smart.get("ads_action") or "direct").strip().lower()
    if ads_action in {"warp", "block"}:
        category = _choose_category(SMART_ADS_CATEGORIES, geosite_categories)
        if category:
            rules.append(_rule(ads_action, domains=[f"geosite:{category}"]))
        else:
            blockers.append("Реклама и трекеры → geosite:category-ads")

    default_action = str(smart.get("default_action") or "direct").strip().lower()
    if default_action == "warp":
        rules.append(_rule("warp", network="tcp,udp"))
    return [item for item in rules if item], blockers, preset


def _template_system_rules(
    template_id: str,
    *,
    geoip_categories: set[str],
    geosite_categories: set[str],
) -> tuple[list[dict], list[str]]:
    rules: list[dict] = []
    blockers: list[str] = []
    if template_id == "private-direct":
        domains = ["geosite:private"] if "private" in geosite_categories else []
        ips = ["geoip:private"] if "private" in geoip_categories else list(SMART_PRIVATE_IPS)
        built = _rule("direct", domains=domains, ips=ips)
        if built:
            rules.append(built)
    elif template_id == "ru-tld-direct":
        if "tld-ru" in geosite_categories:
            rules.append(_rule("direct", domains=["geosite:tld-ru"]))
        else:
            blockers.append("Российские доменные зоны → geosite:tld-ru")
    elif template_id == "ru-sites-ip-direct":
        missing = []
        if "category-ru" not in geosite_categories:
            missing.append("geosite:category-ru")
        if "ru" not in geoip_categories:
            missing.append("geoip:ru")
        if missing:
            blockers.extend(f"Российские сайты и IP → {item}" for item in missing)
        else:
            rules.append(_rule("direct", domains=["geosite:category-ru"], ips=["geoip:ru"]))
    elif template_id == "ads-block":
        category = _choose_category(SMART_ADS_CATEGORIES, geosite_categories)
        if category:
            rules.append(_rule("block", domains=[f"geosite:{category}"]))
        else:
            blockers.append("Реклама и трекеры → geosite:category-ads")
    return [item for item in rules if item], blockers


def _plan_routing_for_candidate(
    report: GeoPairReport,
    *,
    block_ads: bool,
    block_windows_telemetry: bool,
    block_torrent: bool,
) -> tuple[dict, dict]:
    """Build future managed Routing from policy + the candidate family.

    User-owned Smart Routing entries are copied byte-for-byte at the value
    level.  System-managed rules are rebuilt for the candidate family instead
    of reusing a fragment created for another GeoFiles family.
    """
    geoip = {str(item).lower() for item in report.geoip.categories}
    geosite = {str(item).lower() for item in report.geosite.categories}
    state = _routing_state()
    previous_family = _active_family()
    user_rules, user_blockers = _user_rules_from_routing_state(
        state,
        geoip_categories=geoip,
        geosite_categories=geosite,
    )
    system_rules: list[dict] = []
    system_blockers: list[str] = []
    preset = ""
    policy_source = "family-default"

    if report.family == "roscomvpn":
        fragment = build_roscom_direct_block_fragment(
            geosite_categories=report.geosite.categories,
            geoip_categories=report.geoip.categories,
            block_ads=block_ads,
            block_windows_telemetry=block_windows_telemetry,
            block_torrent=block_torrent,
        )
        system_rules = list(fragment.get("routing", {}).get("rules", []))
        preset = "roscomvpn-direct-block"
        policy_source = "roscomvpn-family"
    else:
        smart = state.get("smart") if isinstance(state, dict) else None
        template_id = str(state.get("template_id") or "") if isinstance(state, dict) else ""
        if isinstance(smart, dict):
            system_rules, system_blockers, preset = _smart_system_rules(
                smart,
                geoip_categories=geoip,
                geosite_categories=geosite,
            )
            policy_source = "routing-smart"
        elif template_id in {"private-direct", "ru-tld-direct", "ru-sites-ip-direct", "ads-block"}:
            system_rules, system_blockers = _template_system_rules(
                template_id,
                geoip_categories=geoip,
                geosite_categories=geosite,
            )
            preset = template_id
            policy_source = "routing-template"
        elif previous_family and previous_family != report.family:
            # Legacy state has no owner/provenance.  On a family transition the
            # safe system default is an empty managed fragment (implicit Direct),
            # never the old family's generated geo rules.
            system_rules = []
            preset = "family-default-direct"
            policy_source = "legacy-family-transition"
        else:
            # Same-family/unknown legacy state: preserve it, but still validate
            # every geo reference before Apply.  This is backward compatible
            # without allowing a known family transition to leak stale rules.
            legacy = load_managed_fragment()
            legacy_missing = list(report.missing_active_categories)
            system_rules = list(legacy.get("routing", {}).get("rules", []))
            system_blockers.extend(f"Legacy managed Routing → {item}" for item in legacy_missing)
            preset = "legacy-preserve"
            policy_source = "legacy-same-family"

    blockers = user_blockers + system_blockers
    combined = {
        "routing": {
            "domainStrategy": "IPIfNonMatch" if (user_rules or system_rules) else "AsIs",
            # User-owned rules must stay first so a family baseline cannot
            # shadow a more specific user decision.
            "rules": user_rules + system_rules,
        }
    }
    try:
        from app.routing.runtime import sanitize_managed_fragment
        combined = sanitize_managed_fragment(combined)
    except RoutingRuntimeError as exc:
        raise GeoFilesError(str(exc)) from exc
    plan = {
        "managed_by": "sg-gateway",
        "family": report.family,
        "preset": preset,
        "policy_source": policy_source,
        "previous_family": previous_family,
        "user_rule_count": len(user_rules),
        "system_rule_count": len(system_rules),
        "blockers": blockers,
    }
    return combined, plan


def _report_payload(report: GeoPairReport) -> dict:
    payload = asdict(report)
    payload["geoip"]["categories"] = list(report.geoip.categories)
    payload["geosite"]["categories"] = list(report.geosite.categories)
    payload["missing_active_categories"] = list(report.missing_active_categories)
    payload["routing_blockers"] = list(report.routing_blockers)
    return payload


def _pair_from_payload(payload: dict) -> GeoPairReport:
    return GeoPairReport(
        source_id=str(payload.get("source_id", "unknown")),
        source_label=str(payload.get("source_label", "Неизвестный источник")),
        checked_at=str(payload.get("checked_at", "")),
        valid=bool(payload.get("valid", False)),
        message=str(payload.get("message", "")),
        geoip=GeoFileReport(
            kind="geoip",
            path=str(payload.get("geoip", {}).get("path", "")),
            size_bytes=int(payload.get("geoip", {}).get("size_bytes", 0)),
            sha256=str(payload.get("geoip", {}).get("sha256", "")),
            categories=tuple(payload.get("geoip", {}).get("categories", [])),
            valid=bool(payload.get("geoip", {}).get("valid", False)),
            message=str(payload.get("geoip", {}).get("message", "")),
        ),
        geosite=GeoFileReport(
            kind="geosite",
            path=str(payload.get("geosite", {}).get("path", "")),
            size_bytes=int(payload.get("geosite", {}).get("size_bytes", 0)),
            sha256=str(payload.get("geosite", {}).get("sha256", "")),
            categories=tuple(payload.get("geosite", {}).get("categories", [])),
            valid=bool(payload.get("geosite", {}).get("valid", False)),
            message=str(payload.get("geosite", {}).get("message", "")),
        ),
        family=str(payload.get("family", "custom")),
        missing_active_categories=tuple(payload.get("missing_active_categories", [])),
        routing_blockers=tuple(payload.get("routing_blockers", [])),
        compatibility_mode=str(payload.get("compatibility_mode", "preserve-active-routing")),
        managed_by=str(payload.get("managed_by", "sg-gateway")),
        preset=str(payload.get("preset", "")),
        policy_source=str(payload.get("policy_source", "")),
        routing_user_rule_count=int(payload.get("routing_user_rule_count", 0)),
        routing_system_rule_count=int(payload.get("routing_system_rule_count", 0)),
        ready=bool(payload.get("ready", payload.get("valid", False))),
        xray_validation=str(payload.get("xray_validation", "not-run")),
        xray_message=str(payload.get("xray_message", "")),
    )


def _load_report(path: Path) -> GeoPairReport | None:
    try:
        return _pair_from_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def _atomic_candidate(source_dir: Path, report: GeoPairReport) -> None:
    root = _state_root()
    final = _candidate_dir()
    old = root / f"candidate-old-{uuid.uuid4().hex}"
    if final.exists():
        final.replace(old)
    try:
        source_dir.replace(final)
    except Exception:
        if old.exists() and not final.exists():
            old.replace(final)
        raise
    shutil.rmtree(old, ignore_errors=True)
    _write_json(_candidate_manifest_path(), _report_payload(report))


def stage_pair(
    source_id: str,
    *,
    geoip_url: str = "",
    geosite_url: str = "",
    geoip_upload: BinaryIO | None = None,
    geosite_upload: BinaryIO | None = None,
    geoip_upload_name: str = "",
    geosite_upload_name: str = "",
    local_geoip: str = "",
    local_geosite: str = "",
    block_ads: bool = False,
    block_windows_telemetry: bool = False,
    block_torrent: bool = False,
) -> GeoPairReport:
    _ensure_state_dirs()
    source = _source(source_id)
    request_state = {
        "source_id": source_id,
        "source_label": source["label"],
        "submitted_at": _utc_now(),
        "geoip_url": (geoip_url or "").strip() if source_id == "custom_url" else "",
        "geosite_url": (geosite_url or "").strip() if source_id == "custom_url" else "",
        "local_geoip": (local_geoip or "").strip() if source_id == "local" else "",
        "local_geosite": (local_geosite or "").strip() if source_id == "local" else "",
        "geoip_upload_name": (geoip_upload_name or "").strip() if source_id == "upload" else "",
        "geosite_upload_name": (geosite_upload_name or "").strip() if source_id == "upload" else "",
        "roscom_block_ads": bool(block_ads) if source_id == "roscomvpn" else False,
        "roscom_block_windows": bool(block_windows_telemetry) if source_id == "roscomvpn" else False,
        "roscom_block_torrent": bool(block_torrent) if source_id == "roscomvpn" else False,
    }
    # Preserve the submitted form across POST/redirect, even when validation
    # fails, so the operator can correct it instead of re-entering everything.
    _write_json(_form_state_path(), request_state)

    # A new check invalidates the previous frozen candidate immediately.
    # This prevents a failed check of source B from leaving source A enabled
    # for Apply by accident.
    candidate = _candidate_dir()
    if candidate.exists():
        shutil.rmtree(candidate)
    candidate.mkdir(parents=True, exist_ok=True)

    incoming = _state_root() / f"incoming-{uuid.uuid4().hex}"
    incoming.mkdir(parents=True, exist_ok=False)
    geoip = incoming / "geoip.dat"
    geosite = incoming / "geosite.dat"
    try:
        if source_id in {"loyalsoldier", "runetfreedom", "roscomvpn"}:
            _download(source["geoip_url"], geoip)
            _download(source["geosite_url"], geosite)
        elif source_id == "custom_url":
            _download(geoip_url, geoip)
            _download(geosite_url, geosite)
        elif source_id == "upload":
            if geoip_upload is None or geosite_upload is None:
                raise GeoFilesError("Выберите оба файла: geoip.dat и geosite.dat")
            _copy_stream(geoip_upload, geoip)
            _copy_stream(geosite_upload, geosite)
        elif source_id == "local":
            _copy_local(local_geoip, geoip)
            _copy_local(local_geosite, geosite)
        elif source_id == "sg_client":
            bundled_geoip, bundled_geosite = _bundled_pair()
            if not bundled_geoip.is_file() or not bundled_geosite.is_file():
                raise GeoFilesError(
                    "Встроенная пара SG Client ещё не добавлена в assets/geofiles"
                )
            shutil.copy2(bundled_geoip, geoip)
            shutil.copy2(bundled_geosite, geosite)
        else:
            raise GeoFilesError("Источник GeoFiles не поддерживается")

        report = validate_pair(geoip, geosite, source_id, source["label"])
        if not report.valid:
            raise GeoFilesError(report.message)

        try:
            routing_fragment, routing_plan = _plan_routing_for_candidate(
                report,
                block_ads=block_ads,
                block_windows_telemetry=block_windows_telemetry,
                block_torrent=block_torrent,
            )
        except RoutingRuntimeError as exc:
            raise GeoFilesError(str(exc)) from exc
        blockers = tuple(str(item) for item in routing_plan.get("blockers", []))
        compatibility_mode = (
            "roscomvpn-direct-block"
            if report.family == "roscomvpn"
            else "family-aware-managed-routing"
        )
        ready = not blockers
        if ready:
            message = (
                f"Candidate Routing перестроен для family={report.family}; "
                "пользовательские правила сохранены."
            )
        else:
            message = "Применение заблокировано правилами: " + "; ".join(blockers)

        # Structural/category preparation is intentionally done by the panel,
        # but the full Xray candidate MUST be validated by sg-hostd as root.
        # An enabled WARP outbound contains root-only WireGuard credentials in
        # /var/lib/sg-gateway/warp/wgcf.xray.json; the unprivileged web process
        # must never read that file just to check GeoFiles.
        report = replace(
            report,
            ready=ready,
            message=message,
            routing_blockers=blockers,
            compatibility_mode=compatibility_mode,
            managed_by=str(routing_plan.get("managed_by", "sg-gateway")),
            preset=str(routing_plan.get("preset", "")),
            policy_source=str(routing_plan.get("policy_source", "")),
            routing_user_rule_count=int(routing_plan.get("user_rule_count", 0)),
            routing_system_rule_count=int(routing_plan.get("system_rule_count", 0)),
            xray_validation="pending",
            xray_message="Полная проверка Xray выполняется через sg-hostd",
        )
        request_state["checked_at"] = report.checked_at
        request_state["geoip_sha256"] = report.geoip.sha256
        request_state["geosite_sha256"] = report.geosite.sha256
        atomic_write_json(incoming / "routing.json", routing_fragment, 0o600)
        _write_json(incoming / "manifest.json", _report_payload(report))
        _write_json(incoming / "request.json", request_state)
        _atomic_candidate(incoming, report)

        if _find_xray() is None:
            report = replace(
                report,
                xray_validation="warning",
                xray_message="Xray не установлен: выполнена только структурная проверка",
            )
            _write_json(_candidate_manifest_path(), _report_payload(report))
        else:
            _run_helper("check")
            report = _load_report(_candidate_manifest_path()) or report
        log_operation(
            "geofiles.check",
            f"geofiles:{source_id}",
            (
                f"Пара проверена: family={report.family}, "
                f"geoip {len(report.geoip.categories)} категорий, "
                f"geosite {len(report.geosite.categories)} категорий, "
                f"ready={report.ready}"
            ),
        )
        return _load_report(_candidate_manifest_path()) or report
    except Exception as exc:
        shutil.rmtree(incoming, ignore_errors=True)
        message = str(exc)
        log_operation(
            "geofiles.check",
            f"geofiles:{source_id}",
            message,
            status="error",
        )
        if isinstance(exc, GeoFilesError):
            raise
        raise GeoFilesError(message) from exc


def _helper_path() -> Path:
    return Path(
        os.getenv(
            "SG_GATEWAY_GEOFILES_HELPER",
            "/usr/local/lib/sg-gateway/geofiles-helper",
        )
    )


def _run_helper(action: str) -> dict:
    command = f"geofiles.{action}"
    result = run_hostd_command(command, timeout=240)
    if result.status != "ok":
        raise GeoFilesError(result.message or f"{command} failed")

    payload = dict(result.payload)
    payload.setdefault("ok", True)
    payload.setdefault("message", result.message)
    return payload

def apply_candidate() -> dict:
    candidate = _candidate_dir()
    structural = validate_pair(
        candidate / "geoip.dat",
        candidate / "geosite.dat",
        source_id="candidate",
        source_label="Проверенный candidate",
    )
    report = _load_report(_candidate_manifest_path())
    if not structural.valid or report is None or not report.ready:
        detail = ", ".join(report.missing_active_categories) if report else ""
        raise GeoFilesError(
            "Сначала подготовьте совместимый candidate GeoFiles"
            + (f": {detail}" if detail else "")
        )
    payload = _run_helper("apply")
    log_operation(
        "geofiles.apply",
        "geofiles:active",
        str(payload.get("message", "GeoFiles применены")),
    )
    return payload


def rollback_latest() -> dict:
    payload = _run_helper("rollback")
    log_operation(
        "geofiles.rollback",
        "geofiles:active",
        str(payload.get("message", "GeoFiles восстановлены")),
    )
    return payload


def _format_bytes(value: int) -> str:
    size = float(max(0, int(value)))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def _report_view(report: GeoPairReport | None) -> dict | None:
    if report is None:
        return None
    payload = _report_payload(report)
    for key in ("geoip", "geosite"):
        payload[key]["size_text"] = _format_bytes(payload[key]["size_bytes"])
        payload[key]["categories_preview"] = payload[key]["categories"][:24]
    return payload


@lru_cache(maxsize=12)
def _validate_pair_cached(
    geoip_path: str,
    geosite_path: str,
    source_id: str,
    source_label: str,
    geoip_size: int,
    geoip_mtime_ns: int,
    geosite_size: int,
    geosite_mtime_ns: int,
) -> GeoPairReport:
    # Size and mtime are deliberate cache-key fields. A replaced pair is
    # re-read automatically, while repeated page renders reuse the parsed
    # protobuf category lists instead of loading ~90 MiB every time.
    return validate_pair(
        Path(geoip_path),
        Path(geosite_path),
        source_id=source_id,
        source_label=source_label,
    )


def _active_report() -> GeoPairReport | None:
    asset = _asset_dir()
    geoip_path = asset / "geoip.dat"
    geosite_path = asset / "geosite.dat"
    if not geoip_path.is_file() or not geosite_path.is_file():
        return None
    stored = _load_report(_active_manifest_path())
    geoip_stat = geoip_path.stat()
    geosite_stat = geosite_path.stat()
    checked = _validate_pair_cached(
        str(geoip_path),
        str(geosite_path),
        stored.source_id if stored else "active",
        stored.source_label if stored else "Активная пара",
        geoip_stat.st_size,
        geoip_stat.st_mtime_ns,
        geosite_stat.st_size,
        geosite_stat.st_mtime_ns,
    )
    if stored:
        checked = GeoPairReport(
            source_id=stored.source_id,
            source_label=stored.source_label,
            checked_at=stored.checked_at,
            valid=checked.valid,
            message=checked.message,
            geoip=checked.geoip,
            geosite=checked.geosite,
            family=stored.family,
            missing_active_categories=stored.missing_active_categories,
            routing_blockers=stored.routing_blockers,
            compatibility_mode=stored.compatibility_mode,
            managed_by=stored.managed_by,
            preset=stored.preset,
            policy_source=stored.policy_source,
            routing_user_rule_count=stored.routing_user_rule_count,
            routing_system_rule_count=stored.routing_system_rule_count,
            ready=stored.ready,
            xray_validation=stored.xray_validation,
            xray_message=stored.xray_message,
        )
    return checked


def _backup_views() -> list[dict]:
    items = []
    for directory in sorted(_backups_dir().glob("*"), reverse=True):
        if not directory.is_dir():
            continue
        manifest = _load_report(directory / "manifest.json")
        items.append(
            {
                "name": directory.name,
                "source_label": manifest.source_label if manifest else "Неизвестно",
                "valid": manifest.valid if manifest else False,
            }
        )
    return items[:10]


def overview() -> dict:
    _ensure_state_dirs()
    bundled_geoip, bundled_geosite = _bundled_pair()
    sources = []
    for source in SOURCE_PRESETS:
        item = dict(source)
        item["available"] = (
            bundled_geoip.is_file() and bundled_geosite.is_file()
            if item["id"] == "sg_client"
            else True
        )
        sources.append(item)
    return {
        "asset_dir": str(_asset_dir()),
        "state_dir": str(_state_root()),
        "sources": sources,
        "active": _report_view(_active_report()),
        "candidate": _report_view(_load_report(_candidate_manifest_path())),
        "candidate_request": _load_json_dict(_candidate_request_path()),
        "form_state": _load_json_dict(_form_state_path()),
        "backups": _backup_views(),
    }


def health_status() -> dict:
    active = _active_report()
    if active is None:
        return {
            "status": "warning",
            "message": f"Активная пара не найдена в {_asset_dir()}",
        }
    if not active.valid:
        return {
            "status": "error",
            "message": "Активная пара GeoFiles не прошла структурную проверку",
        }
    return {
        "status": "ok",
        "message": (
            f"geoip: {len(active.geoip.categories)} категорий; "
            f"geosite: {len(active.geosite.categories)} категорий"
        ),
    }


def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    return stream


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".tmp-{uuid.uuid4().hex}")
    with source.open("rb") as input_stream, temporary.open("wb") as output:
        shutil.copyfileobj(input_stream, output, length=1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, target)


def _find_xray() -> str | None:
    for candidate in (shutil.which("xray"), "/usr/local/bin/xray", "/usr/bin/xray"):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _xray_test(asset_dir: Path, report: GeoPairReport) -> tuple[str, str]:
    xray = _find_xray()
    if xray is None:
        return "warning", "Xray не установлен: выполнена только структурная проверка"
    config = {
        "log": {"loglevel": "none"},
        "inbounds": [],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "domain": [f"geosite:{report.geosite.categories[0]}"],
                    "outboundTag": "direct",
                },
                {
                    "type": "field",
                    "ip": [f"geoip:{report.geoip.categories[0]}"],
                    "outboundTag": "direct",
                },
            ]
        },
    }
    with tempfile.TemporaryDirectory(prefix="sg-gateway-geofiles-") as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment["XRAY_LOCATION_ASSET"] = str(asset_dir)
        messages = []
        for command in (
            [xray, "run", "-test", "-config", str(config_path)],
            [xray, "-test", "-config", str(config_path)],
        ):
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
                check=False,
            )
            if result.returncode == 0:
                return "ok", "Xray принял реальную категорию из каждого файла"
            messages.append((result.stderr or result.stdout).strip())
    return "error", "; ".join(item for item in messages if item) or "Xray test failed"


def _restart_xray_if_present() -> tuple[str, str]:
    if shutil.which("systemctl") is None:
        return "warning", "systemctl недоступен"
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray.service"],
        check=False,
    )
    if active.returncode != 0:
        return "warning", "xray.service не активен; перезапуск не выполнялся"
    restart = subprocess.run(
        ["systemctl", "restart", "xray.service"],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if restart.returncode != 0:
        return "error", (restart.stderr or restart.stdout).strip() or "restart failed"
    verify = subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray.service"],
        check=False,
    )
    if verify.returncode != 0:
        return "error", "xray.service не активен после перезапуска"
    return "ok", "xray.service перезапущен и активен"


def _path_size(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _ensure_apply_free_space(candidate: Path, asset: Path) -> None:
    candidate_bytes = _path_size(candidate / "geoip.dat") + _path_size(candidate / "geosite.dat")
    active_bytes = _path_size(asset / "geoip.dat") + _path_size(asset / "geosite.dat")
    metadata_bytes = _path_size(managed_routing_path()) + _path_size(xray_config_path()) + _path_size(_active_manifest_path())
    backup_required = active_bytes + metadata_bytes + GEOFILES_DISK_RESERVE
    asset_required = candidate_bytes + GEOFILES_DISK_RESERVE

    state_parent = _state_root()
    state_parent.mkdir(parents=True, exist_ok=True)
    asset.mkdir(parents=True, exist_ok=True)
    state_free = shutil.disk_usage(state_parent).free
    asset_free = shutil.disk_usage(asset).free
    if state_free < backup_required:
        raise GeoFilesError(
            f"Недостаточно места для полного GeoFiles backup: требуется около {backup_required // (1024 * 1024)} MiB, "
            f"доступно {state_free // (1024 * 1024)} MiB"
        )
    if asset_free < asset_required:
        raise GeoFilesError(
            f"Недостаточно места для атомарного переключения GeoFiles: требуется около {asset_required // (1024 * 1024)} MiB, "
            f"доступно {asset_free // (1024 * 1024)} MiB"
        )


def _verify_backup(backup: Path, asset_dir: Path) -> None:
    try:
        state = json.loads((backup / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise GeoFilesError(f"Backup GeoFiles не содержит корректный state.json: {exc}") from exc
    checks = (
        ("geoip.dat", "geoip_present", asset_dir / "geoip.dat"),
        ("geosite.dat", "geosite_present", asset_dir / "geosite.dat"),
        ("routing.json", "routing_present", managed_routing_path()),
        ("config.json", "config_present", xray_config_path()),
    )
    for name, flag, source in checks:
        if not state.get(flag):
            continue
        target = backup / name
        if not source.is_file() or not target.is_file():
            raise GeoFilesError(f"Backup GeoFiles неполон: {name}")
        if _sha256(source) != _sha256(target):
            raise GeoFilesError(f"Backup GeoFiles не прошёл SHA-256: {name}")
    if state.get("manifest_present") and not (backup / "manifest.json").is_file():
        raise GeoFilesError("Backup GeoFiles неполон: manifest.json")


def _stop_xray_for_switch() -> None:
    result = subprocess.run(
        ["systemctl", "stop", "xray.service"],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if result.returncode != 0:
        raise GeoFilesError((result.stderr or result.stdout).strip() or "Не удалось остановить xray.service перед переключением GeoFiles")


def _start_xray_after_switch() -> tuple[str, str]:
    result = subprocess.run(
        ["systemctl", "start", "xray.service"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return "error", (result.stderr or result.stdout).strip() or "xray.service не запустился"
    verify = subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray.service"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if verify.returncode != 0:
        return "error", "xray.service не активен после переключения GeoFiles"
    return "ok", "xray.service запущен с новым GeoFiles-набором"


def _backup_active(asset_dir: Path) -> Path:
    backup = _backups_dir() / _timestamp()
    backup.mkdir(parents=True, exist_ok=False)
    state = {
        "geoip_present": (asset_dir / "geoip.dat").is_file(),
        "geosite_present": (asset_dir / "geosite.dat").is_file(),
        "manifest_present": _active_manifest_path().is_file(),
        "routing_present": managed_routing_path().is_file(),
        "config_present": xray_config_path().is_file(),
    }
    for name in ("geoip.dat", "geosite.dat"):
        source = asset_dir / name
        if source.is_file():
            shutil.copy2(source, backup / name)
    if _active_manifest_path().is_file():
        shutil.copy2(_active_manifest_path(), backup / "manifest.json")
    elif state["geoip_present"] and state["geosite_present"]:
        existing = validate_pair(
            asset_dir / "geoip.dat",
            asset_dir / "geosite.dat",
            "previous",
            "Предыдущая активная пара",
        )
        _write_json(backup / "manifest.json", _report_payload(existing))
    if managed_routing_path().is_file():
        shutil.copy2(managed_routing_path(), backup / "routing.json")
    if xray_config_path().is_file():
        shutil.copy2(xray_config_path(), backup / "config.json")
    _write_json(backup / "state.json", state)
    _verify_backup(backup, asset_dir)
    return backup


def _restore_backup(backup: Path, asset: Path) -> None:
    try:
        state = json.loads((backup / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        state = {
            "geoip_present": (backup / "geoip.dat").is_file(),
            "geosite_present": (backup / "geosite.dat").is_file(),
            "manifest_present": (backup / "manifest.json").is_file(),
            "routing_present": (backup / "routing.json").is_file(),
            "config_present": (backup / "config.json").is_file(),
        }
    for name, flag in (("geoip.dat", "geoip_present"), ("geosite.dat", "geosite_present")):
        source = backup / name
        target = asset / name
        if state.get(flag) and source.is_file():
            _atomic_copy(source, target)
        else:
            target.unlink(missing_ok=True)
    if state.get("manifest_present") and (backup / "manifest.json").is_file():
        shutil.copy2(backup / "manifest.json", _active_manifest_path())
    else:
        _active_manifest_path().unlink(missing_ok=True)
    if state.get("routing_present") and (backup / "routing.json").is_file():
        atomic_write_json(
            managed_routing_path(),
            json.loads((backup / "routing.json").read_text(encoding="utf-8")),
            0o640,
        )
    else:
        managed_routing_path().unlink(missing_ok=True)
    if state.get("config_present") and (backup / "config.json").is_file():
        atomic_write_json(
            xray_config_path(),
            json.loads((backup / "config.json").read_text(encoding="utf-8")),
            0o600,
        )
    else:
        xray_config_path().unlink(missing_ok=True)


def _sync_compatibility_asset_path(asset: Path) -> None:
    compatibility = Path("/usr/share/xray")
    if compatibility == asset or not compatibility.exists():
        return
    compatibility.mkdir(parents=True, exist_ok=True)
    for name in ("geoip.dat", "geosite.dat"):
        source = asset / name
        if source.is_file():
            _atomic_copy(source, compatibility / name)


def root_validate_candidate() -> dict:
    """Validate the staged pair against the exact privileged Xray runtime.

    This runs only through sg-hostd.  In particular, WARP credentials remain
    root-only while the candidate still gets tested with the real WARP
    outbound and the real live Xray configuration.
    """
    _ensure_state_dirs()
    lock_stream = _lock(GEOFILES_LOCK_PATH)
    try:
        candidate = _candidate_dir()
        report = _load_report(_candidate_manifest_path())
        if report is None:
            raise GeoFilesError("Candidate GeoFiles не содержит manifest.json")

        structural = validate_pair(
            candidate / "geoip.dat",
            candidate / "geosite.dat",
            report.source_id,
            report.source_label,
        )
        if not structural.valid:
            report = replace(
                report,
                ready=False,
                message=structural.message,
                xray_validation="error",
                xray_message=structural.message,
            )
            _write_json(_candidate_manifest_path(), _report_payload(report))
            return {
                "ok": True,
                "message": structural.message,
                "ready": False,
                "xray_validation": "error",
            }

        try:
            routing_fragment = json.loads(
                _candidate_routing_path().read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GeoFilesError(f"Не найден Routing candidate GeoFiles: {exc}") from exc

        if report.routing_blockers:
            blocker_message = "Применение заблокировано правилами: " + "; ".join(report.routing_blockers)
            report = replace(
                report,
                ready=False,
                message=blocker_message,
                xray_validation="blocked",
                xray_message=blocker_message,
            )
            _write_json(_candidate_manifest_path(), _report_payload(report))
            return {
                "ok": True,
                "message": blocker_message,
                "ready": False,
                "xray_validation": "blocked",
                "xray_message": blocker_message,
            }

        try:
            full_candidate = build_full_config(routing_fragment)
            xray_status, xray_message = xray_test_config(
                full_candidate,
                asset_dir=candidate,
            )
        except Exception as exc:
            xray_status, xray_message = "error", str(exc)

        ready = bool(report.ready) and xray_status != "error"
        message = report.message if xray_status != "error" else xray_message
        report = replace(
            report,
            ready=ready,
            message=message,
            xray_validation=xray_status,
            xray_message=xray_message,
        )
        _write_json(_candidate_manifest_path(), _report_payload(report))
        return {
            "ok": True,
            "message": message,
            "ready": ready,
            "xray_validation": xray_status,
            "xray_message": xray_message,
        }
    finally:
        lock_stream.close()


def root_apply_candidate() -> dict:
    _ensure_state_dirs()
    lock_stream = _lock(GEOFILES_LOCK_PATH)
    try:
        candidate = _candidate_dir()
        manifest = _load_report(_candidate_manifest_path())
        structural = validate_pair(
            candidate / "geoip.dat",
            candidate / "geosite.dat",
            manifest.source_id if manifest else "candidate",
            manifest.source_label if manifest else "Проверенный candidate",
        )
        if not structural.valid or manifest is None or not manifest.ready:
            raise GeoFilesError("Candidate GeoFiles отсутствует, повреждён или несовместим")
        try:
            routing_fragment = json.loads(
                _candidate_routing_path().read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GeoFilesError(f"Не найден Routing candidate GeoFiles: {exc}") from exc

        full_candidate = build_full_config(routing_fragment)
        xray_status, xray_message = xray_test_config(
            full_candidate,
            asset_dir=candidate,
        )
        if xray_status == "error":
            raise GeoFilesError(xray_message)

        asset = _asset_dir()
        asset.mkdir(parents=True, exist_ok=True)
        _ensure_apply_free_space(candidate, asset)
        backup = _backup_active(asset)
        was_active = service_is_active()
        had_config = xray_config_path().is_file()
        stopped_for_switch = False
        try:
            if was_active:
                _stop_xray_for_switch()
                stopped_for_switch = True
            _atomic_copy(candidate / "geoip.dat", asset / "geoip.dat")
            _atomic_copy(candidate / "geosite.dat", asset / "geosite.dat")
            atomic_write_json(managed_routing_path(), routing_fragment, 0o640)
            if had_config:
                atomic_write_json(xray_config_path(), full_candidate, 0o600)
            _sync_compatibility_asset_path(asset)
            restart_message = "xray.service не был активен; файлы и Routing подготовлены"
            if was_active:
                restart_status, restart_message = _start_xray_after_switch()
                stopped_for_switch = False
                if restart_status == "error":
                    raise GeoFilesError(restart_message)

            active_report = GeoPairReport(
                source_id=manifest.source_id,
                source_label=manifest.source_label,
                checked_at=_utc_now(),
                valid=True,
                message="Активная пара и совместимая маршрутизация применены",
                geoip=_validate_file(asset / "geoip.dat", "geoip"),
                geosite=_validate_file(asset / "geosite.dat", "geosite"),
                family=manifest.family,
                missing_active_categories=(),
                routing_blockers=(),
                compatibility_mode=manifest.compatibility_mode,
                managed_by=manifest.managed_by,
                preset=manifest.preset,
                policy_source=manifest.policy_source,
                routing_user_rule_count=manifest.routing_user_rule_count,
                routing_system_rule_count=manifest.routing_system_rule_count,
                ready=True,
                xray_validation=xray_status,
                xray_message=f"{xray_message}; {restart_message}",
            )
            _write_json(_active_manifest_path(), _report_payload(active_report))
            return {
                "ok": True,
                "message": (
                    f"GeoFiles и Routing применены транзакционно. Backup: {backup.name}. "
                    f"{active_report.xray_message}"
                ),
                "backup": backup.name,
                "family": manifest.family,
                "compatibility_mode": manifest.compatibility_mode,
            }
        except Exception as exc:
            _restore_backup(backup, asset)
            _sync_compatibility_asset_path(asset)
            if was_active and xray_config_path().is_file():
                restore_status, restore_message = (
                    _start_xray_after_switch()
                    if stopped_for_switch or not service_is_active()
                    else restart_xray(required=False)
                )
                if restore_status == "error":
                    raise GeoFilesError(
                        f"{exc}; откат файлов выполнен, но старый Xray не запустился: "
                        f"{restore_message}"
                    ) from exc
            raise
    finally:
        lock_stream.close()


def root_rollback_latest() -> dict:
    _ensure_state_dirs()
    lock_stream = _lock(GEOFILES_LOCK_PATH)
    try:
        backups = [
            item for item in sorted(_backups_dir().glob("*"), reverse=True)
            if item.is_dir()
        ]
        if not backups:
            raise GeoFilesError("Нет резервной пары GeoFiles для отката")
        backup = backups[0]
        structural = validate_pair(
            backup / "geoip.dat",
            backup / "geosite.dat",
            "rollback",
            f"Backup {backup.name}",
        )
        if not structural.valid:
            raise GeoFilesError("Последний backup GeoFiles повреждён или неполон")
        try:
            backup_routing = json.loads((backup / "routing.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            backup_routing = load_managed_fragment()
        try:
            backup_config = json.loads((backup / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            backup_config = build_full_config(backup_routing)
        status, message = xray_test_config(backup_config, asset_dir=backup)
        if status == "error":
            raise GeoFilesError(message)

        asset = _asset_dir()
        _ensure_apply_free_space(backup, asset)
        current_backup = _backup_active(asset)
        was_active = service_is_active()
        stopped_for_switch = False
        try:
            if was_active:
                _stop_xray_for_switch()
                stopped_for_switch = True
            _restore_backup(backup, asset)
            _sync_compatibility_asset_path(asset)
            restart_message = "xray.service не был активен"
            if was_active and xray_config_path().is_file():
                restart_status, restart_message = _start_xray_after_switch()
                stopped_for_switch = False
                if restart_status == "error":
                    raise GeoFilesError(restart_message)
            return {
                "ok": True,
                "message": (
                    f"GeoFiles, Routing и config.json восстановлены из {backup.name}. "
                    f"Страховочная копия: {current_backup.name}. {restart_message}"
                ),
            }
        except Exception as exc:
            _restore_backup(current_backup, asset)
            _sync_compatibility_asset_path(asset)
            if was_active and xray_config_path().is_file():
                if stopped_for_switch or not service_is_active():
                    _start_xray_after_switch()
                else:
                    restart_xray(required=False)
            raise GeoFilesError(str(exc)) from exc
    finally:
        lock_stream.close()
