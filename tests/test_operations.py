from app.clients.repository import create_client, delete_client, set_client_enabled
from app.db import init_db
from app.maintenance.operations import count_operations, list_operations


def test_client_actions_are_logged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    client_id = create_client("Irina", "recommended")
    set_client_enabled(client_id, False)

    operations = list_operations()
    actions = [operation.action for operation in operations]

    assert count_operations() == 2
    assert "client.create" in actions
    assert "client.disable" in actions


def test_missing_client_actions_are_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    enabled = set_client_enabled(404, False)
    deleted = delete_client(404)

    operations = list_operations()
    assert enabled is False
    assert deleted is False
    assert count_operations() == 0
    assert operations == []
