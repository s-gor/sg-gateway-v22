from app.clients.repository import count_clients, create_client
from app.db import init_db
from app.maintenance.backups import create_backup, list_backups, restore_backup


def test_create_and_restore_backup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Before", "recommended")

    backup = create_backup()
    create_client("After", "recommended")

    assert backup.name in {item.name for item in list_backups()}
    assert count_clients() == 2

    assert restore_backup(backup.name) is True
    assert count_clients() == 1


def test_create_backup_uses_unique_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    first = create_backup()
    second = create_backup()

    assert first.name != second.name
    assert first.path.exists()
    assert second.path.exists()



def test_restore_safety_backup_is_listed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Before", "recommended")

    backup = create_backup()
    create_client("After", "recommended")
    restore_backup(backup.name)

    names = {item.name for item in list_backups()}
    assert any(name.startswith("pre-restore-") for name in names)



def test_backup_kind_labels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Before", "recommended")

    backup = create_backup()
    create_client("After", "recommended")
    restore_backup(backup.name)

    backups = list_backups()
    kinds_by_name = {item.name: item.kind for item in backups}
    assert kinds_by_name[backup.name] == "Ручная резервная копия"
    assert "Страховочная копия перед восстановлением" in kinds_by_name.values()
