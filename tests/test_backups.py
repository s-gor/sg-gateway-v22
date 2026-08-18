from app.clients.repository import count_clients, create_client
from app.db import init_db
from app.maintenance.backups import (
    backup_cleanup_preview,
    create_backup,
    delete_old_backups,
    list_backups,
    restore_backup,
)


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


def test_delete_old_backups_keeps_two_latest_and_reports_freed_space(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()

    created = [create_backup() for _ in range(5)]
    preview = backup_cleanup_preview()

    assert preview.total_count == 5
    assert preview.delete_count == 3
    assert preview.keep_count == 2

    result = delete_old_backups()
    remaining = list_backups()

    assert result.deleted_count == 3
    assert result.freed_bytes == sum(item.size_bytes for item in created[:3])
    assert result.kept_count == 2
    assert result.failed_names == ()
    assert [item.name for item in remaining] == [created[4].name, created[3].name]


def test_delete_old_backups_with_two_copies_deletes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    create_backup()
    create_backup()

    result = delete_old_backups()

    assert result.deleted_count == 0
    assert result.freed_bytes == 0
    assert result.kept_count == 2
    assert len(list_backups()) == 2
