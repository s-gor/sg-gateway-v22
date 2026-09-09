from types import SimpleNamespace

from app.db import init_db
import app.maintenance.health as health
from app.maintenance.health import collect_health_checks, health_summary


def test_health_checks_report_expected_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    checks = collect_health_checks()
    names = {check.name for check in checks}

    assert "База данных" in names
    assert "Каталог резервных копий" in names
    assert "Настройки AmneziaWG 3.1" in names
    assert "Настройки AmneziaWG" not in names
    assert health_summary() in {"ok", "warning", "error"}


def test_awg_health_check_uses_awg31_only(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_get_connection_settings(engine: str):
        calls.append(("settings", engine))
        if engine == "amneziawg31":
            return SimpleNamespace(
                host="awg31.internal",
                port=587,
                config={"server_public_key": "real-awg31-key"},
            )
        if engine == "xray":
            return SimpleNamespace(
                host="example.test",
                port=443,
                config={
                    "public_key": "real-xray-key",
                    "short_id": "abcd1234",
                    "server_name": "www.example.com",
                },
            )
        raise AssertionError(f"retired engine health check requested: {engine}")

    def fake_run_hostd_command(command: str):
        calls.append(("hostd", command))
        return SimpleNamespace(status="ok", message="ready")

    monkeypatch.setattr(health, "get_connection_settings", fake_get_connection_settings)
    monkeypatch.setattr(health, "run_hostd_command", fake_run_hostd_command)

    checks = health._connection_checks()
    awg31 = next(check for check in checks if check.name == "Настройки AmneziaWG 3.1")

    assert awg31.status == "ok"
    assert awg31.message == "awg31.internal:587; hostd: ready"
    assert ("settings", "amneziawg31") in calls
    assert ("hostd", "awg31.status") in calls
    assert ("settings", "amneziawg") not in calls
    assert ("settings", "amneziawg3") not in calls
    assert ("hostd", "awg.status") not in calls
    assert ("hostd", "awg3.status") not in calls
