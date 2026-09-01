from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app.connections.geoip_country import lookup_country_code


DEFAULT_IP_INTELLIGENCE_CACHE = Path(
    "/var/lib/sg-gateway/infosec/ip-intelligence.json"
)
DEFAULT_REPUTATION_PATH = Path(
    "/var/lib/sg-gateway/infosec/reputation.json"
)
RIPESTAT_PREFIX_OVERVIEW = (
    "https://stat.ripe.net/data/prefix-overview/data.json"
)
_CACHE_VERSION = 1
_MAX_CACHE_BYTES = 2 * 1024 * 1024
_MAX_CACHE_ENTRIES = 4096
_MAX_PAGE_LOOKUPS = 12

_COUNTRY_NAMES = {
    "ad": "Андорра", "ae": "ОАЭ", "af": "Афганистан", "al": "Албания",
    "am": "Армения", "ar": "Аргентина", "at": "Австрия", "au": "Австралия",
    "az": "Азербайджан", "ba": "Босния и Герцеговина", "bd": "Бангладеш",
    "be": "Бельгия", "bg": "Болгария", "bh": "Бахрейн", "br": "Бразилия",
    "by": "Беларусь", "ca": "Канада", "ch": "Швейцария", "cl": "Чили",
    "cn": "Китай", "co": "Колумбия", "cz": "Чехия", "de": "Германия",
    "dk": "Дания", "ee": "Эстония", "eg": "Египет", "es": "Испания",
    "fi": "Финляндия", "fr": "Франция", "gb": "Великобритания", "ge": "Грузия",
    "gr": "Греция", "hk": "Гонконг", "hr": "Хорватия", "hu": "Венгрия",
    "id": "Индонезия", "ie": "Ирландия", "il": "Израиль", "in": "Индия",
    "ir": "Иран", "is": "Исландия", "it": "Италия", "jp": "Япония",
    "kg": "Кыргызстан", "kr": "Южная Корея", "kz": "Казахстан", "lt": "Литва",
    "lu": "Люксембург", "lv": "Латвия", "md": "Молдова", "me": "Черногория",
    "mk": "Северная Македония", "mn": "Монголия", "mx": "Мексика",
    "my": "Малайзия", "nl": "Нидерланды", "no": "Норвегия", "nz": "Новая Зеландия",
    "ph": "Филиппины", "pk": "Пакистан", "pl": "Польша", "pt": "Португалия",
    "ro": "Румыния", "rs": "Сербия", "ru": "Россия", "sa": "Саудовская Аравия",
    "se": "Швеция", "sg": "Сингапур", "si": "Словения", "sk": "Словакия",
    "th": "Таиланд", "tr": "Турция", "tw": "Тайвань", "ua": "Украина",
    "us": "США", "uz": "Узбекистан", "vn": "Вьетнам", "za": "ЮАР",
}

