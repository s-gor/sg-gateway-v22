from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Hashable

from app.security.sg_infosec_guard import (
    AlertStore,
    GuardDecision,
    GuardEngine,
    GuardSettings,
    WebhookNotifier,
    register_sg_infosec_guard,
)

_GUARD_ADMIN_PREFIX = "/security/infosec/guard/"
_DEDUPLICATION_SECONDS = 60.0
_MAX_DEDUPLICATION_KEYS = 8192


class _RecentKeys:
    def __init__(
        self,
        *,
        ttl: float = _DEDUPLICATION_SECONDS,
        max_keys: int = _MAX_DEDUPLICATION_KEYS,
    ) -> None:
        self.ttl = max(1.0, float(ttl))
        self.max_keys = max(16, int(max_keys))
        self.lock = threading.Lock()
        self.items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()

    def get(self, key: Hashable, now: float) -> Any | None:
        item = self.items.get(key)
        if item is None:
            return None
        created_at, value = item
        if now - created_at >= self.ttl:
            del self.items[key]
            return None
        self.items.move_to_end(key)
        return value

    def put(self, key: Hashable, now: float, value: Any) -> None:
        self.items[key] = (now, value)
        self.items.move_to_end(key)
        while len(self.items) > self.max_keys:
            self.items.popitem(last=False)


class _FirstAttemptThrottle(dict[tuple[str, str], float]):
    """Treat an unseen key as eligible regardless of host monotonic uptime."""

    def get(
        self,
        key: tuple[str, str],
        default: float | None = None,
    ) -> float:
        if key not in self:
            return float("-inf")
        value = super().get(key, default)
        return float(value) if value is not None else float("-inf")


class _DeduplicatingAlertStore:
    """Collapse repeated identical findings before they amplify disk writes."""

    def __init__(self, store: AlertStore) -> None:
        self._store = store
        self._recent = _RecentKeys()

    def append(self, **payload: Any) -> str:
        key = (
            str(payload.get("ip", "")),
            str(payload.get("action", "")),
            str(payload.get("scope", "")),
            tuple(sorted(str(item) for item in payload.get("rule_ids", ()))),
            str((payload.get("reputation") or {}).get("cidr", "")),
        )
        now = time.monotonic()
        with self._recent.lock:
            existing = self._recent.get(key, now)
            if isinstance(existing, str) and existing:
                return existing
            identifier = self._store.append(**payload)
            self._recent.put(key, now, identifier)
            return identifier

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


class _DeduplicatingEventClient:
    """Bound repeated WAF events before they reach SQLite correlation state."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._recent = _RecentKeys()

    def emit_security_event(self, **payload: Any) -> bool:
        metadata = payload.get("metadata") or {}
        key = (
            str(payload.get("ip", "")),
            str(payload.get("scope", "")),
            str(payload.get("route", "")),
            str(metadata.get("reason", "")),
            tuple(sorted(str(item) for item in metadata.get("rule_ids", ()))),
        )
        now = time.monotonic()
        with self._recent.lock:
            if self._recent.get(key, now) is True:
                return True
            accepted = self._client.emit_security_event(**payload) is True
            if accepted:
                self._recent.put(key, now, True)
            return accepted

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _DeduplicatingNotifier:
    """Prevent one attacker from flooding the configured webhook."""

    def __init__(self, notifier: WebhookNotifier) -> None:
        self._notifier = notifier
        self._recent = _RecentKeys()

    def submit(self, payload: dict[str, Any]) -> None:
        key = (
            str(payload.get("ip", "")),
            str(payload.get("action", "")),
            str(payload.get("scope", "")),
            tuple(sorted(str(item) for item in payload.get("rule_ids", ()))),
        )
        now = time.monotonic()
        with self._recent.lock:
            if self._recent.get(key, now) is True:
                return
            self._recent.put(key, now, True)
        self._notifier.submit(payload)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._notifier, name)


class _VerifiedManagementClient:
    """Convert rejected bridge writes into exceptions understood by GuardEngine."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def create_manual_decision(self, **payload: Any):
        result = self._client.create_manual_decision(**payload)
        if (
            isinstance(result, tuple)
            and len(result) >= 1
            and result[0] is not True
        ):
            message = str(result[1] if len(result) > 1 else "")
            raise RuntimeError(message or "SG InfoSec decision was rejected")
        if result is False or result is None:
            raise RuntimeError("SG InfoSec decision was rejected")
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class HardenedGuardEngine(GuardEngine):
    """Production guard with bounded outputs and verified local writes."""

    def __init__(self, **kwargs: Any) -> None:
        alerts = kwargs.get("alerts")
        if alerts is None:
            alerts = AlertStore()
        if not isinstance(alerts, _DeduplicatingAlertStore):
            alerts = _DeduplicatingAlertStore(alerts)
        kwargs["alerts"] = alerts
        super().__init__(**kwargs)
        self._last_block = _FirstAttemptThrottle(self._last_block)
        self.notifier = _DeduplicatingNotifier(self.notifier)

    def update_settings(self, settings: GuardSettings) -> None:
        super().update_settings(settings)
        self.notifier = _DeduplicatingNotifier(self.notifier)

    def evaluate(self, request: Any, *, ip: str) -> GuardDecision:
        path = str(getattr(request, "path", "") or "")
        if path.startswith(_GUARD_ADMIN_PREFIX):
            try:
                from app.security.auth import is_authenticated

                if is_authenticated():
                    return GuardDecision(
                        action="allow",
                        status_code=200,
                        score=0,
                    )
            except RuntimeError:
                pass
        return super().evaluate(request, ip=ip)

    def verify_event_client(self) -> None:
        client = self.event_client
        if client is None or isinstance(client, _DeduplicatingEventClient):
            return
        self.event_client = _DeduplicatingEventClient(client)

    def verify_management_client(self) -> None:
        client = self.management_client
        if client is None or isinstance(client, _VerifiedManagementClient):
            return
        self.management_client = _VerifiedManagementClient(client)


def register_hardened_sg_infosec_guard(
    app: Any,
    *,
    engine: HardenedGuardEngine | None = None,
) -> None:
    guard = engine or HardenedGuardEngine.from_environment()
    register_sg_infosec_guard(app, engine=guard)
    guard.verify_event_client()
    guard.verify_management_client()
