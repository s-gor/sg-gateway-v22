from types import SimpleNamespace


def test_server_identity_reuses_recent_lookup(monkeypatch):
    import app.main as main

    calls = {"connections": 0, "geo": 0}

    def fake_connections():
        calls["connections"] += 1
        return []

    def fake_geo(address):
        calls["geo"] += 1
        return "fr"

    monkeypatch.setattr(main, "list_connections", fake_connections)
    monkeypatch.setattr(main, "lookup_country_code", fake_geo)
    config = SimpleNamespace(
        public_address="performance-cache.example.invalid",
        host="127.0.0.1",
        country_code="unknown",
        server_name="Performance test",
    )

    first = main._sg_gateway_server_identity(config)
    second = main._sg_gateway_server_identity(config)

    assert first == second
    assert calls == {"connections": 1, "geo": 1}


def test_system_context_does_not_build_full_diagnostic_report(monkeypatch):
    import app.main as main

    def forbidden_diagnostic():
        raise AssertionError("full diagnostics must not run during ordinary System page rendering")

    monkeypatch.setattr(main, "build_diagnostic_report", forbidden_diagnostic)
    monkeypatch.setattr(main, "collect_health_checks", lambda: [])
    monkeypatch.setattr(main, "_dashboard_resources", lambda: {})
    monkeypatch.setattr(main, "list_connections", lambda: [])
    monkeypatch.setattr(main, "count_clients", lambda: 7)
    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "get_release_manifest", lambda: {"status": "STABLE"})
    monkeypatch.setattr(main, "get_version", lambda: "0.1.0-test")

    context = main._sg_gateway_system_context()

    assert context["report"]["health"] == "ok"
    assert context["report"]["version"] == "0.1.0-test"
    assert context["report"]["generated_at"]
    assert context["client_total"] == 7
