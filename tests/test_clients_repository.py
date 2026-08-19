import pytest

from app.clients.repository import count_clients, create_client, list_clients
from app.engines import provisioning
from app.maintenance.operations import list_operations


def test_create_client_with_recommended_access(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    create_client("Irina iPhone", "recommended")

    clients = list_clients()
    assert count_clients() == 1
    assert clients[0].name == "Irina iPhone"
    assert clients[0].awg_status == "missing"
    assert clients[0].xray_status == "creating"
    assert clients[0].mihomo_status == "missing"
    assert clients[0].sgclient_status == "creating"
    assert clients[0].device_count == 1
    assert clients[0].active_device_count == 1


def test_create_client_normalizes_name_whitespace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    client_id = create_client("  Irina   iPhone  ", "recommended")

    clients = list_clients()
    assert client_id is not None
    assert clients[0].name == "Irina iPhone"


def test_create_client_rejects_duplicate_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    first_id = create_client("Irina iPhone", "recommended")
    second_id = create_client("  irina   iphone  ", "xray")

    operations = list_operations()
    assert first_id is not None
    assert second_id is None
    assert count_clients() == 1
    assert operations[0].status == "error"
    assert "Отклонено повторяющееся имя клиента" in operations[0].message


def test_create_client_rejects_invalid_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    empty_id = create_client("    ", "recommended")
    long_id = create_client("A" * 81, "recommended")

    assert empty_id is None
    assert long_id is None
    assert count_clients() == 0


def test_missing_awg3_runtime_blocks_client_without_persisted_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-awg3"
    monkeypatch.setattr(provisioning, "AWG3_AWG", str(missing / "bin" / "awg"))
    monkeypatch.setattr(provisioning, "AWG3_AWG_QUICK", str(missing / "bin" / "awg-quick"))
    monkeypatch.setattr(provisioning, "AWG3_GO", str(missing / "bin" / "amneziawg-go"))
    monkeypatch.setattr(provisioning, "AWG3_HELPER", str(missing / "deploy" / "helper.sh"))
    monkeypatch.setattr(
        provisioning,
        "AWG3_UNIT_PATHS",
        (str(missing / "systemd" / "sg-gateway-awg3.service"),),
    )

    with pytest.raises(RuntimeError, match="AWG3 требует восстановления") as error:
        create_client("AWG3 test", "amneziawg3")

    assert "Откройте Maintenance → AWG3 Runtime" in str(error.value)
    assert count_clients() == 0
