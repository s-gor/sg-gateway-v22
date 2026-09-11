from types import SimpleNamespace


def test_server_identity_uses_direct_awg31_settings_and_reuses_recent_lookup(monkeypatch):
    import app.main as main

    calls = {"settings": 0, "geo": 0}

    def forbidden_connections():
        raise AssertionError("server identity must not build the full Connections catalogue")

    def fake_settings(engine):
        assert engine == "amneziawg31"
        calls["settings"] += 1
        return SimpleNamespace(host="awg31-performance.example.invalid")

    def fake_geo(address):
        calls["geo"] += 1
        assert address == "awg31-performance.example.invalid"
        return "fr"

    monkeypatch.setattr(main, "list_connections", forbidden_connections)
    monkeypatch.setattr(main, "get_connection_settings", fake_settings)
    monkeypatch.setattr(main, "lookup_country_code", fake_geo)
    config = SimpleNamespace(
        public_address="performance-cache.example.invalid",
        host="127.0.0.1",
        country_code="unknown",
        server_name="Performance test",
    )

    main._SERVER_IDENTITY_CACHE.update({"key": None, "updated_at": 0.0, "value": None})
    first = main._sg_gateway_server_identity(config)
    second = main._sg_gateway_server_identity(config)

    assert first == second
    assert first["address"] == "awg31-performance.example.invalid"
    assert calls == {"settings": 1, "geo": 1}


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


def test_recovery_page_reuses_one_health_scan(monkeypatch):
    import app.main as main

    checks = [SimpleNamespace(status="warning")]
    calls = {"checks": 0}

    def fake_checks():
        calls["checks"] += 1
        return checks

    def forbidden_summary():
        raise AssertionError("Recovery must derive its summary from the checks it already collected")

    monkeypatch.setattr(main, "collect_health_checks", fake_checks)
    monkeypatch.setattr(main, "health_summary", forbidden_summary)
    monkeypatch.setattr(main, "list_backups", lambda: [])
    monkeypatch.setattr(main, "render_template", lambda template, **context: (template, context))

    with main.app.test_request_context("/recovery"):
        template, context = main.app.view_functions["recovery"]()

    assert template == "recovery.html"
    assert context["health_checks"] is checks
    assert context["health"] == "warning"
    assert calls["checks"] == 1


def test_system_activity_api_uses_aggregate_counts_not_full_client_catalogue(monkeypatch):
    import app.main as main

    expected = {
        "total": 12,
        "enabled": 9,
        "devices_total": 17,
        "devices_enabled": 13,
    }

    def forbidden_clients():
        raise AssertionError("activity polling must not hydrate every client/device/credential")

    monkeypatch.setattr(main, "collect_system_activity", lambda: {"cpu": {"percent": 1}})
    monkeypatch.setattr(main, "list_clients", forbidden_clients)
    monkeypatch.setattr(main, "client_activity_counts", lambda: expected, raising=False)

    with main.app.test_request_context("/api/system/activity"):
        response = main.app.view_functions["system_activity_api"]()
        payload = response.get_json()

    assert payload["clients"] == expected


def test_connections_page_reuses_batched_settings(monkeypatch):
    import app.main as main

    settings_map = {
        "xray": SimpleNamespace(engine="xray"),
        "mihomo": SimpleNamespace(engine="mihomo"),
        "amneziawg31": SimpleNamespace(engine="amneziawg31"),
    }
    calls = {"batch": 0, "connections": 0}

    def batch(engines):
        calls["batch"] += 1
        assert tuple(engines) == ("xray", "mihomo", "amneziawg31")
        return settings_map

    def connections(*, settings_map=None):
        calls["connections"] += 1
        assert settings_map is not None
        return []

    monkeypatch.setattr(main, "list_connection_settings", batch, raising=False)
    monkeypatch.setattr(main, "list_connections", connections)
    monkeypatch.setattr(main, "get_connection_settings", lambda *_: (_ for _ in ()).throw(AssertionError("page must reuse batched settings")))
    monkeypatch.setattr(main, "get_shared_awg_dns", lambda: None)
    monkeypatch.setattr(main, "xray_profiles_overview", lambda: {})
    monkeypatch.setattr(main, "mihomo_overview", lambda: {})
    monkeypatch.setattr(main, "count_clients", lambda: 0)
    monkeypatch.setattr(main, "render_template", lambda template, **context: (template, context))

    with main.app.test_request_context("/connections"):
        template, context = main.app.view_functions["connections"]()

    assert template == "connections.html"
    assert context["xray_settings"] is settings_map["xray"]
    assert calls == {"batch": 1, "connections": 1}


def test_routing_page_reuses_batched_settings(monkeypatch):
    import app.main as main

    settings_map = {
        "xray": SimpleNamespace(engine="xray"),
        "mihomo": SimpleNamespace(engine="mihomo"),
        "amneziawg31": SimpleNamespace(engine="amneziawg31"),
        "amneziawg": SimpleNamespace(engine="amneziawg"),
    }
    calls = {"batch": 0, "connections": 0}

    def batch(engines):
        calls["batch"] += 1
        assert tuple(engines) == ("xray", "mihomo", "amneziawg31", "amneziawg")
        return settings_map

    def connections(*, settings_map=None):
        calls["connections"] += 1
        assert settings_map is not None
        return []

    monkeypatch.setattr(main, "list_connection_settings", batch, raising=False)
    monkeypatch.setattr(main, "list_connections", connections)
    monkeypatch.setattr(main, "get_connection_settings", lambda *_: (_ for _ in ()).throw(AssertionError("page must reuse batched settings")))
    monkeypatch.setattr(main, "xray_profiles_overview", lambda: {})
    monkeypatch.setattr(main, "geofiles_overview", lambda: {})
    monkeypatch.setattr(main, "routing_templates_overview", lambda: {})
    monkeypatch.setattr(main, "warp_overview", lambda: {})
    monkeypatch.setattr(main, "mihomo_overview", lambda: {})
    monkeypatch.setattr(main, "count_clients", lambda: 0)
    monkeypatch.setattr(main, "render_template", lambda template, **context: (template, context))

    with main.app.test_request_context("/routing"):
        template, context = main.app.view_functions["routing"]()

    assert template == "routing.html"
    assert context["awg_settings"] is settings_map["amneziawg"]
    assert context["xray_settings"] is settings_map["xray"]
    assert calls == {"batch": 1, "connections": 1}
