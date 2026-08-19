from flask import Flask

from app.db import init_db
from app.maintenance import health
from app.maintenance.health import collect_health_checks, health_summary


def test_health_checks_report_expected_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    checks = collect_health_checks()
    names = {check.name for check in checks}

    assert "База данных" in names
    assert "Каталог резервных копий" in names
    assert "Настройки AmneziaWG" in names
    assert health_summary() in {"ok", "warning", "error"}


def test_login_health_summary_never_waits_for_runtime_checks(monkeypatch):
    app = Flask(__name__)

    @app.get("/login")
    def login():
        return health.health_summary()

    def should_not_run():
        raise AssertionError("login must not execute synchronous runtime health checks")

    monkeypatch.setattr(health, "collect_health_checks", should_not_run)
    response = app.test_client().get("/login")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "warning"
