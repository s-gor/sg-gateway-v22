from types import SimpleNamespace


def test_xray_os_probes_reuse_recent_results(monkeypatch):
    from app.xray import profiles

    calls = []

    def fake_run(args, **kwargs):
        calls.append(tuple(args))
        if args[-1] == "version":
            return SimpleNamespace(returncode=0, stdout="Xray 26.9.9 test\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(profiles.subprocess, "run", fake_run)
    assert profiles._installed_xray_version() == "26.9.9"
    assert profiles._installed_xray_version() == "26.9.9"
    assert profiles._service_active() is True
    assert profiles._service_active() is True
    assert len(calls) == 2


def test_tls_systemctl_probes_reuse_recent_results(monkeypatch):
    from app.security import tls

    calls = []

    def fake_run(args, **kwargs):
        calls.append(tuple(args))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tls.subprocess, "run", fake_run)
    assert tls._service_active("nginx.service") is True
    assert tls._service_active("nginx.service") is True
    assert tls._service_active("certbot.timer") is True
    assert tls._service_active("certbot.timer") is True
    assert tls._service_enabled("certbot.timer") is True
    assert tls._service_enabled("certbot.timer") is True
    assert len(calls) == 3
