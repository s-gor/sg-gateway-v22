from __future__ import annotations

import io
import sqlite3
from pathlib import Path

from flask import Flask

from app.clients.repository import count_clients, create_client
from app.db import get_database_path, init_db
from app.maintenance.backups import (
    UPLOAD_RESTORE_NAME,
    list_backups,
    restore_backup_transaction,
)


ROOT = Path(__file__).resolve().parents[1]


def _snapshot_current_database() -> bytes:
    return get_database_path().read_bytes()


def test_uploaded_sqlite_uses_existing_restore_transaction_and_creates_safety(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Before", "recommended")
    downloaded = _snapshot_current_database()
    create_client("After", "recommended")
    assert count_clients() == 2

    app = Flask(__name__)
    with app.test_request_context(
        "/maintenance/backups/__upload__/restore",
        method="POST",
        data={"backup": (io.BytesIO(downloaded), "downloaded.sqlite")},
        content_type="multipart/form-data",
    ):
        restored = restore_backup_transaction(UPLOAD_RESTORE_NAME)

    assert restored.ok is True
    assert restored.backup is not None
    assert restored.backup.name.startswith("sg-gateway-uploaded-")
    assert restored.safety_backup is not None
    assert restored.safety_backup.name.startswith("pre-restore-")
    assert count_clients() == 1

    names = {item.name for item in list_backups()}
    assert restored.backup.name in names
    assert restored.safety_backup.name in names


def test_uploaded_sqlite_is_validated_before_live_database_is_mutated(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init_db()
    create_client("Keep", "recommended")
    before = _snapshot_current_database()

    app = Flask(__name__)
    with app.test_request_context(
        "/maintenance/backups/__upload__/restore",
        method="POST",
        data={"backup": (io.BytesIO(b"not a sqlite database"), "broken.sqlite")},
        content_type="multipart/form-data",
    ):
        restored = restore_backup_transaction(UPLOAD_RESTORE_NAME)

    assert restored.ok is False
    assert restored.backup is None
    assert restored.safety_backup is None
    assert _snapshot_current_database() == before
    assert not any(item.name.startswith("sg-gateway-uploaded-") for item in list_backups())


def test_uploaded_foreign_sqlite_is_rejected_by_sg_gateway_schema_check(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    init_db()
    before = _snapshot_current_database()

    foreign = tmp_path / "foreign.sqlite"
    database = sqlite3.connect(foreign)
    try:
        database.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        database.commit()
    finally:
        database.close()

    app = Flask(__name__)
    with app.test_request_context(
        "/maintenance/backups/__upload__/restore",
        method="POST",
        data={"backup": (io.BytesIO(foreign.read_bytes()), "foreign.sqlite")},
        content_type="multipart/form-data",
    ):
        restored = restore_backup_transaction(UPLOAD_RESTORE_NAME)

    assert restored.ok is False
    assert "не похож на базу SG-Gateway" in restored.message
    assert _snapshot_current_database() == before


def test_maintenance_ui_exposes_clients_keys_https_and_sqlite_file_restore() -> None:
    base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
    ui = (ROOT / "app/web/static/sg-clients-keys-download-v1.js").read_text(
        encoding="utf-8"
    )

    assert "sg-maintenance-recovery-v1.js" in base
    assert "sg-clients-keys-download-v1.js" in base
    assert base.index("sg-maintenance-recovery-v1.js") < base.index(
        "sg-clients-keys-download-v1.js"
    )

    assert 'MAINTENANCE_UI_REVISION = "clients-keys-https-sqlite-v2"' in ui
    assert "CLIENTS, KEYS & HTTPS" in ui
    assert "Клиенты, ключи и HTTPS" in ui
    assert "активный HTTPS-домен, сертификат и private key" in ui
    assert "настройки протоколов" in ui
    assert 'SQLITE_UPLOAD_ACTION = "/maintenance/backups/__upload__/restore"' in ui
    assert 'form.enctype = "multipart/form-data"' in ui
    assert 'input.name = "backup"' in ui
    assert "Восстановить из файла" in ui
