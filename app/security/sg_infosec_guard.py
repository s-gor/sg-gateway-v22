from __future__ import annotations

import ipaddress
import json
import os
import queue
import re
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SETTINGS_PATH = Path("/etc/sg-gateway/sg-infosec-guard.json")
DEFAULT_REPUTATION_PATH = Path("/etc/sg-gateway/sg-infosec-reputation.json")
DEFAULT_ALERTS_PATH = Path("/var/lib/sg-gateway/sg-infosec-alerts.jsonl")
MAX_REPUTATION_ENTRIES = 20_000
MAX_ALERT_ENTRIES = 5_000
MAX_INSPECTION_BYTES = 65_536
_ALLOWED_MODES = frozenset({"off", "monitor", "enforce"})
_ALLOWED_CONTENT_TYPES = (
    "application/json",
    "application/x-www-form-urlencoded",
    "text/",
    "application/xml",
)

_SENSITIVE_PATH = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:$|[/.])|\.git(?:$|/)|wp-admin(?:$|/)|"
    r"wp-login\.php$|phpmyadmin(?:$|/)|server-status$|actuator(?:$|/)|"
    r"cgi-bin(?:$|/)|vendor/phpunit(?:$|/))"
)
_TRAVERSAL = re.compile(
    r"(?i)(?:\.\./|\.\.\\|%2e%2e|%252e%252e|%c0%ae%c0%ae)"
)
_SQLI = re.compile(
    r"(?is)(?:\bunion(?:\s|%20|\+)+select\b|"
    r"\bselect\b.{0,80}\bfrom\b|\binformation_schema\b|"
    r"\bsleep\s*\(|\bbenchmark\s*\(|"
    r"(?:\bor\b|%20or%20|\+or\+).{0,20}"
    r"(?:1\s*=\s*1|'[^']*'\s*=\s*'[^']*'))"
)
_XSS = re.compile(
    r"(?is)(?:<\s*script\b|javascript\s*:|data\s*:\s*text/html|"
    r"on(?:error|load|click|mouseover|focus)\s*=|"
    r"<\s*(?:iframe|object|embed|svg)\b)"
)
_COMMAND_INJECTION = re.compile(
    r"(?is)(?:\$\s*\(|`[^`]{0,200}`|(?:;|\||&&)\s*"
    r"(?:curl|wget|nc|ncat|bash|sh|python|perl|php)\b)"
)
_DANGEROUS_METHODS = frozenset({"TRACE", "TRACK", "CONNECT"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _atomic_write(path: Path, text: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _canonical_ip(value: object) -> str:
    address = ipaddress.ip_address(str(value or "").strip())
    if (
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped is not None
    ):
        return str(address.ipv4_mapped)
    return address.compressed


@dataclass(frozen=True)
class GuardSettings:
    mode: str = "enforce"
    max_body_bytes: int = MAX_INSPECTION_BYTES
    login_requests_per_minute: int = 20
    api_requests_per_minute: int = 120
    block_score: int = 80
    notification_min_score: int = 70
    notification_webhook: str = ""

    @classmethod
    def load(
        cls,
        path: str | os.PathLike[str] = DEFAULT_SETTINGS_PATH,
    ) -> "GuardSettings":
        source = Path(path)
        if not source.exists():
            return cls()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("guard settings must be a JSON object")
        settings = cls(
            mode=str(payload.get("mode", cls.mode)).strip().lower(),
            max_body_bytes=int(
                payload.get("max_body_bytes", cls.max_body_bytes)
            ),
            login_requests_per_minute=int(
                payload.get(
                    "login_requests_per_minute",
                    cls.login_requests_per_minute,
                )
            ),
            api_requests_per_minute=int(
                payload.get(
                    "api_requests_per_minute",
                    cls.api_requests_per_minute,
                )
            ),
            block_score=int(payload.get("block_score", cls.block_score)),
            notification_min_score=int(
                payload.get(
                    "notification_min_score",
                    cls.notification_min_score,
                )
            ),
            notification_webhook=str(
                payload.get("notification_webhook", "")
            ).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.mode not in _ALLOWED_MODES:
            raise ValueError("mode must be off, monitor, or enforce")
        if not 1024 <= self.max_body_bytes <= 1_048_576:
            raise ValueError(
                "max_body_bytes must be between 1024 and 1048576"
            )
        if not 1 <= self.login_requests_per_minute <= 10_000:
            raise ValueError("login_requests_per_minute is out of range")
        if not 1 <= self.api_requests_per_minute <= 100_000:
            raise ValueError("api_requests_per_minute is out of range")
        if not 1 <= self.block_score <= 100:
            raise ValueError("block_score must be between 1 and 100")
        if not 1 <= self.notification_min_score <= 100:
            raise ValueError(
                "notification_min_score must be between 1 and 100"
            )
        if (
            self.notification_webhook
            and not self.notification_webhook.startswith("https://")
        ):
            raise ValueError("notification_webhook must use https")
        if len(self.notification_webhook) > 2048:
            raise ValueError("notification_webhook is too long")

    def save(
        self,
        path: str | os.PathLike[str] = DEFAULT_SETTINGS_PATH,
    ) -> None:
        self.validate()
        _atomic_write(
            Path(path),
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
        )


@dataclass(frozen=True)
class ReputationEntry:
    network: ipaddress.IPv4Network | ipaddress.IPv6Network
    score: int
    country: str = ""
    asn: int | None = None
    tags: tuple[str, ...] = ()
    expires_at: datetime | None = None

    def view(self) -> dict[str, Any]:
        return {
            "cidr": self.network.compressed,
            "score": self.score,
            "country": self.country,
            "asn": self.asn,
            "tags": list(self.tags),
            "expires_at": _iso(self.expires_at) if self.expires_at else None,
        }


class ReputationIndex:
    def __init__(self, entries: Iterable[ReputationEntry] = ()) -> None:
        self._entries = tuple(
            sorted(
                entries,
                key=lambda item: item.network.prefixlen,
                reverse=True,
            )
        )

    @classmethod
    def load(
        cls,
        path: str | os.PathLike[str] = DEFAULT_REPUTATION_PATH,
        *,
        now: datetime | None = None,
    ) -> "ReputationIndex":
        source = Path(path)
        if not source.exists():
            return cls()
        payload = json.loads(source.read_text(encoding="utf-8"))
        raw_entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(raw_entries, list):
            raise ValueError("reputation file must contain an entries array")
        if len(raw_entries) > MAX_REPUTATION_ENTRIES:
            raise ValueError("reputation file contains too many entries")
        current = now or _utc_now()
        entries: list[ReputationEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError("reputation entry must be an object")
            network = ipaddress.ip_network(
                str(raw.get("cidr", "")).strip(),
                strict=False,
            )
            score = int(raw.get("score", 0))
            if not 1 <= score <= 100:
                raise ValueError(
                    "reputation score must be between 1 and 100"
                )
            country = str(raw.get("country", "")).strip().upper()
            if country and (len(country) != 2 or not country.isalpha()):
                raise ValueError(
                    "reputation country must be a two-letter code"
                )
            raw_asn = raw.get("asn")
            asn = int(raw_asn) if raw_asn not in {None, ""} else None
            if asn is not None and not 1 <= asn <= 4_294_967_295:
                raise ValueError("reputation ASN is out of range")
            raw_tags = raw.get("tags", [])
            if not isinstance(raw_tags, list) or len(raw_tags) > 16:
                raise ValueError("reputation tags must be a short array")
            tags = tuple(
                str(item).strip().lower()[:48]
                for item in raw_tags
                if str(item).strip()
            )
            expires_at = None
            if raw.get("expires_at"):
                text = str(raw["expires_at"]).replace("Z", "+00:00")
                expires_at = datetime.fromisoformat(text)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                expires_at = expires_at.astimezone(timezone.utc)
                if expires_at <= current:
                    continue
            entries.append(
                ReputationEntry(
                    network=network,
                    score=score,
                    country=country,
                    asn=asn,
                    tags=tags,
                    expires_at=expires_at,
                )
            )
        return cls(entries)

    def lookup(self, ip: str) -> ReputationEntry | None:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        for entry in self._entries:
            if (
                address.version == entry.network.version
                and address in entry.network
            ):
                return entry
        return None

    def count(self) -> int:
        return len(self._entries)

    def export(self) -> dict[str, Any]:
        return {"entries": [entry.view() for entry in self._entries]}

    def save(
        self,
        path: str | os.PathLike[str] = DEFAULT_REPUTATION_PATH,
    ) -> None:
        _atomic_write(
            Path(path),
            json.dumps(self.export(), ensure_ascii=False, indent=2) + "\n",
        )


class SlidingWindowLimiter:
    def __init__(self, *, max_keys: int = 8192) -> None:
        self.max_keys = max(16, max_keys)
        self._lock = threading.Lock()
        self._windows: OrderedDict[
            tuple[str, str], deque[float]
        ] = OrderedDict()

    def allow(
        self,
        ip: str,
        bucket: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> bool:
        current = time.monotonic() if now is None else float(now)
        key = (ip, bucket)
        cutoff = current - window_seconds
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                if len(self._windows) >= self.max_keys:
                    self._windows.popitem(last=False)
                window = deque()
                self._windows[key] = window
            else:
                self._windows.move_to_end(key)
            while window and window[0] <= cutoff:
                window.popleft()
            allowed = len(window) < limit
            window.append(current)
            return allowed


class AlertStore:
    def __init__(
        self,
        path: str | os.PathLike[str] = DEFAULT_ALERTS_PATH,
        *,
        max_entries: int = MAX_ALERT_ENTRIES,
    ) -> None:
        self.path = Path(path)
        self.max_entries = max(1, min(int(max_entries), 50_000))
        self._lock = threading.RLock()

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in self.path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                items.append(item)
        return items[-self.max_entries :]

    def _write(self, items: list[dict[str, Any]]) -> None:
        text = "".join(
            json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
            for item in items[-self.max_entries :]
        )
        _atomic_write(self.path, text)

    def append(
        self,
        *,
        ip: str,
        action: str,
        score: int,
        rule_ids: Iterable[str],
        scope: str,
        reputation: dict[str, Any],
    ) -> str:
        identifier = uuid.uuid4().hex
        safe_reputation: dict[str, Any] = {}
        for key in ("score", "country", "asn", "tags", "cidr"):
            value = reputation.get(key)
            if value is None or value == "" or value == []:
                continue
            safe_reputation[key] = value
        item = {
            "id": identifier,
            "occurred_at": _iso(_utc_now()),
            "ip": _canonical_ip(ip),
            "action": action,
            "score": max(0, min(int(score), 100)),
            "rule_ids": sorted(
                {str(value)[:64] for value in rule_ids if str(value)}
            ),
            "scope": str(scope)[:32],
            "reputation": safe_reputation,
            "acknowledged": False,
        }
        with self._lock:
            items = self._read()
            items.append(item)
            self._write(items)
        return identifier

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read()
        return list(
            reversed(items[-max(1, min(int(limit), 500)) :])
        )

    def unread_count(self) -> int:
        with self._lock:
            return sum(
                1 for item in self._read() if not item.get("acknowledged")
            )

    def acknowledge(self, identifier: str) -> bool:
        changed = False
        with self._lock:
            items = self._read()
            for item in items:
                if (
                    item.get("id") == identifier
                    and not item.get("acknowledged")
                ):
                    item["acknowledged"] = True
                    changed = True
            if changed:
                self._write(items)
        return changed

    def acknowledge_all(self) -> int:
        changed = 0
        with self._lock:
            items = self._read()
            for item in items:
                if not item.get("acknowledged"):
                    item["acknowledged"] = True
                    changed += 1
            if changed:
                self._write(items)
        return changed


@dataclass(frozen=True)
class GuardDecision:
    action: str
    status_code: int
    score: int
    rule_ids: tuple[str, ...] = ()
    scope: str = ""
    reputation: dict[str, Any] = field(default_factory=dict)
    alert_id: str = ""


class WebhookNotifier:
    def __init__(self, url: str, *, queue_size: int = 128) -> None:
        self.url = url
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=queue_size
        )
        self._thread: threading.Thread | None = None

    def submit(self, payload: dict[str, Any]) -> None:
        if not self.url:
            return
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run,
                name="sg-infosec-webhook",
                daemon=True,
            )
            self._thread.start()
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            return

    def _run(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                encoded = json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                request = urllib.request.Request(
                    self.url,
                    data=encoded,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "SG-InfoSec/1",
                    },
                )
                with urllib.request.urlopen(
                    request,
                    timeout=2.0,
                ) as response:
                    response.read(1024)
            except (OSError, ValueError):
                pass
            finally:
                self._queue.task_done()


class GuardEngine:
    def __init__(
        self,
        *,
        settings: GuardSettings | None = None,
        alerts: AlertStore | None = None,
        reputation: ReputationIndex | None = None,
        limiter: SlidingWindowLimiter | None = None,
        event_client: Any | None = None,
        management_client: Any | None = None,
    ) -> None:
        self.settings = settings or GuardSettings()
        self.alerts = alerts or AlertStore()
        self.reputation = reputation or ReputationIndex()
        self.limiter = limiter or SlidingWindowLimiter()
        self.event_client = event_client
        self.management_client = management_client
        self.notifier = WebhookNotifier(
            self.settings.notification_webhook
        )
        self._counters_lock = threading.Lock()
        self._counters = {
            "inspected": 0,
            "monitored": 0,
            "blocked": 0,
            "rate_limited": 0,
        }
        self._last_block: dict[tuple[str, str], float] = {}

    @classmethod
    def from_environment(cls) -> "GuardEngine":
        settings_path = Path(
            os.environ.get(
                "SG_INFOSEC_GUARD_SETTINGS",
                str(DEFAULT_SETTINGS_PATH),
            )
        )
        reputation_path = Path(
            os.environ.get(
                "SG_INFOSEC_REPUTATION_FILE",
                str(DEFAULT_REPUTATION_PATH),
            )
        )
        alerts_path = Path(
            os.environ.get(
                "SG_INFOSEC_ALERTS_FILE",
                str(DEFAULT_ALERTS_PATH),
            )
        )
        return cls(
            settings=GuardSettings.load(settings_path),
            reputation=ReputationIndex.load(reputation_path),
            alerts=AlertStore(alerts_path),
        )

    def update_settings(self, settings: GuardSettings) -> None:
        settings.validate()
        self.settings = settings
        self.notifier = WebhookNotifier(settings.notification_webhook)

    def update_reputation(self, reputation: ReputationIndex) -> None:
        self.reputation = reputation

    def _inspect_text(self, target: str, body: str) -> dict[str, int]:
        findings: dict[str, int] = {}
        lowered = target.lower()
        decoded = urllib.parse.unquote(lowered)
        combined = f"{lowered}\n{decoded}\n{body.lower()}"
        if _SENSITIVE_PATH.search(decoded):
            findings["sensitive-path"] = 95
        if _TRAVERSAL.search(combined):
            findings["path-traversal"] = 95
        if _SQLI.search(combined):
            findings["sqli"] = 90
        if _XSS.search(combined):
            findings["xss"] = 90
        if _COMMAND_INJECTION.search(combined):
            findings["command-injection"] = 95
        return findings

    def _rate_rule(
        self,
        request: Any,
        ip: str,
    ) -> tuple[str, int] | None:
        path = str(getattr(request, "path", ""))
        method = str(getattr(request, "method", "GET")).upper()
        if method == "POST" and path in {"/login", "/admin/login"}:
            allowed = self.limiter.allow(
                ip,
                "login",
                limit=self.settings.login_requests_per_minute,
                window_seconds=60,
            )
            return None if allowed else ("login-rate", 85)
        if path.startswith("/api/"):
            allowed = self.limiter.allow(
                ip,
                "api",
                limit=self.settings.api_requests_per_minute,
                window_seconds=60,
            )
            return None if allowed else ("api-rate", 80)
        return None

    def evaluate(self, request: Any, *, ip: str) -> GuardDecision:
        try:
            canonical_ip = _canonical_ip(ip)
        except ValueError:
            return GuardDecision(
                action="allow",
                status_code=200,
                score=0,
            )
        with self._counters_lock:
            self._counters["inspected"] += 1
        if self.settings.mode == "off":
            return GuardDecision(
                action="allow",
                status_code=200,
                score=0,
            )

        method = str(getattr(request, "method", "GET")).upper()
        path = str(getattr(request, "path", ""))[:4096]
        raw_query = getattr(request, "query_string", b"")
        if isinstance(raw_query, bytes):
            query = raw_query[:8192].decode(
                "utf-8",
                errors="replace",
            )
        else:
            query = str(raw_query)[:8192]
        target = path + ("?" + query if query else "")
        findings: dict[str, int] = {}
        if method in _DANGEROUS_METHODS:
            findings["dangerous-method"] = 85

        content_length = getattr(request, "content_length", None)
        try:
            length = (
                int(content_length)
                if content_length is not None
                else 0
            )
        except (TypeError, ValueError):
            length = 0
        if length > self.settings.max_body_bytes:
            findings["body-size"] = 85

        body = ""
        content_type = str(
            getattr(request, "content_type", "") or ""
        ).lower()
        if (
            0 < length <= min(
                self.settings.max_body_bytes,
                MAX_INSPECTION_BYTES,
            )
            and any(
                content_type.startswith(value)
                for value in _ALLOWED_CONTENT_TYPES
            )
        ):
            try:
                raw_body = request.get_data(cache=True, as_text=False)
                if isinstance(raw_body, bytes):
                    body = raw_body[:MAX_INSPECTION_BYTES].decode(
                        "utf-8",
                        errors="replace",
                    )
                else:
                    body = str(raw_body)[:MAX_INSPECTION_BYTES]
            except (OSError, RuntimeError, ValueError):
                body = ""
        findings.update(self._inspect_text(target, body))

        rate = self._rate_rule(request, canonical_ip)
        if rate is not None:
            findings[rate[0]] = rate[1]

        reputation_entry = self.reputation.lookup(canonical_ip)
        reputation: dict[str, Any] = {}
        if reputation_entry is not None:
            reputation = reputation_entry.view()
            findings["reputation"] = reputation_entry.score

        if not findings:
            return GuardDecision(
                action="allow",
                status_code=200,
                score=0,
            )

        score = min(
            100,
            max(findings.values()) + max(0, 5 * (len(findings) - 1)),
        )
        is_rate = any(rule.endswith("-rate") for rule in findings)
        should_block = score >= self.settings.block_score
        if self.settings.mode == "monitor" or not should_block:
            action = "monitor"
            status_code = 200
        else:
            action = "rate_limit" if is_rate else "block"
            status_code = 429 if is_rate else 403
        if path.startswith("/api/"):
            scope = "admin-api"
        elif path in {"/login", "/admin/login"}:
            scope = "admin-login"
        else:
            scope = "admin-api"
        alert_id = self.alerts.append(
            ip=canonical_ip,
            action=action,
            score=score,
            rule_ids=findings.keys(),
            scope=scope,
            reputation=reputation,
        )
        with self._counters_lock:
            if action == "monitor":
                self._counters["monitored"] += 1
            elif action == "rate_limit":
                self._counters["rate_limited"] += 1
            else:
                self._counters["blocked"] += 1

        event_payload: dict[str, Any] = {
            "reason": "web-threat",
            "rule_ids": sorted(findings),
            "score": float(score),
        }
        if reputation:
            event_payload["reputation_score"] = float(
                reputation.get("score", 0)
            )
            if reputation.get("country"):
                event_payload["country"] = reputation["country"]
            if reputation.get("asn"):
                event_payload["asn"] = float(reputation["asn"])
        if self.event_client is not None:
            try:
                self.event_client.emit_security_event(
                    scope=scope,
                    ip=canonical_ip,
                    route=str(
                        getattr(request, "endpoint", "") or "unknown"
                    ),
                    metadata=event_payload,
                )
            except (
                AttributeError,
                OSError,
                RuntimeError,
                ValueError,
            ):
                pass

        if (
            action in {"block", "rate_limit"}
            and self.management_client is not None
        ):
            key = (canonical_ip, scope)
            current = time.monotonic()
            if current - self._last_block.get(key, 0.0) >= 300:
                try:
                    self.management_client.create_manual_decision(
                        ip=canonical_ip,
                        scope=scope,
                        duration="1h",
                        reason="Автоматическая веб-защита SG InfoSec",
                    )
                    self._last_block[key] = current
                except (
                    AttributeError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ):
                    pass

        if score >= self.settings.notification_min_score:
            self.notifier.submit(
                {
                    "type": "sg-infosec.alert",
                    "id": alert_id,
                    "occurred_at": _iso(_utc_now()),
                    "ip": canonical_ip,
                    "action": action,
                    "score": score,
                    "rule_ids": sorted(findings),
                    "scope": scope,
                    "reputation": reputation,
                }
            )
        return GuardDecision(
            action=action,
            status_code=status_code,
            score=score,
            rule_ids=tuple(sorted(findings)),
            scope=scope,
            reputation=reputation,
            alert_id=alert_id,
        )

    def overview(self) -> dict[str, Any]:
        with self._counters_lock:
            counters = dict(self._counters)
        return {
            "mode": self.settings.mode,
            "settings": asdict(self.settings),
            "counters": counters,
            "alerts": self.alerts.list_recent(100),
            "unread_count": self.alerts.unread_count(),
            "reputation_count": self.reputation.count(),
        }


def register_sg_infosec_guard(
    app: Any,
    *,
    engine: GuardEngine | None = None,
) -> None:
    """Attach the WAF/rate/reputation guard before authentication hooks."""

    extensions = getattr(app, "extensions", None)
    if not isinstance(extensions, dict):
        return
    if "sg_infosec_guard" in extensions:
        return

    guard = engine or GuardEngine.from_environment()
    if guard.event_client is None:
        integration = extensions.get("sg_infosec")
        if isinstance(integration, dict):
            guard.event_client = integration.get("client")
    if guard.management_client is None:
        try:
            from app.security.sg_infosec_management import (
                SGInfoSecManagementClient,
            )

            guard.management_client = (
                SGInfoSecManagementClient.from_environment()
            )
        except (ImportError, RuntimeError, ValueError):
            guard.management_client = None

    @app.before_request
    def _sg_infosec_guard_before_request():
        from flask import g, jsonify, request

        try:
            from app.security.sg_infosec import client_ip_from_request

            ip = client_ip_from_request(request)
            decision = guard.evaluate(request, ip=ip)
        except (OSError, RuntimeError, ValueError):
            return None
        g.sg_infosec_guard_decision = decision
        if decision.action not in {"block", "rate_limit"}:
            return None
        response = jsonify(
            {
                "error": "request_blocked",
                "reason": "security_policy",
                "alert_id": decision.alert_id,
            }
        )
        response.status_code = decision.status_code
        response.headers["Cache-Control"] = "no-store"
        response.headers["Retry-After"] = "60"
        return response

    before_handlers = app.before_request_funcs.get(None, [])
    if before_handlers and before_handlers[-1] is _sg_infosec_guard_before_request:
        before_handlers.insert(0, before_handlers.pop())

    extensions["sg_infosec_guard"] = {"engine": guard}