_SCOPE_LABELS = {
    "ssh": "Вход на сервер (SSH, порт 22)",
    "admin-login": "Вход в панель",
    "admin-api": "API панели",
    "panel-port": "Порт панели",
}
_SCOPE_EFFECTS = {
    "ssh": "Ограничен только удалённый вход на сервер. VPN продолжает работать.",
    "admin-login": "Ограничен вход в панель с этого IP. VPN продолжает работать.",
    "admin-api": "Ограничены административные API-запросы с этого IP. VPN продолжает работать.",
    "panel-port": "Ограничен доступ к панели. VPN-сервисы не затрагиваются.",
}
_REASON_LABELS = {
    "threshold_exceeded": "Превышен лимит неудачных попыток",
    "manual": "Ручная блокировка",
    "manual_block": "Ручная блокировка",
    "web-threat": "Обнаружена веб-атака",
    "invalid_credentials": "Неудачная авторизация",
    "rate_limit": "Превышен лимит запросов",
}
_STATE_LABELS = {
    "active": "Активна",
    "revoked": "Снята",
    "expired": "Истекла",
}
_AUDIT_ACTION_LABELS = {
    "decision.auto_created": "Автоматически создана блокировка",
    "decision.manual_created": "Создана ручная блокировка",
    "decision.created": "Создана блокировка",
    "decision.revoked": "Блокировка снята",
    "allowlist.created": "Добавлено исключение",
    "allowlist.deleted": "Удалено исключение",
    "allowlist.updated": "Изменено исключение",
}
_RESULT_LABELS = {
    "success": "Успешно",
    "ok": "Успешно",
    "failure": "Ошибка",
    "error": "Ошибка",
    "denied": "Отклонено",
}
_GUARD_ACTION_LABELS = {
    "block": "Запрос заблокирован",
    "rate_limit": "Превышен лимит запросов",
    "monitor": "Зафиксировано без блокировки",
    "allow": "Разрешено",
}
_RULE_LABELS = {
    "sensitive-path": "Сканирование закрытых путей",
    "path-traversal": "Попытка выхода за каталог",
    "sqli": "SQL-инъекция",
    "xss": "XSS",
    "command-injection": "Командная инъекция",
    "dangerous-method": "Опасный HTTP-метод",
    "body-size": "Слишком большой запрос",
    "login-rate": "Слишком частые попытки входа",
    "api-rate": "Слишком частые API-запросы",
    "reputation": "Совпадение с локальной репутацией",
}
_NETWORK_TYPE_LABELS = (
    ("botnet", "Ботнет"),
    ("tor", "Узел Tor"),
    ("proxy", "Прокси-сеть"),
    ("vpn", "VPN-сеть"),
    ("hosting", "Сеть хостинг-провайдера"),
    ("scanner", "Сеть сканера"),
)


def _enabled_from_environment() -> bool:
    value = os.environ.get("SG_INFOSEC_IP_INTEL_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "off", "disabled"}


def _country_flag(code: str) -> str:
    normalized = code.lower()
    if not re.fullmatch(r"[a-z]{2}", normalized):
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("a")) for letter in normalized)


def _country_name(code: str) -> str:
    normalized = code.strip().lower()
    if not re.fullmatch(r"[a-z]{2}", normalized):
        return ""
    return _COUNTRY_NAMES.get(normalized, normalized.upper())


def _network_type(reputation: Mapping[str, Any] | None) -> str:
    tags = {
        str(item).strip().lower()
        for item in (reputation or {}).get("tags", [])
        if str(item).strip()
    }
    for tag, label in _NETWORK_TYPE_LABELS:
        if tag in tags:
            return label
    return "Публичная сеть"


