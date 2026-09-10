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
