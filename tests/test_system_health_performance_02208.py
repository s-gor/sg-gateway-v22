from types import SimpleNamespace


def test_system_context_collects_health_only_once(monkeypatch):
    import app.main as main

    calls = 0

    def fake_checks():
        nonlocal calls
        calls += 1
        return [SimpleNamespace(status="warning")]

    monkeypatch.setattr(main, "collect_health_checks", fake_checks)
    monkeypatch.setattr(main, "health_summary", lambda: (_ for _ in ()).throw(AssertionError("system context must derive summary from collected checks")))
    monkeypatch.setattr(main, "list_connections", lambda: [])
    monkeypatch.setattr(main, "_dashboard_resources", lambda: {})
    monkeypatch.setattr(main, "count_clients", lambda: 0)
    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "get_release_manifest", lambda: {})
    monkeypatch.setattr(main, "get_version", lambda: "test")

    result = main._sg_gateway_system_context()

    assert calls == 1
    assert result["report"]["health"] == "warning"
    assert len(result["health_checks"]) == 1


def test_connection_health_reads_settings_in_one_batch(monkeypatch):
    from app.maintenance import health

    settings = {
        "amneziawg31": SimpleNamespace(
            host="awg31.example",
            port=587,
            config={"server_public_key": "real-key"},
        ),
        "xray": SimpleNamespace(
            host="xray.example",
            port=443,
            config={"public_key": "real-key", "short_id": "abcd", "server_name": "example.com"},
        ),
    }
    calls = 0

    def batch(engines):
        nonlocal calls
        calls += 1
        assert tuple(engines) == ("amneziawg31", "xray")
        return settings

    monkeypatch.setattr(health, "list_connection_settings", batch, raising=False)
    monkeypatch.setattr(
        health,
        "get_connection_settings",
        lambda *_: (_ for _ in ()).throw(AssertionError("health must not open settings DB per engine")),
    )
    monkeypatch.setattr(
        health,
        "run_hostd_command",
        lambda command: SimpleNamespace(status="ok", message=f"{command}: ok"),
    )

    checks = health._connection_checks()

    assert calls == 1
    assert len(checks) == 2