def _is_local_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
        return True
    if isinstance(address, ipaddress.IPv4Address):
        return (
            address in ipaddress.ip_network("10.0.0.0/8")
            or address in ipaddress.ip_network("172.16.0.0/12")
            or address in ipaddress.ip_network("192.168.0.0/16")
        )
    return address in ipaddress.ip_network("fc00::/7")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _default_fetcher(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "SG-Gateway-InfoSec/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(256 * 1024)
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("RIPEstat response is not an object")
    return decoded


class IPIntelligenceResolver:
    def __init__(
        self,
        *,
        cache_path: str | os.PathLike[str] = DEFAULT_IP_INTELLIGENCE_CACHE,
        country_lookup: Callable[[str], str] = lookup_country_code,
        fetcher: Callable[[str, float], dict[str, Any]] = _default_fetcher,
        now: Callable[[], datetime] | None = None,
        timeout: float = 0.8,
        ttl: timedelta = timedelta(days=7),
        negative_ttl: timedelta = timedelta(hours=1),
        enabled: bool | None = None,
        reputation_path: str | os.PathLike[str] = DEFAULT_REPUTATION_PATH,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.country_lookup = country_lookup
        self.fetcher = fetcher
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout = min(max(float(timeout), 0.1), 1.0)
        self.ttl = max(ttl, timedelta(minutes=1))
        self.negative_ttl = max(negative_ttl, timedelta(minutes=1))
        self.enabled = _enabled_from_environment() if enabled is None else bool(enabled)
        self.reputation_path = Path(reputation_path)
        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, Any]] | None = None
        self._reputation_mtime: int | None = None
        self._reputation: Any | None = None

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            if self._cache is not None:
                return self._cache
            entries: dict[str, dict[str, Any]] = {}
            try:
                if self.cache_path.stat().st_size > _MAX_CACHE_BYTES:
                    raise ValueError("cache is too large")
                payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
                raw_entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
                if isinstance(raw_entries, dict):
                    for ip, item in list(raw_entries.items())[-_MAX_CACHE_ENTRIES:]:
                        if isinstance(ip, str) and isinstance(item, dict):
                            entries[ip] = item
            except (OSError, ValueError, json.JSONDecodeError):
                entries = {}
            self._cache = entries
            return self._cache

    def _save_cache(self) -> None:
        with self._lock:
            entries = self._load_cache()
            if len(entries) > _MAX_CACHE_ENTRIES:
                ordered = sorted(
                    entries.items(),
                    key=lambda item: str(item[1].get("cached_at", "")),
                )
                entries = dict(ordered[-_MAX_CACHE_ENTRIES:])
                self._cache = entries
            try:
                _atomic_json(
                    self.cache_path,
                    {"version": _CACHE_VERSION, "entries": entries},
                )
            except OSError:
                return

    def _cached(self, ip: str) -> dict[str, Any] | None:
        item = self._load_cache().get(ip)
        if not isinstance(item, dict):
            return None
        try:
            cached_at = datetime.fromisoformat(
                str(item["cached_at"]).replace("Z", "+00:00")
            )
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            return None
        data = item.get("data")
        if not isinstance(data, dict):
            return None
        lifetime = self.ttl if data.get("available") else self.negative_ttl
        age = self.now().astimezone(timezone.utc) - cached_at.astimezone(timezone.utc)
        if age > lifetime:
            return None
        return dict(data)

    def _lookup_reputation(self, ip: str) -> dict[str, Any]:
        with self._lock:
            try:
                mtime = self.reputation_path.stat().st_mtime_ns
            except OSError:
                return {}
            try:
                if self._reputation is None or self._reputation_mtime != mtime:
                    from app.security.sg_infosec_guard import ReputationIndex

                    self._reputation = ReputationIndex.load(self.reputation_path)
                    self._reputation_mtime = mtime
                entry = self._reputation.lookup(ip)
                return entry.view() if entry is not None else {}
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return {}

    def _country_code(self, ip: str) -> str:
        try:
            value = str(self.country_lookup(ip) or "").strip().lower()
        except (OSError, RuntimeError, ValueError):
            return ""
        return value if re.fullmatch(r"[a-z]{2}", value) else ""

    def _base(self, ip: str, country_code: str) -> dict[str, Any]:
        name = _country_name(country_code)
        return {
            "ip": ip,
            "country_code": country_code,
            "country_name": name,
            "country_flag": _country_flag(country_code),
            "asn": None,
            "organization": "",
            "prefix": "",
            "source": "GeoIP" if country_code else "",
            "available": False,
        }

    def _render(
        self,
        data: Mapping[str, Any],
        reputation: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        result = dict(data)
        network_type = _network_type(reputation)
        result["network_type_label"] = network_type
        country = " ".join(
            filter(
                None,
                [
                    str(result.get("country_flag", "")),
                    str(result.get("country_name", "")),
                ],
            )
        ).strip()
        routing = []
        if result.get("asn"):
            routing.append(f"AS{result['asn']}")
        if result.get("organization"):
            routing.append(str(result["organization"]))
        if routing:
            result["summary"] = " · ".join(filter(None, [country, *routing]))
        elif country:
            result["summary"] = f"{country} · Сведения о сети недоступны"
        else:
            result["summary"] = "Сведения о сети недоступны"
        details = []
        if result.get("prefix"):
            details.append(f"Сеть {result['prefix']}")
        details.append(network_type)
        result["details"] = " · ".join(details)
        return result

    def _unavailable(
        self,
        ip: str,
        reputation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._render(self._base(ip, self._country_code(ip)), reputation)

    def resolve(self, ip: object, reputation: object = None) -> dict[str, Any]:
        try:
            address = ipaddress.ip_address(str(ip or "").strip())
        except ValueError:
            return {
                "ip": str(ip or ""),
                "summary": "Некорректный IP-адрес",
                "details": "",
                "country_code": "",
                "country_name": "",
                "country_flag": "",
                "asn": None,
                "organization": "",
                "prefix": "",
                "network_type_label": "Не определена",
                "source": "",
                "available": False,
            }
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        canonical = address.compressed
        if _is_local_address(address):
            return {
                "ip": canonical,
                "summary": "Локальный адрес",
                "details": "Внутренняя сеть сервера",
                "country_code": "",
                "country_name": "",
                "country_flag": "",
                "asn": None,
                "organization": "",
                "prefix": "",
                "network_type_label": "Локальная сеть",
                "source": "local",
                "available": True,
            }

        rep = (
            dict(reputation)
            if isinstance(reputation, Mapping)
            else self._lookup_reputation(canonical)
        )
        cached = self._cached(canonical)
        if cached is not None:
            return self._render(cached, rep)

        data = self._base(canonical, self._country_code(canonical))
        if self.enabled:
            try:
                query = urllib.parse.urlencode({"resource": canonical})
                payload = self.fetcher(
                    f"{RIPESTAT_PREFIX_OVERVIEW}?{query}",
                    self.timeout,
                )
                body = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(body, dict):
                    raise ValueError("missing RIPEstat data")
                data["prefix"] = str(body.get("resource") or "")[:80]
                raw_asns = body.get("asns")
                if isinstance(raw_asns, list) and raw_asns:
                    first = raw_asns[0]
                    if isinstance(first, dict):
                        raw_asn = first.get("asn")
                        data["asn"] = int(raw_asn) if raw_asn else None
                        data["organization"] = " ".join(
                            str(first.get("holder") or "").split()
                        )[:160]
                    elif str(first).isdigit():
                        data["asn"] = int(first)
                data["source"] = "RIPEstat + GeoIP" if data["country_code"] else "RIPEstat"
                data["available"] = bool(data.get("asn") or data.get("prefix"))
            except (
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                pass

        with self._lock:
            self._load_cache()[canonical] = {
                "cached_at": self.now()
                .astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "data": data,
            }
            self._save_cache()
        return self._render(data, rep)

    def resolve_many(
        self,
        values: Iterable[tuple[object, object]],
    ) -> dict[str, dict[str, Any]]:
        unique: dict[str, object] = {}
        for raw_ip, reputation in values:
            text = str(raw_ip or "").strip()
            if text and text not in unique:
                unique[text] = reputation
        items = list(unique.items())
        results: dict[str, dict[str, Any]] = {}
        immediate = items[:_MAX_PAGE_LOOKUPS]
        if immediate:
            with ThreadPoolExecutor(max_workers=min(4, len(immediate))) as executor:
                futures = {
                    executor.submit(self.resolve, ip, rep): ip
                    for ip, rep in immediate
                }
                for future in as_completed(futures):
                    ip = futures[future]
                    try:
                        results[ip] = future.result()
                    except Exception:
                        rep = unique.get(ip)
                        results[ip] = self._unavailable(
                            ip,
                            rep if isinstance(rep, Mapping) else {},
                        )
        for ip, rep in items[_MAX_PAGE_LOOKUPS:]:
            results[ip] = self._unavailable(
                ip,
                rep if isinstance(rep, Mapping) else {},
            )
        return results


_shared_resolver: IPIntelligenceResolver | None = None
_shared_lock = threading.Lock()


def get_ip_intelligence_resolver() -> IPIntelligenceResolver:
    global _shared_resolver
    with _shared_lock:
        if _shared_resolver is None:
            _shared_resolver = IPIntelligenceResolver(
                cache_path=os.environ.get(
                    "SG_INFOSEC_IP_INTEL_CACHE",
                    str(DEFAULT_IP_INTELLIGENCE_CACHE),
                ),
                reputation_path=os.environ.get(
                    "SG_INFOSEC_REPUTATION_FILE",
                    str(DEFAULT_REPUTATION_PATH),
                ),
            )
        return _shared_resolver


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    normalized = re.sub(r"(\.\d{6})\d+(?=[+-])", r"\1", normalized)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_time(value: object, local_timezone: tzinfo) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return "—" if not value else str(value)
    return parsed.astimezone(local_timezone).strftime("%d.%m.%Y, %H:%M")


def _timezone(value: tzinfo | None) -> tzinfo:
    return value or datetime.now().astimezone().tzinfo or timezone.utc


def _scope_label(value: object) -> str:
    text = str(value or "")
    return _SCOPE_LABELS.get(text, text or "Не указана")


def _decision(
    item: Mapping[str, Any],
    intel: Mapping[str, Any],
    local_timezone: tzinfo,
) -> dict[str, Any]:
    raw = dict(item)
    scope = str(raw.get("scope") or "")
    reason = str(raw.get("reason_code") or raw.get("reason") or "manual")
    state = str(raw.get("state") or "")
    result = dict(raw)
    result.update(
        {
            "scope_label": _scope_label(scope),
            "scope_effect": _SCOPE_EFFECTS.get(
                scope,
                "Ограничение действует только в указанной области.",
            ),
            "reason_label": _REASON_LABELS.get(
                reason,
                reason.replace("_", " ") or "Ручная блокировка",
            ),
            "state_label": _STATE_LABELS.get(state, state or "Не указано"),
            "created_at_label": _format_time(
                raw.get("created_at"), local_timezone
            ),
            "expires_at_label": _format_time(
                raw.get("expires_at"), local_timezone
            ),
            "updated_at_label": _format_time(
                raw.get("updated_at"), local_timezone
            ),
            "ip_intel": dict(intel),
            "technical": {
                key: raw.get(key)
                for key in (
                    "id",
                    "source_id",
                    "policy_id",
                    "scope",
                    "reason_code",
                    "state",
                    "backend",
                    "strike",
                    "created_at",
                    "starts_at",
                    "expires_at",
                    "updated_at",
                )
                if raw.get(key) not in {None, ""}
            },
        }
    )
    return result


def _intelligence_for(
    source: Any,
    intelligence: Mapping[str, Mapping[str, Any]],
    ip: object,
    reputation: object = None,
) -> Mapping[str, Any]:
    key = str(ip or "")
    known = intelligence.get(key)
    if known is not None:
        return known
    return source.resolve(ip, reputation)


def present_management_overview(
    overview: Mapping[str, Any],
    *,
    resolver: IPIntelligenceResolver | Any | None = None,
    local_timezone: tzinfo | None = None,
) -> dict[str, Any]:
    result = dict(overview)
    source = resolver or get_ip_intelligence_resolver()
    zone = _timezone(local_timezone)
    active_raw = [
        item
        for item in overview.get("active_decisions", [])
        if isinstance(item, Mapping)
    ]
    history_raw = [
        item
        for item in overview.get("history", [])
        if isinstance(item, Mapping)
    ]
    allowlist_raw = [
        item
        for item in overview.get("allowlist", [])
        if isinstance(item, Mapping)
    ]
    audit_raw = [
        item
        for item in overview.get("audit", [])
        if isinstance(item, Mapping)
    ]
    pairs = [
        (item.get("ip"), {})
        for item in (*active_raw, *history_raw)
        if item.get("ip")
    ]
    if hasattr(source, "resolve_many"):
        intelligence = source.resolve_many(pairs)
    else:
        intelligence = {}
        for ip, reputation in pairs:
            key = str(ip)
            if key not in intelligence:
                intelligence[key] = source.resolve(ip, reputation)

    result["active_decisions"] = [
        _decision(
            item,
            _intelligence_for(source, intelligence, item.get("ip")),
            zone,
        )
        for item in active_raw
    ]
    result["history"] = [
        _decision(
            item,
            _intelligence_for(source, intelligence, item.get("ip")),
            zone,
        )
        for item in history_raw
    ]
    result["allowlist"] = [
        {
            **dict(item),
            "scope_label": (
                _scope_label(item.get("scope"))
                if item.get("scope")
                else "Все области"
            ),
            "expires_at_label": (
                _format_time(item.get("expires_at"), zone)
                if item.get("expires_at")
                else "Без срока"
            ),
            "technical": {
                key: item.get(key)
                for key in ("id", "scope", "created_at", "expires_at")
                if item.get(key) not in {None, ""}
            },
        }
        for item in allowlist_raw
    ]
    result["audit"] = [
        {
            **dict(item),
            "action_label": _AUDIT_ACTION_LABELS.get(
                str(item.get("action") or ""),
                str(item.get("action") or "Действие"),
            ),
            "target_label": (
                "Блокировка"
                if item.get("target_type") == "decision"
                else (
                    "Исключение"
                    if item.get("target_type") == "allowlist"
                    else str(item.get("target_type") or "Объект")
                )
            ),
            "result_label": _RESULT_LABELS.get(
                str(item.get("result") or ""),
                str(item.get("result") or "Не указано"),
            ),
            "occurred_at_label": _format_time(item.get("occurred_at"), zone),
            "technical": {
                key: item.get(key)
                for key in (
                    "actor",
                    "action",
                    "target_type",
                    "target_id",
                    "request_id",
                    "result",
                    "occurred_at",
                )
                if item.get(key) not in {None, ""}
            },
        }
        for item in audit_raw
    ]
    return result


def present_guard_overview(
    overview: Mapping[str, Any],
    *,
    resolver: IPIntelligenceResolver | Any | None = None,
    local_timezone: tzinfo | None = None,
) -> dict[str, Any]:
    result = dict(overview)
    source = resolver or get_ip_intelligence_resolver()
    zone = _timezone(local_timezone)
    alerts = [
        item
        for item in overview.get("alerts", [])
        if isinstance(item, Mapping)
    ]
    pairs = [
        (item.get("ip"), item.get("reputation") or {})
        for item in alerts
        if item.get("ip")
    ]
    if hasattr(source, "resolve_many"):
        intelligence = source.resolve_many(pairs)
    else:
        intelligence = {}
        for ip, reputation in pairs:
            key = str(ip)
            if key not in intelligence:
                intelligence[key] = source.resolve(ip, reputation)

    presented = []
    for item in alerts:
        raw = dict(item)
        ip = str(raw.get("ip") or "")
        rule_ids = [str(value) for value in raw.get("rule_ids", [])]
        presented.append(
            {
                **raw,
                "action_label": _GUARD_ACTION_LABELS.get(
                    str(raw.get("action") or ""),
                    str(raw.get("action") or "Действие"),
                ),
                "scope_label": _scope_label(raw.get("scope")),
                "rule_labels": [
                    _RULE_LABELS.get(value, value) for value in rule_ids
                ],
                "occurred_at_label": _format_time(
                    raw.get("occurred_at"), zone
                ),
                "ip_intel": _intelligence_for(
                    source,
                    intelligence,
                    ip,
                    raw.get("reputation") or {},
                ),
                "technical": {
                    "id": raw.get("id"),
                    "action": raw.get("action"),
                    "scope": raw.get("scope"),
                    "rule_ids": rule_ids,
                    "occurred_at": raw.get("occurred_at"),
                },
            }
        )
    result["alerts"] = presented
    return result
