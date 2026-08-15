from app.hostd.client import hostd_health, run_hostd_command


def test_unavailable_hostd_is_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_HOSTD_URL", "http://127.0.0.1:9")

    result = hostd_health()

    assert result.status == "warning"
    assert result.payload["connected"] is False


def test_unavailable_hostd_command_is_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_HOSTD_URL", "http://127.0.0.1:9")

    result = run_hostd_command("awg.status")

    assert result.status == "warning"
    assert result.payload["connected"] is False