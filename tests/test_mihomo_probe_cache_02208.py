from types import SimpleNamespace


def test_mihomo_systemctl_and_version_probes_are_short_cached(monkeypatch, tmp_path):
    from app.mihomo import service

    service._clear_probe_cache()
    calls = []
    binary = tmp_path / "mihomo"
    binary.write_text("x", encoding="utf-8")
    monkeypatch.setattr(service, "MIHOMO_BINARY", binary)

    def fake_run(args, **kwargs):
        calls.append(tuple(str(x) for x in args))
        if args[-1] == "-v":
            return SimpleNamespace(returncode=0, stdout="Mihomo Meta v1.19.29\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    assert service._service_active() is True
    assert service._service_active() is True
    assert service._service_enabled() is True
    assert service._service_enabled() is True
    assert service._version() == "Mihomo Meta v1.19.29"
    assert service._version() == "Mihomo Meta v1.19.29"
    assert len(calls) == 3


def test_mihomo_hostd_status_is_short_cached(monkeypatch):
    from app.mihomo import service

    service._clear_probe_cache()
    calls = 0

    def fake_hostd(*args, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(status="ok", payload={
            "runtime_source": "hostd",
            "protocols": {
                "mieru": {"active": True, "port": 2099, "transport": "TCP"},
                "anytls": {"active": False, "port": 8443},
                "tuic": {"active": False, "port": 10443},
            },
        })

    monkeypatch.setattr(service, "run_hostd_command", fake_hostd)
    settings = {
        "mieru_enabled": True, "mieru_port": 2099, "mieru_transport": "TCP",
        "anytls_enabled": False, "anytls_port": 8443,
        "tuic_enabled": False, "tuic_port": 10443,
    }
    first = service._hostd_live_snapshot(settings)
    second = service._hostd_live_snapshot(settings)
    assert first is not None and second is not None
    assert first[1] == {"mieru"}
    assert second[1] == {"mieru"}
    assert calls == 1
