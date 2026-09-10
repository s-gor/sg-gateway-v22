from __future__ import annotations

import json


def test_tls_overview_never_performs_implicit_network_dns_check(tmp_path, monkeypatch):
    from app.security import tls

    state_dir = tmp_path / "security"
    state_dir.mkdir()
    (state_dir / "tls-state.json").write_text(
        json.dumps(
            {
                "domain": "vpn.example.com",
                "https_ready": True,
                "certificate": {"days_left": 30},
                "public_port": 443,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tls, "_state_dir", lambda: state_dir)
    monkeypatch.setattr(tls, "_service_active", lambda name: False)
    monkeypatch.setattr(tls, "_service_enabled", lambda name: False)
    monkeypatch.setattr(tls, "_safe_is_file", lambda path: False)

    def forbidden_network_check(domain):
        raise AssertionError(f"implicit DNS/network check for {domain}")

    monkeypatch.setattr(tls, "check_domain", forbidden_network_check)

    result = tls.overview()

    assert result["domain"] == "vpn.example.com"
    assert result["dns"] is None


def test_health_summary_reuses_recent_expensive_scan(monkeypatch):
    from app.maintenance import health

    calls = 0

    def fake_checks():
        nonlocal calls
        calls += 1
        return [health.HealthCheck("test", "ok", "ok")]

    monkeypatch.setattr(health, "collect_health_checks", fake_checks)
    health._HEALTH_SUMMARY_CACHE["updated_at"] = 0.0
    health._HEALTH_SUMMARY_CACHE["value"] = None

    assert health.health_summary() == "ok"
    assert health.health_summary() == "ok"
    assert calls == 1
