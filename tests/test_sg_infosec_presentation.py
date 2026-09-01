from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.security.sg_infosec_presentation import (
    IPIntelligenceResolver,
    present_guard_overview,
    present_management_overview,
)


class StaticResolver:
    def resolve(self, ip: object, reputation: object = None):
        return {
            "ip": str(ip),
            "country_code": "us",
            "country_name": "США",
            "country_flag": "🇺🇸",
            "asn": 7488,
            "organization": "CNServer LLC",
            "prefix": "144.225.6.0/23",
            "network_type_label": "Сеть хостинг-провайдера",
            "summary": "🇺🇸 США · AS7488 · CNServer LLC",
            "details": "Сеть 144.225.6.0/23 · Сеть хостинг-провайдера",
            "source": "RIPEstat + GeoIP",
            "available": True,
        }


class CountingResolver(StaticResolver):
    def __init__(self):
        self.calls: list[str] = []

    def resolve(self, ip: object, reputation: object = None):
        self.calls.append(str(ip))
        return super().resolve(ip, reputation)

    def resolve_many(self, values):
        result = {}
        for ip, reputation in values:
            key = str(ip)
            if key not in result:
                result[key] = self.resolve(key, reputation)
        return result


def test_ip_intelligence_combines_country_routing_data_reputation_and_cache(tmp_path: Path):
    calls: list[str] = []

    def fetcher(url: str, timeout: float):
        assert timeout <= 1.0
        calls.append(url)
        return {
            "status": "ok",
            "data": {
                "resource": "144.225.6.0/23",
                "asns": [{"asn": 7488, "holder": "CNServer LLC"}],
            },
        }

    cache = tmp_path / "ip-intelligence.json"
    resolver = IPIntelligenceResolver(
        cache_path=cache,
        country_lookup=lambda _ip: "us",
        fetcher=fetcher,
        now=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    first = resolver.resolve("144.225.6.182", {"tags": ["scanner", "hosting"]})

    assert first["summary"] == "🇺🇸 США · AS7488 · CNServer LLC"
    assert first["prefix"] == "144.225.6.0/23"
    assert first["organization"] == "CNServer LLC"
    assert first["network_type_label"] == "Сеть хостинг-провайдера"
    assert first["source"] == "RIPEstat + GeoIP"
    assert len(calls) == 1
    assert cache.exists()

    second_calls: list[str] = []
    second = IPIntelligenceResolver(
        cache_path=cache,
        country_lookup=lambda _ip: "unknown",
        fetcher=lambda url, timeout: second_calls.append(url),
        now=lambda: datetime(2026, 9, 2, tzinfo=timezone.utc),
    ).resolve("144.225.6.182")

    assert second["summary"] == first["summary"]
    assert second_calls == []


def test_ip_intelligence_is_fail_open_and_skips_non_global_addresses(tmp_path: Path):
    calls: list[str] = []

    def failed(url: str, timeout: float):
        calls.append(url)
        raise OSError("network unavailable")

    resolver = IPIntelligenceResolver(
        cache_path=tmp_path / "cache.json",
        country_lookup=lambda ip: "fr" if ip == "203.0.113.7" else "unknown",
        fetcher=failed,
        now=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    local = resolver.resolve("127.0.0.1")
    unavailable = resolver.resolve("203.0.113.7")

    assert local["summary"] == "Локальный адрес"
    assert local["source"] == "local"
    assert unavailable["summary"] == "🇫🇷 Франция · Сведения о сети недоступны"
    assert unavailable["available"] is False
    assert len(calls) == 1


def test_failed_lookup_uses_short_negative_cache(tmp_path: Path):
    current = [datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)]
    calls: list[str] = []

    def failed(url: str, timeout: float):
        calls.append(url)
        raise OSError("offline")

    resolver = IPIntelligenceResolver(
        cache_path=tmp_path / "cache.json",
        country_lookup=lambda _ip: "de",
        fetcher=failed,
        now=lambda: current[0],
        ttl=timedelta(days=7),
        negative_ttl=timedelta(hours=1),
    )

    resolver.resolve("198.51.100.10")
    current[0] += timedelta(minutes=30)
    resolver.resolve("198.51.100.10")
    assert len(calls) == 1

    current[0] += timedelta(hours=2)
    resolver.resolve("198.51.100.10")
    assert len(calls) == 2


def test_management_overview_humanizes_decisions_audit_and_time():
    raw = {
        "available": True,
        "status": "Работает",
        "active_decisions": [
            {
                "id": "decision-1",
                "ip": "144.225.6.182",
                "scope": "ssh",
                "reason_code": "threshold_exceeded",
                "state": "active",
                "backend": "nftables",
                "created_at": "2026-09-01T20:21:11.527289068Z",
                "expires_at": "2026-09-01T20:51:11.527289068Z",
            }
        ],
        "history": [
            {
                "id": "decision-1",
                "ip": "144.225.6.182",
                "scope": "ssh",
                "reason_code": "threshold_exceeded",
                "state": "active",
                "created_at": "2026-09-01T20:21:11Z",
                "expires_at": "2026-09-01T20:51:11Z",
            }
        ],
        "allowlist": [],
        "allowlist_count": 0,
        "audit": [
            {
                "action": "decision.auto_created",
                "target_type": "decision",
                "target_id": "decision-1",
                "result": "success",
                "occurred_at": "2026-09-01T20:21:11Z",
            }
        ],
        "last_sync": "01.09.2026 22:41:06",
        "error": "",
    }

    result = present_management_overview(
        raw,
        resolver=StaticResolver(),
        local_timezone=timezone(timedelta(hours=2)),
    )
    decision = result["active_decisions"][0]

    assert decision["scope_label"] == "Вход на сервер (SSH, порт 22)"
    assert decision["scope_effect"] == "Ограничен только удалённый вход на сервер. VPN продолжает работать."
    assert decision["reason_label"] == "Превышен лимит неудачных попыток"
    assert decision["state_label"] == "Активна"
    assert decision["expires_at_label"] == "01.09.2026, 22:51"
    assert decision["ip_intel"]["summary"] == "🇺🇸 США · AS7488 · CNServer LLC"
    assert decision["technical"]["scope"] == "ssh"
    assert result["audit"][0]["action_label"] == "Автоматически создана блокировка"
    assert result["audit"][0]["result_label"] == "Успешно"
    assert result["audit"][0]["occurred_at_label"] == "01.09.2026, 22:21"


def test_presentation_does_not_repeat_lookup_for_same_ip():
    resolver = CountingResolver()
    raw = {
        "available": True,
        "active_decisions": [{"id": "one", "ip": "144.225.6.182", "scope": "ssh"}],
        "history": [{"id": "one", "ip": "144.225.6.182", "scope": "ssh"}],
        "allowlist": [],
        "audit": [],
    }

    result = present_management_overview(raw, resolver=resolver)

    assert result["active_decisions"][0]["ip_intel"]["asn"] == 7488
    assert result["history"][0]["ip_intel"]["asn"] == 7488
    assert resolver.calls == ["144.225.6.182"]


def test_guard_overview_humanizes_actions_rules_and_network():
    raw = {
        "mode": "enforce",
        "settings": {},
        "counters": {},
        "unread_count": 1,
        "reputation_count": 1,
        "alerts": [
            {
                "id": "alert-1",
                "occurred_at": "2026-09-01T20:25:00Z",
                "ip": "144.225.6.182",
                "action": "block",
                "score": 95,
                "rule_ids": ["sensitive-path", "reputation"],
                "scope": "admin-api",
                "reputation": {"score": 90, "tags": ["hosting", "scanner"]},
                "acknowledged": False,
            }
        ],
    }

    result = present_guard_overview(
        raw,
        resolver=StaticResolver(),
        local_timezone=timezone(timedelta(hours=2)),
    )
    alert = result["alerts"][0]

    assert alert["action_label"] == "Запрос заблокирован"
    assert alert["scope_label"] == "API панели"
    assert alert["rule_labels"] == [
        "Сканирование закрытых путей",
        "Совпадение с локальной репутацией",
    ]
    assert alert["occurred_at_label"] == "01.09.2026, 22:25"
    assert alert["ip_intel"]["details"] == "Сеть 144.225.6.0/23 · Сеть хостинг-провайдера"
    assert alert["technical"]["action"] == "block"
