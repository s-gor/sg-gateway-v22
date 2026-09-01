from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.security.sg_infosec_guard import (
    AlertStore,
    GuardEngine,
    GuardSettings,
    ReputationIndex,
    SlidingWindowLimiter,
)


class RequestStub:
    def __init__(
        self,
        *,
        path: str,
        method: str = "GET",
        query: bytes = b"",
        body: bytes = b"",
        content_type: str = "text/plain",
        content_length: int | None = None,
        remote_addr: str = "203.0.113.10",
    ) -> None:
        self.path = path
        self.method = method
        self.query_string = query
        self._body = body
        self.content_type = content_type
        self.content_length = len(body) if content_length is None else content_length
        self.remote_addr = remote_addr
        self.headers: dict[str, str] = {}
        self.endpoint = "test"

    def get_data(self, *, cache: bool, as_text: bool = False) -> bytes | str:
        assert cache is True
        return self._body.decode("utf-8", errors="replace") if as_text else self._body


def _settings(tmp_path: Path, **overrides: object) -> GuardSettings:
    payload: dict[str, object] = {
        "mode": "enforce",
        "max_body_bytes": 65536,
        "login_requests_per_minute": 20,
        "api_requests_per_minute": 120,
        "block_score": 80,
        "notification_min_score": 70,
        "notification_webhook": "",
    }
    payload.update(overrides)
    path = tmp_path / "guard.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return GuardSettings.load(path)


def test_sensitive_probe_is_blocked_without_storing_request_content(tmp_path: Path) -> None:
    alerts = AlertStore(tmp_path / "alerts.jsonl", max_entries=100)
    engine = GuardEngine(settings=_settings(tmp_path), alerts=alerts)

    result = engine.evaluate(RequestStub(path="/.env"), ip="203.0.113.10")

    assert result.action == "block"
    assert result.status_code == 403
    assert "sensitive-path" in result.rule_ids
    stored = alerts.list_recent(10)
    assert len(stored) == 1
    assert stored[0]["ip"] == "203.0.113.10"
    assert ".env" not in json.dumps(stored[0])


def test_sqli_and_xss_are_detected_in_query_and_small_body(tmp_path: Path) -> None:
    engine = GuardEngine(settings=_settings(tmp_path), alerts=AlertStore(tmp_path / "alerts.jsonl"))

    sqli = engine.evaluate(
        RequestStub(path="/api/client", query=b"id=1%20UNION%20SELECT%20password%20FROM%20users"),
        ip="198.51.100.2",
    )
    xss = engine.evaluate(
        RequestStub(
            path="/api/client",
            method="POST",
            body=b'{"name":"<script>alert(1)</script>"}',
            content_type="application/json",
        ),
        ip="198.51.100.3",
    )

    assert sqli.action == "block"
    assert "sqli" in sqli.rule_ids
    assert xss.action == "block"
    assert "xss" in xss.rule_ids


def test_monitor_mode_records_but_does_not_reject(tmp_path: Path) -> None:
    alerts = AlertStore(tmp_path / "alerts.jsonl")
    engine = GuardEngine(settings=_settings(tmp_path, mode="monitor"), alerts=alerts)

    result = engine.evaluate(RequestStub(path="/.git/config"), ip="203.0.113.15")

    assert result.action == "monitor"
    assert result.status_code == 200
    assert alerts.unread_count() == 1


def test_oversized_body_and_dangerous_method_are_rejected(tmp_path: Path) -> None:
    engine = GuardEngine(settings=_settings(tmp_path), alerts=AlertStore(tmp_path / "alerts.jsonl"))

    oversized = engine.evaluate(
        RequestStub(path="/api/upload", method="POST", content_length=70000),
        ip="203.0.113.20",
    )
    trace = engine.evaluate(RequestStub(path="/", method="TRACE"), ip="203.0.113.21")

    assert oversized.action == "block"
    assert "body-size" in oversized.rule_ids
    assert trace.action == "block"
    assert "dangerous-method" in trace.rule_ids


def test_reputation_uses_longest_prefix_and_ignores_expired_entries(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "reputation.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {"cidr": "203.0.113.0/24", "score": 60, "country": "ZZ", "asn": 64500, "tags": ["scanner"]},
                    {"cidr": "203.0.113.128/25", "score": 95, "country": "ZZ", "asn": 64501, "tags": ["botnet"]},
                    {"cidr": "198.51.100.0/24", "score": 100, "expires_at": (now - timedelta(minutes=1)).isoformat()},
                ]
            }
        ),
        encoding="utf-8",
    )

    index = ReputationIndex.load(path, now=now)

    match = index.lookup("203.0.113.200")
    assert match is not None
    assert match.score == 95
    assert match.asn == 64501
    assert index.lookup("198.51.100.9") is None


def test_high_risk_reputation_blocks_without_signature(tmp_path: Path) -> None:
    reputation_path = tmp_path / "reputation.json"
    reputation_path.write_text(
        json.dumps({"entries": [{"cidr": "203.0.113.0/24", "score": 90, "tags": ["abuse"]}]}),
        encoding="utf-8",
    )
    engine = GuardEngine(
        settings=_settings(tmp_path),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
        reputation=ReputationIndex.load(reputation_path),
    )

    result = engine.evaluate(RequestStub(path="/login"), ip="203.0.113.50")

    assert result.action == "block"
    assert "reputation" in result.rule_ids
    assert result.reputation["score"] == 90


def test_rate_limit_is_per_ip_and_window(tmp_path: Path) -> None:
    limiter = SlidingWindowLimiter(max_keys=32)
    start = 1_000.0

    assert limiter.allow("203.0.113.1", "login", limit=2, window_seconds=60, now=start)
    assert limiter.allow("203.0.113.1", "login", limit=2, window_seconds=60, now=start + 1)
    assert not limiter.allow("203.0.113.1", "login", limit=2, window_seconds=60, now=start + 2)
    assert limiter.allow("203.0.113.2", "login", limit=2, window_seconds=60, now=start + 2)
    assert limiter.allow("203.0.113.1", "login", limit=2, window_seconds=60, now=start + 61)


def test_alert_store_acknowledges_and_bounds_history(tmp_path: Path) -> None:
    store = AlertStore(tmp_path / "alerts.jsonl", max_entries=3)
    ids = []
    for index in range(5):
        ids.append(
            store.append(
                ip=f"203.0.113.{index}",
                action="monitor",
                score=40,
                rule_ids=["test"],
                scope="admin-api",
                reputation={},
            )
        )

    items = store.list_recent(10)
    assert len(items) == 3
    assert {item["id"] for item in items} == set(ids[-3:])
    assert store.unread_count() == 3
    assert store.acknowledge(ids[-1])
    assert store.unread_count() == 2
    store.acknowledge_all()
    assert store.unread_count() == 0


def test_settings_reject_unsafe_values(tmp_path: Path) -> None:
    path = tmp_path / "guard.json"
    path.write_text(json.dumps({"mode": "unknown"}), encoding="utf-8")

    with pytest.raises(ValueError, match="mode"):
        GuardSettings.load(path)
