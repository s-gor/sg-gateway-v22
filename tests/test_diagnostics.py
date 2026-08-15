import json

from app.clients.repository import create_client
from app.db import init_db
from app.maintenance.diagnostics import build_diagnostic_report, build_diagnostic_report_json


def test_diagnostic_report_contains_core_sections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Irina", "recommended")

    report = build_diagnostic_report()

    assert report["service"] == "sg-gateway-panel"
    assert report["summary"]["clients"] == 1
    assert report["connections"]
    assert report["clients"][0]["name"] == "Irina"


def test_diagnostic_report_json_is_valid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    payload = build_diagnostic_report_json()
    report = json.loads(payload)

    assert report["service"] == "sg-gateway-panel"


def test_diagnostic_report_summarizes_operation_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    from app.clients.repository import set_client_enabled

    set_client_enabled(404, False)

    report = build_diagnostic_report()

    assert report["summary"]["operation_errors"] == 0
    assert report["summary"]["last_error"] is None



def test_diagnostic_report_includes_backup_kind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    from app.maintenance.backups import create_backup

    create_backup()
    report = build_diagnostic_report()

    assert report["backups"][0]["kind"] == "Ручная резервная копия"
