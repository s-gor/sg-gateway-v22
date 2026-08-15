from app.db import init_db
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